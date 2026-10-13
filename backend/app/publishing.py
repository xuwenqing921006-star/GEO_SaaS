import asyncio
import logging
import re

# Browser login uses a validated local executable with argv-only invocation.
import subprocess  # nosec B404
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Literal, TypedDict, cast
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.article_cover import article_cover_path, ensure_article_cover
from app.auth import Authenticated, CsrfAuthenticated
from app.config import Settings
from app.content_images import resolve_content_image_paths, select_content_image_ids
from app.database import (
    Client,
    ContentBrief,
    ContentDocument,
    ContentPublication,
    ContentVersion,
    DatabaseSession,
    FactSnapshot,
    Job,
    PublishingAccount,
    utc_now,
)
from app.publishing_images import PublishingImageError, prepare_publishing_image
from app.publishing_specs import (
    PUBLISHING_PLATFORM_SPECS,
    get_publishing_platform_spec,
    platform_prompt_contract,
)
from app.responses import error_response, success_response

LOGGER = logging.getLogger("geo-saas.publishing")

TOUTIAO_LOGIN_URL = "https://mp.toutiao.com/profile_v4/graphic/publish"
TOUTIAO_MANAGE_URL = "https://mp.toutiao.com/profile_v4/manage/content/all"
SOHU_PUBLISH_URL = "https://mp.sohu.com/mpfe/v4/contentManagement/news/addarticle?contentStatus=1"
BAIJIA_PUBLISH_URL = "https://baijiahao.baidu.com/builder/rc/edit?type=news"
NETEASE_LOGIN_URL = "https://mp.163.com/"
NETEASE_PUBLISH_URL = "https://mp.163.com/#/article-publish"
NETEASE_MANAGE_URL = "https://mp.163.com/#/content-manage"
PENGUIN_LOGIN_URL = "https://om.qq.com/"
PENGUIN_PUBLISH_URL = "https://om.qq.com/"
PENGUIN_MANAGE_URL = "https://om.qq.com/"
YIDIAN_LOGIN_URL = "https://mp.yidianzixun.com/"
YIDIAN_PUBLISH_URL = "https://mp.yidianzixun.com/"
YIDIAN_MANAGE_URL = "https://mp.yidianzixun.com/"
MAX_ACCOUNTS_PER_PLATFORM = 5
PUBLISHING_SESSION_CHECK_INTERVAL = timedelta(hours=24)
PUBLISHING_SESSION_DUE_SOON = timedelta(hours=2)
PUBLISHING_SESSION_SWEEP_INTERVAL_SECONDS = 5 * 60
PENDING_PUBLICATION_CHECK_INTERVAL = timedelta(minutes=10)
TOUTIAO_MIN_SUBMISSION_INTERVAL = timedelta(hours=3)
TOUTIAO_MAX_SUBMISSIONS_PER_24_HOURS = 2
TOUTIAO_ACTIVE_SUBMISSION_STATUSES = (
    "publishing",
    "pending_review",
    "published",
)
BAIJIA_MANAGEMENT_RECORD_GRACE_PERIOD = timedelta(minutes=30)
NETEASE_MANAGEMENT_RECORD_GRACE_PERIOD = timedelta(minutes=30)
PENGUIN_MANAGEMENT_RECORD_GRACE_PERIOD = timedelta(hours=2)
SOHU_BODY_IMAGE_COUNT = PUBLISHING_PLATFORM_SPECS["sohu"].image.target_body_images
SOHU_PUBLIC_IMAGE_LIMIT = 2
BAIJIA_BODY_IMAGE_COUNT = PUBLISHING_PLATFORM_SPECS["baijia"].image.target_body_images
BAIJIA_PUBLIC_IMAGE_LIMIT = 2
BAIJIA_TITLE_MAX_CHARS = PUBLISHING_PLATFORM_SPECS["baijia"].title_max_characters
NETEASE_BODY_IMAGE_COUNT = PUBLISHING_PLATFORM_SPECS["netease"].image.target_body_images
NETEASE_PUBLIC_IMAGE_LIMIT = PUBLISHING_PLATFORM_SPECS["netease"].image.maximum_body_images
NETEASE_TITLE_MAX_CHARS = PUBLISHING_PLATFORM_SPECS["netease"].title_max_characters
PENGUIN_BODY_IMAGE_COUNT = PUBLISHING_PLATFORM_SPECS["penguin"].image.target_body_images
PENGUIN_PUBLIC_IMAGE_LIMIT = PUBLISHING_PLATFORM_SPECS["penguin"].image.maximum_body_images
YIDIAN_BODY_IMAGE_COUNT = PUBLISHING_PLATFORM_SPECS["yidian"].image.target_body_images
YIDIAN_PUBLIC_IMAGE_LIMIT = PUBLISHING_PLATFORM_SPECS["yidian"].image.maximum_body_images
NETEASE_SUCCESS_RECEIPT = "发布成功,即将跳转到内容管理页"
BAIJIA_COVER_CONFIRM_PATTERN = re.compile(r"^确定(?:\s*\(\d+\))?$")


class PublishingPlatformEntry(TypedDict):
    id: str
    name: str
    description: str
    official_url: str
    login_url: str
    manage_url: str
    implementation_status: Literal["available"]


PUBLISHING_PLATFORM_CATALOG: tuple[PublishingPlatformEntry, ...] = (
    {
        "id": "toutiao",
        "name": "头条号",
        "description": "支持图文自动发布，每个账号使用独立本机浏览器会话。",
        "official_url": "https://mp.toutiao.com/",
        "login_url": TOUTIAO_LOGIN_URL,
        "manage_url": TOUTIAO_MANAGE_URL,
        "implementation_status": "available",
    },
    {
        "id": "sohu",
        "name": "搜狐号",
        "description": "支持图文自动发布，遇到验证码或安全验证时暂停任务。",
        "official_url": "https://mp.sohu.com/",
        "login_url": "https://mp.sohu.com/mpfe/v4/contentManagement/first/page",
        "manage_url": "https://mp.sohu.com/mpfe/v4/contentManagement/first/page",
        "implementation_status": "available",
    },
    {
        "id": "baijia",
        "name": "百家号",
        "description": "支持图文自动发布，发布结果以平台回执或内容管理记录为准。",
        "official_url": "https://baijiahao.baidu.com/",
        "login_url": "https://baijiahao.baidu.com/builder/rc/home",
        "manage_url": "https://baijiahao.baidu.com/builder/rc/content",
        "implementation_status": "available",
    },
    {
        "id": "netease",
        "name": "网易号",
        "description": "支持正文配图、单图封面和审核结果回查，每个账号使用独立会话。",
        "official_url": NETEASE_LOGIN_URL,
        "login_url": NETEASE_LOGIN_URL,
        "manage_url": NETEASE_MANAGE_URL,
        "implementation_status": "available",
    },
    {
        "id": "penguin",
        "name": "企鹅号",
        "description": "支持腾讯内容生态图文发布、AI声明和审核状态回查。",
        "official_url": PENGUIN_LOGIN_URL,
        "login_url": PENGUIN_LOGIN_URL,
        "manage_url": PENGUIN_MANAGE_URL,
        "implementation_status": "available",
    },
    {
        "id": "yidian",
        "name": "一点号",
        "description": "支持账号连接与一点号专属内容生成，首个真实账号需先完成发布页字段验证。",
        "official_url": YIDIAN_LOGIN_URL,
        "login_url": YIDIAN_LOGIN_URL,
        "manage_url": YIDIAN_MANAGE_URL,
        "implementation_status": "available",
    },
)
PUBLISHING_PLATFORMS_BY_ID = {item["id"]: item for item in PUBLISHING_PLATFORM_CATALOG}


def _publishing_editor_url(channel_id: str) -> str:
    if channel_id == "sohu":
        return SOHU_PUBLISH_URL
    if channel_id == "baijia":
        return BAIJIA_PUBLISH_URL
    if channel_id == "netease":
        return NETEASE_PUBLISH_URL
    if channel_id == "penguin":
        return PENGUIN_PUBLISH_URL
    if channel_id == "yidian":
        return YIDIAN_PUBLISH_URL
    return PUBLISHING_PLATFORMS_BY_ID[channel_id]["login_url"]


ConnectionStatus = Literal[
    "disconnected",
    "awaiting_login",
    "connected",
    "needs_login",
    "needs_verification",
    "error",
]
SessionHealth = Literal[
    "healthy",
    "check_due_soon",
    "check_due",
    "awaiting_login",
    "expired",
    "verification_required",
    "error",
    "not_checked",
]
PublicationStatus = Literal[
    "queued",
    "publishing",
    "pending_review",
    "published",
    "failed",
    "needs_login",
    "needs_verification",
    "rejected",
]


class PublishingChannelUpdate(BaseModel):
    enabled: bool
    version: int = Field(ge=1)


class PublishingAccountCreate(BaseModel):
    display_name: str = Field(min_length=1, max_length=100)


class PublishingAccountUpdate(BaseModel):
    version: int = Field(ge=1)
    display_name: str | None = Field(default=None, min_length=1, max_length=100)
    enabled: bool | None = None


@dataclass(frozen=True)
class ConnectionResult:
    status: ConnectionStatus
    account_name: str | None = None
    error_message: str | None = None


@dataclass(frozen=True)
class PublishResult:
    status: PublicationStatus
    public_url: str | None = None
    platform_post_id: str | None = None
    error_message: str | None = None


@dataclass(frozen=True)
class PublishingSessionHealth:
    status: SessionHealth
    label: str
    message: str
    next_check_at: datetime | None


def _publication_result_requires_account_pause(result: PublishResult) -> bool:
    if result.status in {"needs_login", "needs_verification"}:
        return True
    message = result.error_message or ""
    return result.status == "rejected" and any(
        marker in message for marker in ("禁言", "封禁", "账号处罚", "限制发布")
    )


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


async def toutiao_publication_guard(
    database: AsyncSession,
    account_id: UUID,
    *,
    now: datetime | None = None,
    exclude_publication_id: UUID | None = None,
) -> str | None:
    """Apply the product's conservative Toutiao cadence before queueing.

    Toutiao does not publish a universal safe daily quota.  These limits are a
    reversible account-protection policy after the observed batch-low-quality
    mute, not a claim about an official platform threshold.
    """

    current = _as_utc(now or utc_now())
    publications = list(
        (
            await database.scalars(
                select(ContentPublication)
                .where(
                    ContentPublication.publishing_account_id == account_id,
                    ContentPublication.channel_id == "toutiao",
                    ContentPublication.status.in_(TOUTIAO_ACTIVE_SUBMISSION_STATUSES),
                )
                .order_by(ContentPublication.updated_at.desc()),
            )
        ).all(),
    )
    recent_activity = sorted(
        (
            _as_utc(publication.submitted_at or publication.updated_at)
            for publication in publications
            if publication.id != exclude_publication_id
            and current - _as_utc(publication.submitted_at or publication.updated_at)
            <= timedelta(hours=24)
        ),
        reverse=True,
    )
    if len(recent_activity) >= TOUTIAO_MAX_SUBMISSIONS_PER_24_HOURS:
        return "头条号账号保护: 过去24小时已提交2篇文章，请稍后再发布"
    if recent_activity and current - recent_activity[0] < TOUTIAO_MIN_SUBMISSION_INTERVAL:
        remaining = TOUTIAO_MIN_SUBMISSION_INTERVAL - (current - recent_activity[0])
        remaining_minutes = max(1, int((remaining.total_seconds() + 59) // 60))
        return f"头条号账号保护: 两篇文章至少间隔3小时，请约{remaining_minutes}分钟后再发布"
    return None


def publishing_session_health(
    account: PublishingAccount,
    *,
    now: datetime | None = None,
) -> PublishingSessionHealth:
    checked_at = _as_utc(account.last_checked_at) if account.last_checked_at else None
    next_check_at = checked_at + PUBLISHING_SESSION_CHECK_INTERVAL if checked_at else None
    status = cast(ConnectionStatus, account.connection_status)

    if status == "needs_login":
        return PublishingSessionHealth(
            status="expired",
            label="登录已失效",
            message=account.last_error or "平台登录状态已失效，请使用原登录环境重新登录。",
            next_check_at=None,
        )
    if status == "needs_verification":
        return PublishingSessionHealth(
            status="verification_required",
            label="需要安全验证",
            message=account.last_error or "平台要求完成扫码、验证码或身份验证。",
            next_check_at=None,
        )
    if status == "error":
        error_message = account.last_error or "登录状态检测异常，请重新检测或重新登录。"
        if any(
            marker in error_message.casefold()
            for marker in ("browser logs:", "launch_persistent_context", "<launching>")
        ):
            error_message = "登录状态检测异常，请稍后重新检测，仍失败时使用原会话重新登录。"
        return PublishingSessionHealth(
            status="error",
            label="检测异常",
            message=error_message,
            next_check_at=None,
        )
    if status == "awaiting_login":
        return PublishingSessionHealth(
            status="awaiting_login",
            label="等待登录",
            message=(
                account.last_error or "请在已打开的独立登录环境完成登录，然后关闭窗口并检测连接。"
            ),
            next_check_at=None,
        )
    if status != "connected":
        return PublishingSessionHealth(
            status="not_checked",
            label="尚未连接",
            message="尚未建立有效登录状态。",
            next_check_at=None,
        )

    current = _as_utc(now or datetime.now(UTC))
    if next_check_at is None or current >= next_check_at:
        return PublishingSessionHealth(
            status="check_due",
            label="需要自动复检",
            message="已到每日自动复检时间，后台将自动核验登录状态。",
            next_check_at=next_check_at,
        )
    if next_check_at - current <= PUBLISHING_SESSION_DUE_SOON:
        return PublishingSessionHealth(
            status="check_due_soon",
            label="即将自动复检",
            message="登录状态即将进入每日自动复检，发布前仍会再次核验。",
            next_check_at=next_check_at,
        )
    return PublishingSessionHealth(
        status="healthy",
        label="登录状态正常",
        message="后台每天自动检测一次，并在每次发布前再次核验。",
        next_check_at=next_check_at,
    )


def _browser_profile_path(
    settings: Settings,
    channel_id: str = "toutiao",
    account_id: UUID | None = None,
) -> Path:
    if channel_id == "toutiao" and account_id is not None:
        legacy_path = (
            settings.storage_root / "publishing" / "toutiao" / "browser-profile"
        ).resolve()
        owner_file = legacy_path.parent / "legacy-account-id"
        if legacy_path.is_dir() and owner_file.is_file():
            try:
                if owner_file.read_text(encoding="utf-8").strip() == str(account_id):
                    return legacy_path
            except OSError:
                pass
    suffix = str(account_id) if account_id is not None else "legacy-default"
    path = (
        settings.storage_root / "publishing" / channel_id / "accounts" / suffix / "browser-profile"
    ).resolve()
    path.mkdir(parents=True, exist_ok=True)
    return path


def _claim_legacy_toutiao_profile(
    settings: Settings,
    accounts: list[PublishingAccount],
) -> None:
    legacy_path = (settings.storage_root / "publishing" / "toutiao" / "browser-profile").resolve()
    owner_file = legacy_path.parent / "legacy-account-id"
    if not legacy_path.is_dir() or owner_file.exists():
        return
    first_toutiao = next(
        (account for account in accounts if account.channel_id == "toutiao"),
        None,
    )
    if first_toutiao is None:
        return
    owner_file.write_text(str(first_toutiao.id), encoding="utf-8")


def _chrome_candidates() -> tuple[Path, ...]:
    return (
        Path(r"C:\Program Files\Google\Chrome\Application\chrome.exe"),
        Path(r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"),
        Path.home() / "AppData/Local/Google/Chrome/Application/chrome.exe",
        Path(r"C:\Program Files\Microsoft\Edge\Application\msedge.exe"),
        Path(r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"),
    )


def _browser_executable(settings: Settings) -> Path:
    if settings.browser_executable_path is not None:
        candidate = settings.browser_executable_path.expanduser().resolve()
        if candidate.is_file():
            return candidate
        raise RuntimeError("配置的浏览器程序不存在")
    for candidate in _chrome_candidates():
        if candidate.is_file():
            return candidate.resolve()
    raise RuntimeError("未找到 Chrome 或 Edge，请先安装浏览器")


def open_login_window(settings: Settings, channel_id: str, account_id: UUID) -> None:
    if settings.publishing_execution_mode == "fixed_mock":
        return
    platform = PUBLISHING_PLATFORMS_BY_ID[channel_id]
    executable = _browser_executable(settings)
    profile = _browser_profile_path(settings, channel_id, account_id)
    flags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
    # Executable, profile path and login URL are resolved from trusted server config.
    subprocess.Popen(  # nosec B603
        [
            str(executable),
            f"--user-data-dir={profile}",
            "--profile-directory=Default",
            "--no-first-run",
            "--no-default-browser-check",
            platform["login_url"],
        ],
        creationflags=flags,
        close_fds=True,
    )


def open_toutiao_login_window(settings: Settings) -> None:
    """Legacy helper kept for adapter tests and older local callers."""
    if settings.publishing_execution_mode == "fixed_mock":
        return
    executable = _browser_executable(settings)
    profile = _browser_profile_path(settings)
    flags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
    # Executable, profile path and login URL are resolved from trusted server config.
    subprocess.Popen(  # nosec B603
        [
            str(executable),
            f"--user-data-dir={profile}",
            "--profile-directory=Default",
            "--no-first-run",
            "--no-default-browser-check",
            TOUTIAO_LOGIN_URL,
        ],
        creationflags=flags,
        close_fds=True,
    )


def _looks_logged_out(url: str, body_text: str) -> bool:
    normalized_url = url.casefold()
    if any(token in normalized_url for token in ("login", "passport", "sso")):
        return True
    compact = re.sub(r"\s+", "", body_text)
    return "扫码登录" in compact or "手机号登录" in compact


async def _confirm_toutiao_logged_out(
    page: Any,
    *,
    attempts: int = 3,
    delay_ms: int = 1500,
) -> bool:
    """Require a stable logged-out page instead of trusting one transient render."""

    for attempt in range(max(1, attempts)):
        body_text = await page.locator("body").inner_text(timeout=5000)
        if not _looks_logged_out(page.url, body_text):
            return False
        if attempt < attempts - 1:
            await page.wait_for_timeout(delay_ms)
    return True


async def verify_toutiao_connection(
    settings: Settings,
    *,
    account_id: UUID | None = None,
) -> ConnectionResult:
    if settings.publishing_execution_mode == "fixed_mock":
        return ConnectionResult(status="connected", account_name="头条号测试账号")
    try:
        from playwright.async_api import async_playwright
    except ImportError:
        return ConnectionResult(status="error", error_message="自动发布组件未安装")
    try:
        async with async_playwright() as playwright:
            context = await playwright.chromium.launch_persistent_context(
                str(_browser_profile_path(settings, "toutiao", account_id)),
                executable_path=str(_browser_executable(settings)),
                headless=True,
                args=["--disable-blink-features=AutomationControlled"],
            )
            try:
                page = context.pages[0] if context.pages else await context.new_page()
                await page.goto(TOUTIAO_LOGIN_URL, wait_until="domcontentloaded", timeout=30_000)
                await page.wait_for_timeout(1500)
                if await _confirm_toutiao_logged_out(page):
                    return ConnectionResult(
                        status="needs_login",
                        error_message="头条号登录已失效，请重新登录",
                    )
                account_name: str | None = None
                account = page.locator(
                    '[class*="user-name"], [class*="account-name"], [class*="avatar-name"]',
                ).first
                if await account.count():
                    value = (await account.inner_text()).strip()
                    account_name = value[:200] or None
                return ConnectionResult(status="connected", account_name=account_name)
            finally:
                await context.close()
    except Exception as error:
        message = str(error)
        if _browser_profile_in_use_error(message):
            return ConnectionResult(
                status="awaiting_login",
                error_message="头条号登录窗口仍在打开，请关闭窗口后再次检测连接",
            )
        else:
            LOGGER.warning(
                "publishing_connection_check_failed",
                extra={"event": "publishing_connection_check_failed", "channel_id": "toutiao"},
                exc_info=True,
            )
            message = "头条号登录状态检测异常，请稍后重新检测或使用原会话重新登录"
        return ConnectionResult(status="error", error_message=message[:500])


def _has_security_verification(body_text: str) -> bool:
    compact = re.sub(r"\s+", "", body_text)
    return any(
        token in compact for token in ("安全验证", "请完成验证", "滑块验证", "验证码", "身份验证")
    )


def _browser_profile_in_use_error(message: str) -> bool:
    normalized = message.casefold()
    return any(
        token in normalized
        for token in (
            "user data directory is already in use",
            "processsingleton",
            "process singleton",
            "profile appears to be in use",
            "opening in existing browser session",
            "exitcode=21",
        )
    )


async def verify_publishing_account(
    settings: Settings,
    *,
    channel_id: str,
    account_id: UUID,
) -> ConnectionResult:
    platform = PUBLISHING_PLATFORMS_BY_ID[channel_id]
    if channel_id == "toutiao":
        return await verify_toutiao_connection(settings, account_id=account_id)
    if settings.publishing_execution_mode == "fixed_mock":
        return ConnectionResult(
            status="connected",
            account_name=f"{platform['name']}测试账号",
        )
    try:
        from playwright.async_api import async_playwright
    except ImportError:
        return ConnectionResult(status="error", error_message="自动发布组件未安装")
    try:
        async with async_playwright() as playwright:
            context = await playwright.chromium.launch_persistent_context(
                str(_browser_profile_path(settings, channel_id, account_id)),
                executable_path=str(_browser_executable(settings)),
                headless=True,
                args=["--disable-blink-features=AutomationControlled"],
            )
            try:
                page = context.pages[0] if context.pages else await context.new_page()
                await page.goto(
                    platform["login_url"],
                    wait_until="domcontentloaded",
                    timeout=30_000,
                )
                await page.wait_for_timeout(1800)
                body_text = await page.locator("body").inner_text(timeout=5000)
                if _looks_logged_out(page.url, body_text):
                    return ConnectionResult(
                        status="needs_login",
                        error_message=f"{platform['name']}登录已失效，请重新登录",
                    )
                if _has_security_verification(body_text):
                    return ConnectionResult(
                        status="needs_verification",
                        error_message=f"{platform['name']}要求完成安全验证",
                    )
                account_name: str | None = None
                account = page.locator(
                    '[class*="user-name"], [class*="account-name"], '
                    '[class*="avatar-name"], [class*="nickname"]',
                ).first
                if await account.count() and await account.is_visible():
                    value = (await account.inner_text()).strip()
                    account_name = value[:200] or None
                return ConnectionResult(status="connected", account_name=account_name)
            finally:
                await context.close()
    except Exception as error:
        message = str(error)
        if _browser_profile_in_use_error(message):
            return ConnectionResult(
                status="awaiting_login",
                error_message=(f"{platform['name']}登录窗口仍在打开，请关闭窗口后再次检测连接"),
            )
        else:
            LOGGER.warning(
                "publishing_connection_check_failed",
                extra={
                    "event": "publishing_connection_check_failed",
                    "channel_id": channel_id,
                },
                exc_info=True,
            )
            message = f"{platform['name']}登录状态检测异常，请稍后重新检测或使用原会话重新登录"
        return ConnectionResult(status="error", error_message=message[:500])


def _markdown_to_plain_text(markdown: str) -> str:
    text = re.sub(r"<!--.*?-->", "", markdown, flags=re.DOTALL)
    text = re.sub(r"(?m)^#{1,6}\s+", "", text)
    text = re.sub(r"(?m)^\s*[-*+]\s+", "• ", text)
    text = re.sub(r"(?m)^\s*\d+\.\s+", "", text)
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
    text = re.sub(r"[*_`>]+", "", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


async def _first_visible(page: Any, selectors: tuple[str, ...]) -> Any:
    for selector in selectors:
        locator = page.locator(selector).first
        if await locator.count() and await locator.is_visible():
            return locator
    return None


async def _first_visible_locator(locator: Any) -> Any:
    for index in range(await locator.count()):
        candidate = locator.nth(index)
        if await candidate.is_visible():
            return candidate
    return None


async def _wait_for_toutiao_cover_entry(
    page: Any,
    *,
    attempts: int = 20,
    delay_ms: int = 250,
) -> Any:
    selectors = (
        ".article-cover-add",
        '.article-cover-images [class*="add"]',
        '.article-cover button:has-text("上传")',
        '.article-cover [aria-label*="上传"], .article-cover [title*="上传"]',
    )
    for attempt in range(max(1, attempts)):
        entry = await _first_visible(page, selectors)
        if entry is not None:
            return entry
        if attempt < attempts - 1:
            await page.wait_for_timeout(delay_ms)
    return None


async def _toutiao_cover_is_configured(page: Any) -> bool:
    configured = await _first_visible(
        page,
        (
            ".article-cover-images img",
            '.article-cover-images [style*="background-image"]',
        ),
    )
    return configured is not None


async def _close_toutiao_assistant(page: Any) -> None:
    close_button = page.locator(".ai-assistant-drawer .close-btn").first
    if await close_button.count() and await close_button.is_visible():
        await close_button.click(timeout=3000)
        await page.wait_for_timeout(250)


async def _type_toutiao_body(page: Any, editor: Any, body_text: str) -> None:
    await editor.click()
    current_text = (await editor.inner_text()).strip()
    if current_text and current_text != "请输入正文":
        await page.keyboard.press("Control+A")
        await page.keyboard.press("Backspace")
    lines = body_text.splitlines()
    for index, line in enumerate(lines):
        if line:
            # ProseMirror ignores Playwright's fill()/insert_text() after its next
            # controlled-state render. Real key events keep the editor state in sync.
            await page.keyboard.type(line)
        if index < len(lines) - 1:
            await page.keyboard.press("Enter")
    await page.wait_for_timeout(700)


def _toutiao_image_paragraph_index(
    *,
    paragraph_count: int,
    image_index: int,
    image_count: int,
) -> int:
    if paragraph_count <= 0:
        return 0
    return max(
        0,
        min(
            paragraph_count - 1,
            int(paragraph_count * (image_index + 1) / (image_count + 1)) - 1,
        ),
    )


async def _position_toutiao_image_cursor(
    editor: Any,
    *,
    image_index: int,
    image_count: int,
) -> None:
    paragraph_count = await editor.locator(":scope > p").count()
    if paragraph_count <= 0:
        await editor.click()
        return
    paragraph_index = _toutiao_image_paragraph_index(
        paragraph_count=paragraph_count,
        image_index=image_index,
        image_count=image_count,
    )
    await editor.evaluate(
        """
        (element, index) => {
          const paragraphs = element.querySelectorAll(":scope > p");
          const paragraph = paragraphs[Math.min(index, paragraphs.length - 1)];
          if (!paragraph) {
            element.focus();
            return;
          }
          const range = document.createRange();
          range.selectNodeContents(paragraph);
          range.collapse(false);
          const selection = window.getSelection();
          selection.removeAllRanges();
          selection.addRange(range);
          element.focus();
        }
        """,
        paragraph_index,
    )


async def _insert_toutiao_body_image(
    page: Any,
    editor: Any,
    image_path: Path,
    *,
    image_index: int,
    image_count: int,
) -> str | None:
    await _position_toutiao_image_cursor(
        editor,
        image_index=image_index,
        image_count=image_count,
    )
    image_button = await _first_visible(
        page,
        (
            '.syl-toolbar-button:has(svg rect[width="16"][height="14"])',
            'button[title*="图片"]',
            '[data-tooltip*="图片"]',
        ),
    )
    if image_button is None:
        return "未找到头条号正文图片上传入口"
    existing_blocks = await editor.locator('[__syl_tag="true"]').count()
    await image_button.click()
    await page.wait_for_timeout(300)
    image_inputs = page.locator('input[type="file"][accept*="image"]')
    if not await image_inputs.count():
        return "头条号正文图片上传组件未加载"
    await image_inputs.first.set_input_files(str(image_path))
    try:
        await page.get_by_text(
            re.compile(r"已上传\s*1\s*张图片"),
        ).wait_for(state="visible", timeout=10_000)
    except Exception:
        await page.wait_for_timeout(2500)
    confirm_upload = await _first_visible_locator(page.get_by_text("确定", exact=True))
    if confirm_upload is None:
        return "头条号正文图片上传后未出现确认按钮"
    await confirm_upload.click()
    for _ in range(10):
        await page.wait_for_timeout(300)
        if await editor.locator('[__syl_tag="true"]').count() > existing_blocks:
            return None
    return "头条号未把企业图片插入文章正文"


async def _upload_toutiao_cover(page: Any, cover_path: Path) -> str | None:
    single_cover = page.get_by_text("单图", exact=True).first
    if not await single_cover.count() or not await single_cover.is_visible():
        return "未找到头条号单图封面选项"
    await single_cover.click()
    if await _toutiao_cover_is_configured(page):
        return None
    add_cover = await _wait_for_toutiao_cover_entry(page)
    if add_cover is None:
        return "未找到头条号封面上传入口"
    await add_cover.click()
    image_input = None
    for _ in range(30):
        image_input = await _first_visible_locator(
            page.locator('input[type="file"][accept*="image"]'),
        )
        if image_input is not None:
            break
        await page.wait_for_timeout(200)
    if image_input is None:
        return "头条号封面上传组件未加载"
    # Only the currently visible local-upload input is wired to the active modal.
    # Other hidden inputs belong to the drag area or a previous material panel.
    await image_input.set_input_files(str(cover_path))
    confirm_upload = await _first_visible_locator(page.get_by_text("确定", exact=True))
    if confirm_upload is None:
        try:
            await page.get_by_text(
                re.compile(r"已上传\s*1\s*张图片"),
            ).wait_for(state="visible", timeout=10_000)
        except Exception:
            return "头条号未完成封面上传"
        confirm_upload = await _first_visible_locator(page.get_by_text("确定", exact=True))
    if confirm_upload is None:
        return "头条号封面上传后未出现确认按钮"
    await confirm_upload.click()
    await page.wait_for_timeout(1000)
    configured_cover = page.locator(".article-cover-images img")
    cover_actions = page.locator(".article-cover-images").get_by_text(
        re.compile(r"编辑|替换"),
    )
    if not await configured_cover.count() and not await cover_actions.count():
        return "头条号未保存文章封面"
    return None


async def _set_toutiao_work_declaration(page: Any) -> None:
    ai_label = page.get_by_text("引用AI", exact=True).first
    ai_checkbox = ai_label.locator(
        'xpath=ancestor::label[1]//input[@type="checkbox"]',
    )
    if (
        await ai_label.count()
        and await ai_label.is_visible()
        and await ai_checkbox.count()
        and not await ai_checkbox.is_checked()
    ):
        await ai_label.click()
        await page.wait_for_timeout(150)

    viewpoint_label = page.get_by_text("个人观点，仅供参考", exact=True).first
    if not await viewpoint_label.count() or not await viewpoint_label.is_visible():
        return
    viewpoint_checkbox = viewpoint_label.locator(
        'xpath=ancestor::label[1]//input[@type="checkbox"]',
    )
    if not await viewpoint_checkbox.count() or not await viewpoint_checkbox.is_checked():
        await viewpoint_label.click()
        await page.wait_for_timeout(250)


async def _wait_for_toutiao_confirm_button(
    page: Any,
    *,
    attempts: int = 30,
    delay_ms: int = 500,
) -> Any:
    """Wait for the asynchronous preview dialog and supported publish labels."""

    button_names = (
        re.compile(r"^\s*确认发布\s*$"),
        re.compile(r"^\s*立即发布\s*$"),
        re.compile(r"^\s*发布\s*$"),
    )
    for attempt in range(max(1, attempts)):
        for name in button_names:
            button = await _first_visible_locator(
                page.get_by_role("button", name=name),
            )
            if button is not None:
                return button
        if attempt < attempts - 1:
            await page.wait_for_timeout(delay_ms)
    return None


async def _toutiao_published_article_urls(context: Any, title: str) -> set[str]:
    manage_page = await context.new_page()
    try:
        await manage_page.goto(
            TOUTIAO_MANAGE_URL,
            wait_until="domcontentloaded",
            timeout=30_000,
        )
        await manage_page.wait_for_timeout(2500)
        urls: set[str] = set()
        article_links = manage_page.locator('a[href*="toutiao.com/item/"]')
        for index in range(await article_links.count()):
            link = article_links.nth(index)
            if not await link.is_visible():
                continue
            if (await link.inner_text()).strip() != title:
                continue
            href = await link.get_attribute("href")
            if href:
                urls.add(href)
        return urls
    finally:
        await manage_page.close()


async def _wait_for_new_toutiao_article_url(
    context: Any,
    *,
    title: str,
    existing_urls: set[str],
) -> str | None:
    for _ in range(4):
        published_urls = await _toutiao_published_article_urls(context, title)
        new_urls = published_urls - existing_urls
        if new_urls:
            return sorted(new_urls)[-1]
        await asyncio.sleep(1500 / 1000)
    return None


def _toutiao_validation_error(body_text: str) -> str | None:
    compact = re.sub(r"\s+", "", body_text)
    checks = (
        ("正文内容不能为空", "头条号未识别到文章正文"),
        ("标题内容不能为空", "头条号未识别到文章标题"),
        ("请输入文章标题", "头条号未识别到文章标题"),
        ("封面上传失败", "头条号封面上传失败"),
        ("图片上传失败", "头条号封面图片上传失败"),
        ("请声明AI生成内容", "头条号要求声明 AI 生成内容"),
        ("AI生成内容未标识", "头条号要求声明 AI 生成内容"),
    )
    for marker, message in checks:
        if marker in compact:
            return message
    missing_match = re.search(r"还需输入(\d+)个字", compact)
    if missing_match:
        return f"头条号标题还需输入 {missing_match.group(1)} 个字"
    return None


def _toutiao_business_result(
    responses: list[dict[str, Any]],
) -> PublishResult | None:
    """Translate Toutiao's HTTP-200 business errors into actionable results."""

    for payload in reversed(responses):
        raw_code = payload.get("err_no", payload.get("code", 0))
        try:
            code = int(raw_code or 0)
        except (TypeError, ValueError):
            code = 0
        if code == 0:
            continue
        message = str(payload.get("message") or payload.get("reason") or "").strip()
        compact = re.sub(r"\s+", "", message)
        if code == 3102 or "禁言" in compact:
            return PublishResult(
                status="rejected",
                error_message=(
                    "头条号账号已被禁言，当前无法发布文章; "
                    "请登录头条号查看账号处罚详情并恢复发布权限"
                ),
            )
        if any(marker in compact for marker in ("安全验证", "验证码", "身份验证")):
            return PublishResult(
                status="needs_verification",
                error_message=f"头条号要求完成安全验证 (平台代码 {code})",
            )
        if code == 7050 or "保存失败" in compact:
            return PublishResult(
                status="failed",
                error_message=(
                    f"头条号草稿保存失败 (平台代码 {code}); 请登录头条号检查账号状态或发布权限"
                ),
            )
        return PublishResult(
            status="rejected",
            error_message=(f"头条号拒绝了本次发布 (平台代码 {code}): {message or '未知原因'}")[
                :500
            ],
        )
    return None


async def publish_to_toutiao(
    settings: Settings,
    *,
    account_id: UUID | None = None,
    document_id: UUID,
    version_id: UUID,
    title: str,
    body_markdown: str,
    cover_path: Path,
    body_image_paths: list[Path] | None = None,
) -> PublishResult:
    if settings.publishing_execution_mode == "fixed_mock":
        return PublishResult(
            status="published",
            public_url=f"https://www.toutiao.com/article/mock-{version_id.hex}",
            platform_post_id=f"mock-{version_id.hex}",
        )
    try:
        from playwright.async_api import async_playwright
    except ImportError:
        return PublishResult(status="failed", error_message="自动发布组件未安装")
    try:
        async with async_playwright() as playwright:
            context = await playwright.chromium.launch_persistent_context(
                str(_browser_profile_path(settings, "toutiao", account_id)),
                executable_path=str(_browser_executable(settings)),
                headless=True,
                args=["--disable-blink-features=AutomationControlled"],
            )
            try:
                page = context.pages[0] if context.pages else await context.new_page()
                publish_responses: list[dict[str, Any]] = []

                async def capture_publish_response(response: Any) -> None:
                    if "/mp/agw/article/publish" not in response.url:
                        return
                    try:
                        payload = await response.json()
                    except Exception:
                        return
                    if isinstance(payload, dict):
                        publish_responses.append(payload)

                page.on("response", capture_publish_response)
                await page.goto(TOUTIAO_LOGIN_URL, wait_until="domcontentloaded", timeout=30_000)
                await page.wait_for_timeout(1500)
                if await _confirm_toutiao_logged_out(page):
                    return PublishResult(
                        status="needs_login",
                        error_message="头条号登录已失效，请到渠道配置重新登录",
                    )
                body_text = await page.locator("body").inner_text(timeout=5000)
                if any(word in body_text for word in ("安全验证", "请完成验证", "验证码")):
                    return PublishResult(
                        status="needs_verification",
                        error_message="头条号要求完成安全验证，请打开登录窗口处理",
                    )
                existing_public_urls = await _toutiao_published_article_urls(
                    context,
                    title.strip()[:30],
                )
                await _close_toutiao_assistant(page)
                title_input = await _first_visible(
                    page,
                    (
                        'textarea[placeholder*="标题"]',
                        'input[placeholder*="标题"]',
                        '[class*="title"] textarea',
                        '[class*="title"] input',
                    ),
                )
                editor = await _first_visible(
                    page,
                    (
                        ".ProseMirror[contenteditable=true]",
                        "textarea[placeholder*='正文']",
                    ),
                )
                if title_input is None or editor is None:
                    return PublishResult(
                        status="failed",
                        error_message="头条号发布页结构已变化，请更新自动发布适配器",
                    )
                normalized_title = title.strip()[:30]
                normalized_body = _markdown_to_plain_text(body_markdown)
                if len(normalized_title) < 2:
                    return PublishResult(
                        status="failed",
                        error_message="头条号标题至少需要 2 个字",
                    )
                if len(normalized_body) < 20:
                    return PublishResult(
                        status="failed",
                        error_message="文章正文过短，暂不能发布到头条号",
                    )
                await title_input.fill(normalized_title)
                await page.wait_for_timeout(350)
                await _type_toutiao_body(page, editor, normalized_body)
                editor_text = (await editor.inner_text()).strip()
                if editor_text == "请输入正文" or len(editor_text) < 20:
                    return PublishResult(
                        status="failed",
                        error_message="头条号未识别到文章正文，请重试",
                    )
                resolved_body_images = body_image_paths or []
                for image_index, image_path in enumerate(resolved_body_images):
                    image_error = await _insert_toutiao_body_image(
                        page,
                        editor,
                        image_path,
                        image_index=image_index,
                        image_count=len(resolved_body_images),
                    )
                    if image_error is not None:
                        return PublishResult(status="failed", error_message=image_error)
                cover_error = await _upload_toutiao_cover(page, cover_path)
                if cover_error is not None:
                    return PublishResult(status="failed", error_message=cover_error)
                await _set_toutiao_work_declaration(page)
                page_text = await page.locator("body").inner_text(timeout=5000)
                validation_error = _toutiao_validation_error(page_text)
                if validation_error is not None:
                    return PublishResult(
                        status="failed",
                        error_message=validation_error,
                    )
                preview_button = page.get_by_role(
                    "button",
                    name=re.compile(r"^\s*预览并发布\s*$"),
                ).last
                if not await preview_button.count():
                    return PublishResult(
                        status="failed",
                        error_message="头条号发布流程已变化，未找到“预览并发布”按钮",
                    )
                if not await preview_button.is_enabled():
                    return PublishResult(
                        status="failed",
                        error_message="头条号发布前校验未通过，请检查标题、正文和封面",
                    )
                await preview_button.click()
                confirm_button = await _wait_for_toutiao_confirm_button(page)
                if confirm_button is None:
                    preview_text = await page.locator("body").inner_text(timeout=5000)
                    preview_error = _toutiao_validation_error(preview_text)
                    return PublishResult(
                        status="failed",
                        error_message=preview_error
                        or "头条号未进入确认发布步骤，请登录平台检查页面提示",
                    )
                for _ in range(20):
                    if await confirm_button.is_enabled():
                        break
                    await page.wait_for_timeout(250)
                else:
                    return PublishResult(
                        status="failed",
                        error_message="头条号确认发布按钮不可用，请登录平台检查页面提示",
                    )
                await confirm_button.click()
                await page.wait_for_timeout(4000)
                business_result = _toutiao_business_result(publish_responses)
                if business_result is not None:
                    return business_result
                result_text = await page.locator("body").inner_text(timeout=5000)
                if any(word in result_text for word in ("安全验证", "请完成验证", "验证码")):
                    return PublishResult(
                        status="needs_verification",
                        error_message="发布前需要完成头条号安全验证",
                    )
                if any(word in result_text for word in ("审核不通过", "发布失败", "内容违规")):
                    return PublishResult(
                        status="rejected",
                        error_message="头条号拒绝了本次发布，请登录平台查看具体原因",
                    )
                public_url = await _wait_for_new_toutiao_article_url(
                    context,
                    title=normalized_title,
                    existing_urls=existing_public_urls,
                )
                success = (
                    any(word in result_text for word in ("发布成功", "审核中", "已提交"))
                    or (
                        "/graphic/publish" not in page.url.casefold()
                        and "toutiao.com" in page.url.casefold()
                    )
                    or public_url is not None
                )
                if not success:
                    return PublishResult(
                        status="failed",
                        error_message="未检测到头条号发布成功回执，请登录平台核对",
                    )
                if public_url is None and re.search(
                    r"www\.toutiao\.com/(?:article|item)/",
                    page.url,
                ):
                    public_url = page.url
                platform_post_id = None
                match = re.search(
                    r"(?:article|item)/([0-9A-Za-z_-]+)",
                    public_url or page.url,
                )
                if match:
                    platform_post_id = match.group(1)
                return PublishResult(
                    status="published",
                    public_url=public_url,
                    platform_post_id=platform_post_id,
                )
            finally:
                await context.close()
    except Exception as error:
        return PublishResult(status="failed", error_message=str(error)[:500])


GENERIC_PUBLISH_SELECTORS: dict[str, dict[str, tuple[str, ...]]] = {
    "baijia": {
        "title": (
            'input[placeholder*="标题"]',
            'textarea[placeholder*="标题"]',
            '[class*="title"] input',
        ),
        "editor": (
            '.ProseMirror[contenteditable="true"]',
            '.ql-editor[contenteditable="true"]',
            '[class*="editor"] [contenteditable="true"]',
            'textarea[placeholder*="正文"]',
        ),
        "cover_trigger": (
            '[class*="cover"] button:has-text("上传")',
            '[class*="cover"] [class*="upload"]',
            '[class*="cover"] [aria-label*="上传"]',
        ),
        "cover_input": (
            '[class*="cover"] input[type="file"][accept*="image"]',
            '[role="dialog"] input[type="file"][accept*="image"]',
            '.ant-modal:visible input[type="file"][accept*="image"]',
        ),
        "cover_preview": (
            '[class*="cover"] img',
            '[class*="cover"] [style*="background-image"]',
        ),
    },
    "netease": {
        "title": (
            'textarea.netease-textarea[placeholder*="请输入标题"]',
            'textarea[placeholder*="请输入标题 (5~64个字)"]',
            '.article-post__content-editor .title-filed textarea[placeholder*="请输入标题"]',
            '.article-post__content-editor textarea[placeholder*="请输入标题"]',
            '.article-post__content-editor input[placeholder*="请输入标题"]',
        ),
        "editor": (
            '.public-DraftEditor-content[role="textbox"][contenteditable="true"]',
            '[role="textbox"][contenteditable="true"][aria-describedby]',
            '.article-post__content-editor .public-DraftEditor-content[contenteditable="true"]',
            '.article-post__content-editor [role="textbox"][contenteditable="true"]',
            '.article-post__content-editor [contenteditable="true"][data-contents="true"]',
        ),
        "cover_trigger": (
            '[class*="cover-pic__single__content-btn"]:has-text("上传图片")',
            '[class*="cover-pic__single__content__choose"]:has-text("上传图片")',
        ),
        "cover_input": (
            '.picture-adder:visible input[type="file"][accept*="image"]',
            '[role="dialog"]:visible input[type="file"][accept*="image"]',
        ),
        "cover_preview": (
            '[class*="cover-pic__single__content__choose"] img',
            '[class*="cover-pic__single"] img',
        ),
    },
    "sohu": {
        "title": (
            'input[placeholder*="标题"]',
            'textarea[placeholder*="标题"]',
            '[class*="title"] input',
        ),
        "editor": (
            '.ql-editor[contenteditable="true"]',
            '.ProseMirror[contenteditable="true"]',
            '[contenteditable="true"]',
            'textarea[placeholder*="正文"]',
        ),
    },
    "penguin": {
        "title": (
            'input[placeholder*="标题"]',
            'textarea[placeholder*="标题"]',
            '[class*="title"] input',
            '[class*="title"] textarea',
        ),
        "editor": (
            '.ql-editor[contenteditable="true"]',
            '.ProseMirror[contenteditable="true"]',
            '[class*="editor"] [contenteditable="true"]',
            '[contenteditable="true"][role="textbox"]',
        ),
        "cover_trigger": (
            '[class*="cover"]:has-text("选择封面")',
            '[class*="cover"] button:has-text("选择")',
            'button:has-text("设置封面")',
            'button:has-text("从正文选择")',
        ),
        "cover_input": (),
        "cover_preview": (
            '[class*="cover"] img',
            '[class*="cover"] [style*="background-image"]',
        ),
    },
    "yidian": {
        # 真实一点号编辑器选择器将在首个已登录账号的只填充验证后固化，
        # 这些候选只用于受控验证，不作为自动提交依据。
        "title": (
            'input[placeholder*="标题"]',
            'textarea[placeholder*="标题"]',
            '[class*="title"] input',
            '[class*="title"] textarea',
        ),
        "editor": (
            '.ql-editor[contenteditable="true"]',
            '.ProseMirror[contenteditable="true"]',
            '[class*="editor"] [contenteditable="true"]',
            '[contenteditable="true"][role="textbox"]',
        ),
        "cover_trigger": (
            '[class*="cover"] button:has-text("上传")',
            '[class*="cover"] [class*="upload"]',
            'button:has-text("设置封面")',
        ),
        "cover_input": (
            '[class*="cover"] input[type="file"][accept*="image"]',
            '[role="dialog"] input[type="file"][accept*="image"]',
        ),
        "cover_preview": (
            '[class*="cover"] img',
            '[class*="cover"] [style*="background-image"]',
        ),
    },
}


PLATFORM_PUBLISH_BUTTON_LABELS: dict[str, tuple[str, ...]] = {
    "baijia": ("发布", "立即发布", "提交审核"),
    "netease": ("发布", "立即发布", "提交审核"),
    "penguin": ("发布", "立即发布", "提交审核"),
    "yidian": ("发布", "立即发布", "提交审核"),
}

PLATFORM_CONFIRMATION_LABELS: dict[str, tuple[str, ...]] = {
    "baijia": ("确认", "确认发布", "立即发布", "提交审核"),
    "netease": ("确认发布", "立即发布", "提交审核"),
    "sohu": ("确认发布", "立即发布", "确定"),
    "penguin": ("确认发布", "立即发布", "提交审核", "确定"),
    "yidian": ("确认发布", "立即发布", "提交审核", "确定"),
}

PLATFORM_PENDING_REVIEW_MARKERS: dict[str, tuple[str, ...]] = {
    "baijia": ("提交成功", "审核中", "已提交", "等待审核", "待审核"),
    "netease": (
        NETEASE_SUCCESS_RECEIPT,
        "发布成功",
        "提交成功",
        "审核中",
        "已提交",
        "等待审核",
        "待审核",
    ),
    "sohu": ("提交成功", "审核中", "已提交", "等待审核", "待审核"),
    "penguin": ("发布成功", "提交成功", "审核中", "已提交", "等待审核", "待审核"),
    "yidian": ("发布成功", "提交成功", "审核中", "已提交", "等待审核", "待审核"),
}

PLATFORM_REJECTION_MARKERS = (
    "审核不通过",
    "审核未通过",
    "未通过",
    "已驳回",
    "发布失败",
    "提交失败",
    "内容违规",
    "处理失败",
    "已下线",
    "作者下线",
    "已删除",
)

PLATFORM_VALIDATION_MARKERS: dict[str, tuple[tuple[str, str], ...]] = {
    "baijia": (
        ("请输入标题", "百家号未识别到文章标题"),
        ("标题不能为空", "百家号未识别到文章标题"),
        ("请输入正文", "百家号未识别到文章正文"),
        ("正文不能为空", "百家号未识别到文章正文"),
        ("请选择封面", "百家号文章封面未设置"),
        ("封面上传失败", "百家号文章封面上传失败"),
        ("请选择分类", "百家号要求选择文章分类"),
    ),
    "netease": (
        ("请输入标题", "网易号未识别到文章标题"),
        ("标题不能为空", "网易号未识别到文章标题"),
        ("请输入正文", "网易号未识别到文章正文"),
        ("正文不能为空", "网易号未识别到文章正文"),
        ("请选择封面", "网易号文章封面未设置"),
        ("封面上传失败", "网易号文章封面上传失败"),
        ("请选择分类", "网易号要求选择文章分类"),
        ("图片尺寸小于", "网易号文章图片尺寸不符合要求"),
        ("请完善封面设置", "网易号文章封面未设置"),
        ("标题内容可能涉嫌标题党", "网易号判断标题存在标题党风险，请调整标题"),
    ),
    "sohu": (
        ("请输入标题", "搜狐号未识别到文章标题"),
        ("请输入正文", "搜狐号未识别到文章正文"),
        ("请选择封面", "搜狐号文章封面未设置"),
        ("请选择属性", "搜狐号要求选择文章属性"),
    ),
    "penguin": (
        ("请输入标题", "企鹅号未识别到文章标题"),
        ("标题不能为空", "企鹅号未识别到文章标题"),
        ("请输入正文", "企鹅号未识别到文章正文"),
        ("正文不能为空", "企鹅号未识别到文章正文"),
        ("请选择封面", "企鹅号文章封面未设置"),
        ("封面上传失败", "企鹅号文章封面设置失败"),
        ("请声明AI", "企鹅号要求声明AI生成内容"),
        ("今日发布数量已达", "企鹅号账号今日发布数量已达上限"),
    ),
    "yidian": (
        ("请输入标题", "一点号未识别到文章标题"),
        ("标题不能为空", "一点号未识别到文章标题"),
        ("请输入正文", "一点号未识别到文章正文"),
        ("正文不能为空", "一点号未识别到文章正文"),
        ("请选择封面", "一点号文章封面未设置"),
        ("封面上传失败", "一点号文章封面上传失败"),
        ("请选择分类", "一点号要求选择文章分类"),
        ("请标注AI", "一点号要求如实声明AI生成内容"),
    ),
}


async def _fill_generic_editor(editor: Any, body_text: str) -> None:
    tag_name = (await editor.evaluate("element => element.tagName")).casefold()
    if tag_name in {"textarea", "input"}:
        await editor.fill(body_text)
        return
    await editor.click()
    await editor.press("Control+A")
    await editor.press("Backspace")
    await editor.press_sequentially(body_text, delay=0)


async def _ensure_penguin_workspace(page: Any, *, target: Literal["editor", "manage"]) -> None:
    """Navigate from the signed-in Penguin dashboard using visible product actions.

    Penguin currently redirects the public root to the account workspace and its
    internal routes may change.  Text navigation is deliberately used only when
    the requested workspace is not already visible.
    """

    selectors = GENERIC_PUBLISH_SELECTORS["penguin"]
    labels: tuple[str, ...]
    if target == "editor":
        if (
            await _first_visible(page, selectors["title"]) is not None
            and await _first_visible(page, selectors["editor"]) is not None
        ):
            return
        labels = ("创作", "发布", "发图文", "写文章", "发布文章")
    else:
        if await page.get_by_text("内容管理", exact=True).count():
            entry = await _first_visible_locator(page.get_by_text("内容管理", exact=True))
            if entry is None:
                return
        labels = ("内容管理", "作品管理", "我的内容", "图文管理")

    for label in labels:
        entry = await _first_visible_locator(page.get_by_text(label, exact=True))
        if entry is None:
            continue
        await entry.click()
        await page.wait_for_timeout(700)
        if target == "editor":
            if (
                await _first_visible(page, selectors["title"]) is not None
                and await _first_visible(page, selectors["editor"]) is not None
            ):
                return
        elif label in {"内容管理", "作品管理", "我的内容", "图文管理"}:
            return


async def _wait_for_penguin_editors(page: Any) -> tuple[Any | None, Any | None]:
    await _ensure_penguin_workspace(page, target="editor")
    selectors = GENERIC_PUBLISH_SELECTORS["penguin"]
    title_input = None
    body_editor = None
    for _ in range(80):
        title_input = await _first_visible(page, selectors["title"])
        body_editor = await _first_visible(page, selectors["editor"])
        if title_input is not None and body_editor is not None:
            return title_input, body_editor
        await page.wait_for_timeout(250)
    return title_input, body_editor


async def _penguin_image_entry(page: Any) -> Any | None:
    return await _first_visible(
        page,
        (
            '[title*="图片"]',
            '[aria-label*="图片"]',
            '[data-action*="image"]',
            '[data-type*="image"]',
            'button:has-text("图片")',
            '[role="button"]:has-text("图片")',
        ),
    )


async def _insert_penguin_body_images(
    page: Any,
    editor: Any,
    body_image_paths: list[Path] | None,
) -> str | None:
    available = [
        path
        for path in list(body_image_paths or [])[:PENGUIN_BODY_IMAGE_COUNT]
        if await asyncio.to_thread(path.is_file)
    ]
    if len(available) < PENGUIN_BODY_IMAGE_COUNT:
        return f"企鹅号发布需要 {PENGUIN_BODY_IMAGE_COUNT} 张真实企业图片"

    for image_index, image_path in enumerate(available):
        await _position_toutiao_image_cursor(
            editor,
            image_index=image_index,
            image_count=len(available),
        )
        entry = await _penguin_image_entry(page)
        if entry is None:
            return "企鹅号发布页结构已变化，未找到正文图片入口"
        existing_count = await editor.locator("img").count()
        await entry.click()
        await page.wait_for_timeout(350)
        file_input = None
        for scope_selector in (
            '[role="dialog"]:visible',
            '[class*="modal"]:visible',
            '[class*="dialog"]:visible',
            "body",
        ):
            scope = page.locator(scope_selector).last
            if not await scope.count():
                continue
            candidates = scope.locator('input[type="file"][accept*="image"]')
            if await candidates.count():
                file_input = candidates.last
                break
        if file_input is None:
            return "企鹅号正文图片上传组件未加载"
        await file_input.set_input_files(str(image_path))
        await page.wait_for_timeout(500)
        confirmation = await _wait_for_generic_confirmation_button(
            page,
            "penguin",
            attempts=8,
        )
        if confirmation is not None and await confirmation.is_enabled():
            await confirmation.click()
        for _ in range(40):
            if await editor.locator("img").count() > existing_count:
                break
            await page.wait_for_timeout(250)
        else:
            return "企鹅号未把企业图片插入文章正文"
    return None


async def _select_penguin_cover_from_body(page: Any) -> str | None:
    preview = await _first_visible(
        page,
        GENERIC_PUBLISH_SELECTORS["penguin"]["cover_preview"],
    )
    if preview is not None:
        return None
    single_cover = await _first_visible_locator(page.get_by_text("单图", exact=True))
    if single_cover is not None:
        await single_cover.click()
    trigger = await _first_visible(
        page,
        GENERIC_PUBLISH_SELECTORS["penguin"]["cover_trigger"],
    )
    if trigger is None:
        return "企鹅号发布页结构已变化，未找到从正文选择封面的入口"
    await trigger.click()
    await page.wait_for_timeout(350)
    dialog = page.locator(
        '[role="dialog"]:visible, [class*="modal"]:visible, [class*="dialog"]:visible',
    ).last
    if not await dialog.count() or not await dialog.is_visible():
        return "企鹅号封面选择窗口未打开"
    candidates = dialog.locator('img:not([src*="data:image/svg"])')
    selected = await _first_visible_locator(candidates)
    if selected is None:
        return "企鹅号没有从正文提取到可用封面候选图"
    await selected.click()
    confirm = await _wait_for_generic_confirmation_button(page, "penguin")
    if confirm is not None and await confirm.is_enabled():
        await confirm.click()
    for _ in range(30):
        if (
            await _first_visible(
                page,
                GENERIC_PUBLISH_SELECTORS["penguin"]["cover_preview"],
            )
            is not None
        ):
            return None
        await page.wait_for_timeout(250)
    return "企鹅号未把正文图片设置为文章封面"


async def _set_penguin_ai_declaration(page: Any) -> str | None:
    for label in ("使用AI生成内容", "内容由AI生成", "AI生成", "包含AI创作内容"):
        candidate = page.get_by_text(label, exact=True).first
        if not await candidate.count() or not await candidate.is_visible():
            continue
        checkbox = candidate.locator("xpath=ancestor::label[1]").locator(
            'input[type="checkbox"]',
        )
        if await checkbox.count():
            if not await checkbox.is_checked():
                await candidate.locator("xpath=ancestor::label[1]").click(
                    force=True,
                    timeout=5000,
                )
                await page.wait_for_timeout(250)
            if await checkbox.is_checked():
                return None
        else:
            await candidate.click()
            return None
    return "企鹅号未找到AI生成内容声明，已停止发布以避免漏标"


async def _fill_netease_editor(page: Any, editor: Any, body_text: str) -> None:
    """Type through Draft.js so its controlled state retains every paragraph."""

    await editor.click()
    await page.keyboard.press("Control+A")
    await page.keyboard.press("Backspace")
    lines = body_text.splitlines()
    for index, line in enumerate(lines):
        if line:
            await page.keyboard.type(line)
        if index < len(lines) - 1:
            await page.keyboard.press("Enter")
    await page.wait_for_timeout(700)


def _baijia_title_error(title: str) -> str | None:
    length = len(title.strip())
    if length < 2:
        return "百家号标题至少需要 2 个字"
    if length > BAIJIA_TITLE_MAX_CHARS:
        return f"百家号标题最多支持 {BAIJIA_TITLE_MAX_CHARS} 个字"
    return None


def _netease_title_error(title: str) -> str | None:
    length = len(title.strip())
    if length < 5:
        return "网易号标题至少需要 5 个字"
    if length > NETEASE_TITLE_MAX_CHARS:
        return f"网易号标题最多支持 {NETEASE_TITLE_MAX_CHARS} 个字"
    return None


def _publishing_daily_limit_error(channel_id: str, submitted_count: int) -> str | None:
    spec = get_publishing_platform_spec(channel_id)
    limit = spec.daily_publication_limit if spec is not None else None
    if limit is None or submitted_count < limit:
        return None
    return (
        f"{PUBLISHING_PLATFORMS_BY_ID[channel_id]['name']}账号今日已提交 "
        f"{submitted_count} 篇文章，达到平台每日上限"
    )


def _platform_submission_title(channel_id: str, title: str) -> str:
    stripped = title.strip()
    if channel_id == "baijia":
        return stripped[:BAIJIA_TITLE_MAX_CHARS]
    if channel_id == "netease":
        # The adapter validates the live limit explicitly.  Silent truncation
        # changes the semantic title and breaks exact-title result matching.
        return stripped
    if channel_id == "penguin":
        return stripped
    return stripped[:30]


def _netease_publish_prerequisite_error(page_text: str) -> str | None:
    compact = re.sub(r"\s+", "", page_text)
    checks = (
        ("账号被禁言", "网易号账号已被禁言，当前无法发布文章"),
        ("您的账号已被永久禁言", "网易号账号已被永久禁言，当前无法发布文章"),
        ("您的账号已被下线", "网易号账号已被下线，当前无法发布文章"),
        ("您的账号未上线", "网易号账号尚未上线，当前无法发布文章"),
        ("请先通过实名认证再发布内容", "网易号账号需要先完成实名认证"),
        ("今日发布数量已达最大值", "网易号账号今日发布数量已达上限"),
    )
    for marker, message in checks:
        if marker in compact:
            return message
    return None


async def _set_labeled_checkbox(page: Any, label_text: str, checked: bool) -> bool:
    label = page.get_by_text(label_text, exact=True).first
    if not await label.count() or not await label.is_visible():
        return False
    checkbox = label.locator("xpath=ancestor::label[1]").locator('input[type="checkbox"]')
    if not await checkbox.count():
        return False
    if await checkbox.is_checked() != checked:
        # This is a controlled React checkbox: mutating the native input is
        # immediately reverted.  Dispatch the platform's label click while
        # bypassing transient helper overlays, then verify React's final state.
        await label.locator("xpath=ancestor::label[1]").click(
            force=True,
            timeout=5000,
        )
        await page.wait_for_timeout(250)
    return bool(await checkbox.is_checked()) == checked


async def _set_baijia_work_settings(page: Any) -> str | None:
    if not await _set_labeled_checkbox(page, "采用AI生成内容", True):
        return "百家号未找到“采用AI生成内容”声明，请检查发布页面"
    # These optional derivatives change the submitted product, so keep them off
    # unless the operator explicitly asks for them.
    await _set_labeled_checkbox(page, "自动生成播客", False)
    await _set_labeled_checkbox(page, "图文转动态", False)
    return None


async def _wait_for_baijia_editors(page: Any) -> tuple[Any | None, Any | None]:
    title_input = None
    body_editor = None
    # The UEditor iframe is loaded after the surrounding React application.  A
    # real logged-in page currently takes about eight seconds on a cold start,
    # so keep a bounded twenty-second readiness window instead of treating the
    # intermediate skeleton as a selector change.
    for _ in range(80):
        title_input = await _first_visible_locator(
            page.locator(
                '[data-testid="news-title-input"] [contenteditable="true"]',
            ),
        )
        body_editor = await _first_visible_locator(
            page.frame_locator("#ueditor_0").locator('body[contenteditable="true"]'),
        )
        if title_input is not None and body_editor is not None:
            return title_input, body_editor
        await page.wait_for_timeout(250)
    return title_input, body_editor


async def _wait_for_netease_editors(page: Any) -> tuple[Any | None, Any | None]:
    """Wait for the live NetEase article composer, not a generic editable node."""

    selectors = GENERIC_PUBLISH_SELECTORS["netease"]
    title_input = None
    body_editor = None
    for _ in range(80):
        title_input = await _first_visible(page, selectors["title"])
        body_editor = await _first_visible(page, selectors["editor"])
        if title_input is not None and body_editor is not None:
            return title_input, body_editor
        await page.wait_for_timeout(250)
    return title_input, body_editor


async def _position_netease_image_cursor(
    editor: Any,
    *,
    image_index: int,
    image_count: int,
) -> None:
    await editor.evaluate(
        """
        (element, position) => {
          const blocks = Array.from(
            element.querySelectorAll('[data-block="true"], p')
          ).filter(block => (block.innerText || '').trim().length > 0);
          if (!blocks.length) {
            element.focus();
            return;
          }
          const ratio = (position.imageIndex + 1) / (position.imageCount + 1);
          const index = Math.max(
            0,
            Math.min(blocks.length - 1, Math.floor(blocks.length * ratio) - 1)
          );
          const block = blocks[index];
          const range = document.createRange();
          range.selectNodeContents(block);
          range.collapse(false);
          const selection = window.getSelection();
          selection.removeAllRanges();
          selection.addRange(range);
          element.focus();
        }
        """,
        {"imageIndex": image_index, "imageCount": image_count},
    )


async def _last_visible_netease_dialog(page: Any) -> Any | None:
    # The live composer nests several elements whose class names also contain
    # "modal".  Always bind uploads to the outer picture-adder first; otherwise
    # a footer/body child can be mistaken for the dialog and hide its file input.
    picture_adders = page.locator(".picture-adder:visible")
    for index in range(await picture_adders.count() - 1, -1, -1):
        dialog = picture_adders.nth(index)
        if await dialog.is_visible():
            return dialog
    dialogs = page.locator(
        '[role="dialog"]:visible, .ne-modal:visible, [class*="dialog"]:visible',
    )
    for index in range(await dialogs.count() - 1, -1, -1):
        dialog = dialogs.nth(index)
        if await dialog.is_visible():
            return dialog
    return None


async def _netease_image_toolbar_entry(page: Any) -> Any | None:
    # Current NetEase composer renders the image action as an icon-only button.
    # Its SVG asset name is stable while the button has no text/title/aria label.
    icon_entry = await _first_visible_locator(
        page.locator(
            'button.rich-editor-panel-item:has(img[src*="icon_image."])',
        ),
    )
    if icon_entry is not None:
        return icon_entry
    toolbar = page.locator(".post-header.fixed-header, .post-header__nav").first
    candidates = (
        '[title*="图片"]',
        '[aria-label*="图片"]',
        '[data-controller="image"]',
        '[data-type="image"]',
        'button:has-text("图片")',
        '[role="button"]:has-text("图片")',
    )
    if await toolbar.count() and await toolbar.is_visible():
        for selector in candidates:
            entry = await _first_visible_locator(toolbar.locator(selector))
            if entry is not None:
                return entry
    titled = page.get_by_title(re.compile(r"(?:插入|上传)?图片"))
    return await _first_visible_locator(titled)


async def _insert_netease_body_images(
    page: Any,
    editor: Any,
    *,
    cover_path: Path,
    body_image_paths: list[Path] | None,
) -> str | None:
    # NetEase builds single-cover candidates from images already present in the
    # article.  The live publishing assistant expects at least three body
    # images, so insert the prepared editorial cover followed by two enterprise
    # photos.  The fixed three-image contract avoids both under-filled articles
    # and decorative image flooding.
    candidates = [cover_path, *(body_image_paths or [])]
    available: list[Path] = []
    for image_path in candidates:
        if image_path in available:
            continue
        if await asyncio.to_thread(image_path.is_file):
            available.append(image_path)
        if len(available) == NETEASE_BODY_IMAGE_COUNT:
            break
    minimum_images = PUBLISHING_PLATFORM_SPECS["netease"].image.minimum_body_images
    if len(available) < minimum_images:
        return f"网易号发布需要 {minimum_images} 张正文图片，当前可用图片不足"

    for image_index, image_path in enumerate(available):
        await _position_netease_image_cursor(
            editor,
            image_index=image_index,
            image_count=len(available),
        )
        image_entry = await _netease_image_toolbar_entry(page)
        if image_entry is None:
            return "未找到网易号正文图片上传入口"
        existing_count = await editor.locator("img").count()
        await image_entry.click()
        await page.wait_for_timeout(350)
        dialog = await _last_visible_netease_dialog(page)
        if dialog is None:
            return "网易号正文图片上传窗口未打开"
        file_inputs = dialog.locator('input[type="file"][accept*="image"]')
        if not await file_inputs.count():
            return "网易号正文图片上传组件未加载"
        await file_inputs.last.set_input_files(str(image_path))
        confirm = await _first_visible_locator(dialog.locator(".s-confirm-btn"))
        if confirm is None:
            confirm = await _first_visible_locator(
                dialog.get_by_role(
                    "button",
                    name=re.compile(r"^\s*确定(?:\(\d+\))?\s*$"),
                ),
            )
        for _ in range(80):
            if confirm is not None and await confirm.is_enabled():
                break
            await page.wait_for_timeout(250)
            if confirm is None:
                confirm = await _first_visible_locator(dialog.locator(".s-confirm-btn"))
        else:
            return "网易号正文图片上传后未进入可确认状态"
        await confirm.click()
        for _ in range(60):
            await page.wait_for_timeout(250)
            if await editor.locator("img").count() > existing_count:
                break
        else:
            return "网易号未把图片插入文章正文"
    return None


async def _upload_netease_cover(page: Any) -> str | None:
    existing = await _first_visible(
        page,
        GENERIC_PUBLISH_SELECTORS["netease"]["cover_preview"],
    )
    if existing is not None:
        return None

    cover_area = page.locator('.article-post__content-other [class*="cover-pic__cover"]').first
    single_mode = (
        cover_area.get_by_text("单图", exact=True)
        if await cover_area.count()
        else page.get_by_text("单图", exact=True)
    )
    single_mode = await _first_visible_locator(single_mode)
    if single_mode is None:
        return "网易号发布页结构已变化，未找到单图封面模式"
    await single_mode.click()
    await page.wait_for_timeout(300)

    trigger = await _first_visible(
        page,
        GENERIC_PUBLISH_SELECTORS["netease"]["cover_trigger"],
    )
    if trigger is None:
        return "网易号发布页结构已变化，未找到封面选择入口"
    await trigger.click()
    await page.wait_for_timeout(350)
    dialog = await _last_visible_netease_dialog(page)
    if dialog is None:
        return "网易号封面选择窗口未打开"

    selected = False
    images = dialog.locator("img[src]")
    for index in range(await images.count()):
        image = images.nth(index)
        if not await image.is_visible():
            continue
        box = await image.bounding_box()
        if box and box["width"] >= 80 and box["height"] >= 60:
            item = image.locator("xpath=ancestor::*[contains(@class, 'cover-picture__item')][1]")
            if await item.count() and await item.is_visible():
                await item.click()
            else:
                await image.click()
            selected = True
            break
    if not selected:
        return "网易号封面选择窗口中没有可用的正文图片"

    confirm = await _first_visible_locator(
        dialog.get_by_role(
            "button",
            name=re.compile(r"^\s*(?:确定|完成|保存)(?:\(\d+\))?\s*$"),
        ),
    )
    if confirm is None:
        confirm = await _first_visible_locator(dialog.locator(".s-confirm-btn"))
    if confirm is None:
        confirm = await _first_visible_locator(
            dialog.locator(".cover-picture__footer > div").filter(has_text="确认"),
        )
    for _ in range(40):
        if confirm is not None and await confirm.is_enabled():
            classes = str(await confirm.get_attribute("class") or "").split()
            if "disabled" not in classes:
                break
        await page.wait_for_timeout(250)
    else:
        return "网易号封面选择后未进入可确认状态"
    await confirm.click()
    for _ in range(40):
        await page.wait_for_timeout(250)
        if (
            await _first_visible(
                page,
                GENERIC_PUBLISH_SELECTORS["netease"]["cover_preview"],
            )
            is not None
        ):
            return None
    return "网易号未把已选图片设置为文章封面"


async def _set_netease_optional_statement(page: Any) -> None:
    # The ordinary article form exposes an optional content statement.  Select
    # non-fiction only when that exact option is rendered; never claim
    # originality, first publication, signing status or an AI label on behalf
    # of the operator.
    non_fiction = await _first_visible_locator(
        page.get_by_text("本文为非虚构内容", exact=True),
    )
    if non_fiction is not None:
        await non_fiction.click()
        await page.wait_for_timeout(200)


async def _baijia_modal(page: Any, marker: str) -> Any | None:
    dialogs = page.locator('[role="dialog"]')
    for index in range(await dialogs.count() - 1, -1, -1):
        dialog = dialogs.nth(index)
        if not await dialog.is_visible():
            continue
        if marker in await dialog.inner_text():
            return dialog
    return None


async def _insert_baijia_body_images(
    page: Any,
    editor: Any,
    body_image_paths: list[Path] | None,
) -> str | None:
    images = list(body_image_paths or [])[:BAIJIA_BODY_IMAGE_COUNT]
    for image_index, image_path in enumerate(images):
        if not await asyncio.to_thread(image_path.is_file):
            return "百家号正文图片文件不存在"
        await _position_toutiao_image_cursor(
            editor,
            image_index=image_index,
            image_count=len(images),
        )
        image_entry = await _first_visible_locator(
            page.locator('[data-function="insertimage"]'),
        )
        if image_entry is None:
            return "未找到百家号正文图片上传入口"
        existing_count = await editor.locator("img").count()
        await image_entry.click()
        await page.wait_for_timeout(350)
        dialog = await _baijia_modal(page, "本地图片")
        if dialog is None:
            return "百家号正文图片上传窗口未打开"
        file_input = dialog.locator(
            'input[type="file"][name="media"][accept*="image"]',
        ).first
        if not await file_input.count():
            return "百家号正文图片上传组件未加载"
        await file_input.set_input_files(str(image_path))
        confirm = dialog.get_by_role("button", name="确认", exact=True)
        if not await confirm.count():
            confirm = dialog.get_by_text("确认", exact=True)
        for _ in range(40):
            if await confirm.count() and await confirm.is_visible() and await confirm.is_enabled():
                break
            await page.wait_for_timeout(250)
        else:
            return "百家号正文图片上传后未进入可确认状态"
        await confirm.click()
        for _ in range(40):
            await page.wait_for_timeout(250)
            if await editor.locator("img").count() > existing_count:
                break
        else:
            return "百家号未把企业图片插入文章正文"
    return None


async def _upload_baijia_cover(page: Any, cover_path: Path) -> str | None:
    if not await asyncio.to_thread(cover_path.is_file):
        return "百家号文章封面文件不存在"
    single_cover = page.get_by_text("单图", exact=True).first
    # The current Baijia editor removes the "单图" switch after a single-cover
    # draft has already been selected.  In that state the cover trigger remains
    # visible and is the authoritative control, so do not reject the page merely
    # because the switch is absent.
    if await single_cover.count() and await single_cover.is_visible():
        await single_cover.click()
    trigger = page.get_by_text("选择封面", exact=True).first
    if not await trigger.count() or not await trigger.is_visible():
        if await _first_visible(page, ('[class*="cover"] img',)) is not None:
            return None
        return "未找到百家号封面上传入口"
    await trigger.click()
    await page.wait_for_timeout(350)
    dialog = await _baijia_modal(page, "封面预览")
    if dialog is None:
        return "百家号封面上传窗口未打开"
    file_input = dialog.locator('input[type="file"][accept*="image"]').first
    if not await file_input.count():
        return "百家号封面上传组件未加载"
    await file_input.set_input_files(str(cover_path))
    # Baijia appends the selected image count to this label (for example
    # "确定 (1)").  Match the semantic action while still excluding unrelated
    # buttons in the modal.
    confirm = dialog.get_by_role("button", name=BAIJIA_COVER_CONFIRM_PATTERN)
    if not await confirm.count():
        confirm = dialog.get_by_text(BAIJIA_COVER_CONFIRM_PATTERN)
    for _ in range(40):
        if await confirm.count() and await confirm.is_visible() and await confirm.is_enabled():
            break
        await page.wait_for_timeout(250)
    else:
        return "百家号封面上传后未进入可确认状态"
    await confirm.click()
    # The crop preview itself contains an image and therefore must not be used
    # as evidence that the cover was committed.  Wait until Baijia closes the
    # upload modal before looking for the editor-side cover preview.  On the
    # current page the first click can occasionally only finish the crop
    # selection while leaving the final confirmation button active, so retry
    # that same modal action once instead of clicking the obscured page-level
    # publish button underneath it.
    try:
        await dialog.wait_for(state="hidden", timeout=10_000)
    except Exception:
        retry_confirm = dialog.get_by_role(
            "button",
            name=BAIJIA_COVER_CONFIRM_PATTERN,
        )
        retry_confirm = await _first_visible_locator(retry_confirm)
        if retry_confirm is None or not await retry_confirm.is_enabled():
            return "百家号封面选择窗口未关闭，本次封面没有确认完成"
        await retry_confirm.click()
        try:
            await dialog.wait_for(state="hidden", timeout=10_000)
        except Exception:
            return "百家号封面选择窗口未关闭，本次封面没有确认完成"
    for _ in range(30):
        await page.wait_for_timeout(250)
        preview = await _first_visible(
            page,
            (
                '[class*="cover"] img',
                '[class*="cover"] [style*="background-image"]',
            ),
        )
        if preview is not None:
            return None
    return "百家号封面图片上传未完成，请检查图片格式或尺寸"


async def _upload_platform_cover(
    page: Any,
    *,
    channel_id: str,
    cover_path: Path,
) -> str | None:
    """Upload a cover only through cover-scoped controls.

    A bare ``input[type=file]`` is deliberately not used here. Creator pages often
    render separate hidden inputs for body images, covers, avatars and material
    libraries; choosing the first one can report success while updating the wrong
    part of the article.
    """
    platform = PUBLISHING_PLATFORMS_BY_ID[channel_id]
    if not await asyncio.to_thread(cover_path.is_file):
        return f"{platform['name']}文章封面文件不存在"
    selectors = GENERIC_PUBLISH_SELECTORS[channel_id]
    if await _first_visible(page, selectors["cover_preview"]) is not None:
        return None

    trigger = await _first_visible(page, selectors["cover_trigger"])
    if trigger is not None:
        await trigger.click()
        await page.wait_for_timeout(400)

    file_input = None
    for selector in selectors["cover_input"]:
        candidates = page.locator(selector)
        if await candidates.count():
            file_input = candidates.last
            break
    if file_input is None:
        return f"{platform['name']}发布页结构已变化，未找到封面专用上传入口"

    try:
        await file_input.set_input_files(str(cover_path))
    except Exception:
        return f"{platform['name']}封面上传组件未接受处理后的图片"

    await page.wait_for_timeout(800)
    for selector in (
        '[role="dialog"]:visible',
        ".ant-modal:visible",
        '[class*="dialog"]:visible',
        '[class*="modal"]:visible',
    ):
        modal = page.locator(selector).last
        if not await modal.count() or not await modal.is_visible():
            continue
        confirm = await _first_visible_locator(
            modal.get_by_role(
                "button",
                name=re.compile(r"^\s*(?:确定|完成|保存)\s*$"),
            ),
        )
        if confirm is not None and await confirm.is_enabled():
            await confirm.click()
            await page.wait_for_timeout(400)
            break

    for _ in range(20):
        if await _first_visible(page, selectors["cover_preview"]) is not None:
            return None
        await page.wait_for_timeout(250)
    return f"{platform['name']}未把已上传图片设置为文章封面"


def _platform_validation_error(channel_id: str, page_text: str) -> str | None:
    for marker, message in PLATFORM_VALIDATION_MARKERS.get(channel_id, ()):
        if marker in page_text:
            return message
    return None


async def _sohu_upload_images_from_dialog(
    page: Any,
    image_paths: list[Path],
    *,
    purpose: str,
) -> str | None:
    dialog = page.locator(".win-mask:visible").last
    for _ in range(40):
        if await dialog.count() and await dialog.is_visible():
            break
        await page.wait_for_timeout(200)
    else:
        return f"搜狐号{purpose}图片上传窗口未打开"

    file_input = dialog.locator('input[type="file"][accept*="image"]').last
    if not await file_input.count():
        return f"搜狐号{purpose}图片上传组件未加载"
    await file_input.set_input_files([str(path) for path in image_paths])

    for _ in range(60):
        confirm = await _first_visible_locator(
            dialog.locator(
                ".local-upload .bottom-buttons .positive-button",
            ).filter(has_text=re.compile(r"^\s*确定\s*$")),
        )
        if confirm is not None:
            classes = await confirm.get_attribute("class") or ""
            if "disable-button" not in classes:
                await confirm.click()
                try:
                    await dialog.wait_for(state="hidden", timeout=10_000)
                except Exception:
                    await page.wait_for_timeout(500)
                return None
        await page.wait_for_timeout(250)
    return f"搜狐号{purpose}图片上传未完成，请检查图片格式或尺寸"


async def _insert_sohu_body_images(
    page: Any,
    editor: Any,
    body_image_paths: list[Path] | None,
) -> str | None:
    available: list[Path] = []
    for image_path in body_image_paths or []:
        if await asyncio.to_thread(image_path.is_file):
            available.append(image_path)
        if len(available) == SOHU_BODY_IMAGE_COUNT:
            break
    if len(available) < SOHU_BODY_IMAGE_COUNT:
        return "搜狐号发布需要 1 张企业图片，当前未找到可用图片"

    existing_images = await editor.locator("img").count()
    await _position_toutiao_image_cursor(
        editor,
        image_index=0,
        image_count=1,
    )
    image_button = await _first_visible(page, ("button.ql-image",))
    if image_button is None:
        return "未找到搜狐号正文图片上传入口"
    await image_button.click()
    upload_error = await _sohu_upload_images_from_dialog(
        page,
        available,
        purpose="正文",
    )
    if upload_error is not None:
        return upload_error
    for _ in range(30):
        image_count = await editor.locator("img").count()
        if image_count == existing_images + SOHU_BODY_IMAGE_COUNT:
            return None
        if image_count > existing_images + SOHU_BODY_IMAGE_COUNT:
            return "搜狐号正文图片数量异常，已停止发布"
        await page.wait_for_timeout(250)
    return "搜狐号未把企业图片插入文章正文"


async def _upload_sohu_cover(page: Any, cover_path: Path) -> str | None:
    if not await asyncio.to_thread(cover_path.is_file):
        return "搜狐号文章封面文件不存在"
    cover_entry = await _first_visible(
        page,
        (
            ".upload-file.mp-upload",
            '.upload-file:has-text("上传图片")',
        ),
    )
    if cover_entry is None:
        return "未找到搜狐号封面上传入口"
    await cover_entry.click()
    dialog = page.locator(".el-dialog:visible").last
    for _ in range(30):
        if await dialog.count() and await dialog.is_visible():
            break
        await page.wait_for_timeout(200)
    else:
        return "搜狐号封面选择窗口未打开"

    local_tab = await _first_visible_locator(
        dialog.get_by_text("本地上传", exact=True),
    )
    if local_tab is None:
        return "搜狐号封面本地上传入口未显示"
    await local_tab.click()
    board = dialog.locator(".board:visible").last
    file_input = board.locator('input[type="file"][accept*="image"]').last
    if not await file_input.count():
        return "搜狐号封面上传组件未加载"
    await file_input.set_input_files(str(cover_path))

    for _ in range(60):
        confirm = await _first_visible_locator(
            board.locator(".bottom-buttons .button").filter(
                has_text=re.compile(r"^\s*确定\s*$"),
            ),
        )
        if confirm is not None:
            classes = await confirm.get_attribute("class") or ""
            if "disable-button" not in classes:
                await confirm.click()
                try:
                    await dialog.wait_for(state="hidden", timeout=10_000)
                except Exception:
                    await page.wait_for_timeout(500)
                cover_style = await page.locator(".pic-cover").first.get_attribute(
                    "style",
                )
                if cover_style and "background-image" in cover_style:
                    return None
                return "搜狐号未把已上传图片设置为文章封面"
        await page.wait_for_timeout(250)
    return "搜狐号封面图片上传未完成，请检查图片格式或尺寸"


async def _fill_sohu_summary(page: Any, body_text: str) -> None:
    summary = await _first_visible(
        page,
        ('textarea[placeholder*="摘要"]',),
    )
    if summary is not None:
        compact_summary = re.sub(r"\s+", " ", body_text).strip()[:120]
        await summary.fill(compact_summary)


def _clean_sohu_topic(value: str) -> str:
    compact = re.sub(r"[\s，。\uFF01\uFF1F、,.!?]+", "", value)
    compact = re.sub(
        r"(?:哪家好|怎么样|好吗|怎么选|如何选|推荐一家|机构推荐|培训推荐|推荐)$",
        "",
        compact,
    )
    return compact[:18]


def _sohu_topic_candidates(
    *,
    brand_name: str,
    target_keywords: list[str],
) -> list[str]:
    candidates = [*target_keywords, brand_name]
    topics: list[str] = []
    for candidate in candidates:
        cleaned = _clean_sohu_topic(candidate)
        if 2 <= len(cleaned) <= 18 and cleaned not in topics:
            topics.append(cleaned)
        if len(topics) == 2:
            break
    return topics


def _sohu_article_attribute(*, title: str, content_type: str | None) -> str:
    by_content_type = {
        "company_fact": "知识科普",
        "scenario_solution": "经验教程",
        "practical_guide": "经验教程",
        "faq": "知识科普",
        "comparison": "测评盘点",
        "service_process": "经验教程",
        "service_description": "知识科普",
        "local_recommendation": "测评盘点",
        "local_service_explainer": "知识科普",
        "case_study": "见闻记录",
        "price_guide": "测评盘点",
        "selection_guide": "经验教程",
    }
    if content_type in by_content_type:
        return by_content_type[content_type]
    if any(marker in title for marker in ("观点", "评论", "怎么看")):
        return "观点评论"
    if any(marker in title for marker in ("推荐", "哪家好", "对比", "盘点", "测评")):
        return "测评盘点"
    if any(marker in title for marker in ("如何", "怎么", "指南", "攻略", "流程", "注意")):
        return "经验教程"
    return "知识科普"


async def _select_sohu_topics(page: Any, topic_candidates: list[str]) -> None:
    topic_input = page.locator(".select-topic input.el-select__input").first
    if not await topic_input.count() or not await topic_input.is_visible():
        return
    selected_topics: set[str] = set()
    for topic in topic_candidates:
        search_terms = [topic]
        for width in (6, 4, 2):
            if len(topic) > width:
                search_terms.append(topic[-width:])
        for search_term in dict.fromkeys(search_terms):
            if search_term in selected_topics:
                continue
            await topic_input.click()
            await topic_input.fill("")
            await topic_input.press_sequentially(search_term, delay=25)
            await page.wait_for_timeout(1200)
            option = await _first_visible_locator(
                page.locator(".el-select-dropdown:visible li").filter(
                    has_text=re.compile(rf"^\s*{re.escape(search_term)}\s*$"),
                ),
            )
            if option is None:
                continue
            await option.click()
            selected_topics.add(search_term)
            await page.wait_for_timeout(200)
            break
        if len(selected_topics) == 2:
            break


async def _select_sohu_attribute(
    page: Any,
    *,
    title: str,
    content_type: str | None,
) -> str | None:
    attribute = _sohu_article_attribute(title=title, content_type=content_type)
    selector = page.locator(".article-attr .select-main").first
    if not await selector.count() or not await selector.is_visible():
        return "搜狐号未找到文章属性选择器"
    await selector.click()
    option = await _first_visible_locator(
        page.locator(".article-attr .select-list:visible li").filter(
            has_text=re.compile(rf"^\s*{re.escape(attribute)}\s*$"),
        ),
    )
    if option is None:
        return f"搜狐号未找到与文章匹配的属性“{attribute}”"
    await option.click()
    await page.wait_for_timeout(150)
    return None


async def _select_sohu_existing_column(
    page: Any,
    topic_candidates: list[str],
) -> None:
    entry = page.locator(".bind-column-btn").first
    if not await entry.count() or not await entry.is_visible():
        return
    await entry.click()
    modal = page.locator(".mt-dialog:visible").last
    if not await modal.count() or not await modal.is_visible():
        return
    tags = modal.locator(".column-tag")
    selected = False
    for index in range(await tags.count()):
        tag = tags.nth(index)
        name = (await tag.inner_text()).strip()
        if not name:
            continue
        if any(name in topic or topic in name for topic in topic_candidates):
            classes = await tag.get_attribute("class") or ""
            if "active" not in classes.split():
                await tag.click()
            selected = True
            break
    footer_button_name = "确定" if selected else "取消"
    footer_button = await _first_visible_locator(
        modal.get_by_role(
            "button",
            name=re.compile(rf"^\s*{footer_button_name}\s*$"),
        ),
    )
    if footer_button is not None:
        await footer_button.click()
        await page.wait_for_timeout(150)


async def _generic_publish_button(page: Any, channel_id: str) -> Any:
    if channel_id == "sohu":
        return await _first_visible_locator(
            page.locator("li.publish-report-btn").filter(
                has_text=re.compile(r"^\s*发布\s*$"),
            ),
        )
    if channel_id == "netease":
        return await _first_visible_locator(
            page.locator(
                ".post-footer__container-right button.primary_button",
            ).filter(has_text=re.compile(r"^\s*发布\s*$")),
        )
    labels = PLATFORM_PUBLISH_BUTTON_LABELS[channel_id]
    label_pattern = "|".join(re.escape(label) for label in labels)
    return await _first_visible_locator(
        page.get_by_role(
            "button",
            name=re.compile(rf"^\s*(?:{label_pattern})\s*$"),
        ),
    )


async def _wait_for_netease_submission_receipt(
    page: Any,
    *,
    before_text: str,
) -> PublishResult:
    """Wait through NetEase's pre-publication quality scan for a real receipt."""

    last_text = before_text
    scan_advanced = False
    for _ in range(120):
        await page.wait_for_timeout(500)
        try:
            last_text = await page.locator("body").inner_text(timeout=5000)
        except Exception:
            # The successful submit can replace the route while the body is
            # being mounted.  Continue within the same bounded wait window.
            continue
        if _has_security_verification(last_text):
            return PublishResult(
                status="needs_verification",
                error_message="网易号发布前要求完成验证码或安全验证",
            )
        prerequisite_error = _netease_publish_prerequisite_error(last_text)
        if prerequisite_error is not None:
            return PublishResult(status="rejected", error_message=prerequisite_error)
        if any(marker in last_text for marker in PLATFORM_REJECTION_MARKERS):
            detail = re.sub(r"\s+", " ", last_text).strip()
            return PublishResult(
                status="rejected",
                error_message=f"网易号拒绝了本次发布: {detail}"[:500],
            )
        validation_error = _platform_validation_error("netease", last_text)
        if validation_error is not None:
            return PublishResult(status="failed", error_message=validation_error)
        if not scan_advanced and _netease_scan_requires_final_submit(
            before_text=before_text,
            after_text=last_text,
        ):
            final_submit = await _generic_publish_button(page, "netease")
            if final_submit is None or not await final_submit.is_enabled():
                return PublishResult(
                    status="failed",
                    error_message="网易号发文检测已完成，但最终发布按钮不可用",
                )
            await final_submit.click(timeout=10_000)
            scan_advanced = True
            continue
        if (
            _has_new_pending_review_marker(
                "netease",
                before_text=before_text,
                after_text=last_text,
            )
            or "content-manage" in page.url
        ):
            return PublishResult(status="pending_review")
    return PublishResult(
        status="failed",
        error_message=(
            "网易号在 60 秒内未返回发布成功回执，本次文章没有确认提交，"
            "请检查账号限制、发文检测或页面提示后重试"
        ),
    )


def _netease_scan_requires_final_submit(*, before_text: str, after_text: str) -> bool:
    """Detect NetEase's non-blocking assistant scan before the real submit."""

    return (
        "发文助手小易" not in before_text
        and "发文助手小易" in after_text
        and "重新检测" in after_text
        and "诊断通过" in after_text
    )


async def _first_public_article_url(page: Any, channel_id: str) -> str | None:
    patterns = {
        "baijia": re.compile(r"(?:baijiahao\.baidu\.com/s\?|mbd\.baidu\.com/)", re.I),
        "netease": re.compile(r"163\.com/dy/article/", re.I),
        "sohu": re.compile(r"sohu\.com/a/", re.I),
        "penguin": re.compile(
            r"(?:new\.qq\.com/rain/a/|page\.om\.qq\.com/page/)",
            re.I,
        ),
        "yidian": re.compile(r"yidianzixun\.com/(?:article|content)/", re.I),
    }
    pattern = patterns[channel_id]
    links = page.locator("a[href]")
    for index in range(min(await links.count(), 200)):
        href = cast(str | None, await links.nth(index).get_attribute("href"))
        if href and pattern.search(href):
            return href
    return None


def _normalized_public_text(value: str) -> str:
    return re.sub(r"[\W_]+", "", value, flags=re.UNICODE).casefold()


def _select_management_public_url(
    entries: list[tuple[str, str]],
    *,
    channel_id: str,
    title: str,
    excluded_urls: set[str],
) -> str | None:
    patterns = {
        "baijia": re.compile(r"(?:baijiahao\.baidu\.com/s\?|mbd\.baidu\.com/)", re.I),
        "netease": re.compile(r"163\.com/dy/article/", re.I),
        "sohu": re.compile(r"sohu\.com/a/", re.I),
        "penguin": re.compile(
            r"(?:new\.qq\.com/rain/a/|page\.om\.qq\.com/page/)",
            re.I,
        ),
        "yidian": re.compile(r"yidianzixun\.com/(?:article|content)/", re.I),
    }
    expected_title = _normalized_public_text(title)
    for href, link_text in entries:
        if href in excluded_urls or not patterns[channel_id].search(href):
            continue
        if _normalized_public_text(link_text) == expected_title:
            return href
    return None


def _classify_management_publication(
    *,
    channel_id: str,
    row_text: str,
    public_url: str | None,
) -> PublishResult:
    """Classify one exact-title management row without treating review as failure."""

    if public_url is not None:
        post_match = re.search(
            r"(?:article/|/a/|rain/a/|page/|[?&]id=)([0-9A-Za-z_-]+)",
            public_url,
        )
        return PublishResult(
            status="published",
            public_url=public_url,
            platform_post_id=post_match.group(1) if post_match else None,
        )
    compact = re.sub(r"\s+", "", row_text)
    if any(marker in compact for marker in PLATFORM_REJECTION_MARKERS):
        detail = re.sub(r"\s+", " ", row_text).strip()
        return PublishResult(
            status="rejected",
            error_message=(f"{PUBLISHING_PLATFORMS_BY_ID[channel_id]['name']}审核未通过: {detail}")[
                :500
            ],
        )
    # Finding the exact title in content management is proof that the platform
    # accepted the submission. An unrecognised row state is therefore kept in
    # review instead of being incorrectly downgraded to a publishing failure.
    return PublishResult(status="pending_review")


def _has_new_pending_review_marker(
    channel_id: str,
    *,
    before_text: str,
    after_text: str,
) -> bool:
    """Only accept a review marker that appeared after the publish action."""

    return any(
        marker in after_text and marker not in before_text
        for marker in PLATFORM_PENDING_REVIEW_MARKERS[channel_id]
    )


def _missing_management_record_result(
    channel_id: str,
    *,
    submitted_at: datetime | None,
    now: datetime,
) -> PublishResult:
    """Stop acknowledged submissions from remaining in review forever."""

    grace_periods = {
        "baijia": BAIJIA_MANAGEMENT_RECORD_GRACE_PERIOD,
        "netease": NETEASE_MANAGEMENT_RECORD_GRACE_PERIOD,
        "penguin": PENGUIN_MANAGEMENT_RECORD_GRACE_PERIOD,
        "yidian": timedelta(hours=2),
    }
    grace_period = grace_periods.get(channel_id)
    if grace_period is None:
        return PublishResult(status="pending_review")
    if submitted_at is not None:
        elapsed = _as_utc(now) - _as_utc(submitted_at)
        if elapsed < grace_period:
            return PublishResult(status="pending_review")
    platform_name = PUBLISHING_PLATFORMS_BY_ID[channel_id]["name"]
    return PublishResult(
        status="failed",
        error_message=(
            f"{platform_name}内容管理在平台审核时限内未找到对应文章，"
            "本次发布未取得可持续回查的记录，请检查账号后台后重新发布"
        ),
    )


def _missing_submission_receipt_result(channel_id: str) -> PublishResult:
    # Sohu is known to return to content management before the new row becomes
    # visible. Baijia must not use this fallback: without a new receipt, public
    # URL or exact-title management row, the platform did not confirm submission.
    if channel_id == "sohu":
        return PublishResult(status="pending_review")
    platform_name = PUBLISHING_PLATFORMS_BY_ID[channel_id]["name"]
    return PublishResult(
        status="failed",
        error_message=(
            f"未检测到{platform_name}发布成功回执，且内容管理中没有找到对应文章，本次发布未成功"
        ),
    )


async def _management_title_row(page: Any, title: str) -> tuple[str, list[str]] | None:
    title_nodes = page.get_by_text(title, exact=True)
    for index in range(min(await title_nodes.count(), 20)):
        node = title_nodes.nth(index)
        if not await node.is_visible():
            continue
        result = cast(
            dict[str, object],
            await node.evaluate(
                """
                element => {
                  const rowPattern = new RegExp(
                    [
                      '审核中', '待审核', '等待审核', '已提交', '提交成功',
                      '已发布', '处理中', '待发布', '审核不通过',
                      '审核未通过', '未通过', '已驳回', '发布失败',
                      '处理失败', '内容违规', '已下线', '作者下线', '已删除'
                    ].join('|')
                  );
                  let current = element;
                  let fallback = element;
                  for (let depth = 0; current && depth < 9; depth += 1) {
                    const text = (current.innerText || '').trim();
                    if (text.length > 0 && text.length <= 1200) fallback = current;
                    const tag = (current.tagName || '').toLowerCase();
                    const className = String(current.className || '');
                    const looksLikeRow = ['tr', 'li', 'article'].includes(tag)
                      || /(item|row|card|content|article)/i.test(className);
                    if (text.length > 0 && text.length <= 1200 && looksLikeRow) {
                      fallback = current;
                    }
                    // NetEase's title wrapper class contains both "Content"
                    // and "Card", but only the outer card contains the review
                    // status and rejection reason.  Keep walking until a real
                    // status marker is present instead of stopping at the
                    // title-only wrapper.
                    if (text.length > 0 && text.length <= 1200 && rowPattern.test(text)) {
                      const hrefs = Array.from(current.querySelectorAll('a[href]'))
                        .map(link => link.href)
                        .filter(Boolean);
                      return { text, hrefs };
                    }
                    current = current.parentElement;
                  }
                  const text = (fallback.innerText || '').trim();
                  const hrefs = Array.from(fallback.querySelectorAll('a[href]'))
                    .map(link => link.href)
                    .filter(Boolean);
                  return { text, hrefs };
                }
                """,
            ),
        )
        text_value = str(result.get("text") or title).strip()
        hrefs = [str(value) for value in cast(list[object], result.get("hrefs") or [])]
        return text_value, hrefs
    return None


async def _generic_management_status(
    context: Any,
    *,
    channel_id: str,
    title: str,
) -> PublishResult | None:
    platform = PUBLISHING_PLATFORMS_BY_ID[channel_id]
    page = await context.new_page()
    try:
        await page.goto(
            platform["manage_url"],
            wait_until="domcontentloaded",
            timeout=30_000,
        )
        if channel_id == "penguin":
            await _ensure_penguin_workspace(page, target="manage")
        for _ in range(10):
            await page.wait_for_timeout(1000)
            page_text = await page.locator("body").inner_text(timeout=5000)
            if _looks_logged_out(page.url, page_text):
                return PublishResult(
                    status="needs_login",
                    error_message=f"{platform['name']}登录已失效，请到渠道配置重新登录",
                )
            if _has_security_verification(page_text):
                return PublishResult(
                    status="needs_verification",
                    error_message=f"{platform['name']}要求完成安全验证，请打开登录窗口处理",
                )
            row = await _management_title_row(page, title)
            if row is None:
                continue
            row_text, hrefs = row
            public_url = _select_management_public_url(
                [(href, title) for href in hrefs],
                channel_id=channel_id,
                title=title,
                excluded_urls=set(),
            )
            return _classify_management_publication(
                channel_id=channel_id,
                row_text=row_text,
                public_url=public_url,
            )
        return None
    finally:
        await page.close()


def _public_article_integrity_error(
    expected_body: str,
    public_body: str,
    *,
    image_count: int,
    max_images: int,
) -> str | None:
    expected = _normalized_public_text(expected_body)
    actual = _normalized_public_text(public_body.replace("返回搜狐查看更多", ""))
    minimum_length = max(300, int(len(expected) * 0.55))
    if len(actual) < minimum_length:
        return f"公开页正文不完整，预期约 {len(expected)} 字，实际仅识别到 {len(actual)} 字"
    anchor_length = min(24, max(12, len(expected) // 12))
    positions = (0, max(0, len(expected) // 2 - anchor_length // 2), len(expected) - anchor_length)
    anchors = {
        expected[max(0, position) : max(0, position) + anchor_length]
        for position in positions
        if expected[max(0, position) : max(0, position) + anchor_length]
    }
    matched_anchors = sum(anchor in actual for anchor in anchors)
    required_anchors = min(2, len(anchors))
    if matched_anchors < required_anchors:
        return "公开页正文不完整，开头、中段或结尾内容与待发布正文不一致"
    if image_count > max_images:
        return f"公开页图片数量异常，正文出现 {image_count} 张图片，最多允许 {max_images} 张"
    return None


async def _verify_public_article(
    context: Any,
    *,
    channel_id: str,
    public_url: str,
    expected_body: str,
) -> str | None:
    if channel_id not in {"sohu", "baijia", "netease", "penguin", "yidian"}:
        return None
    page = await context.new_page()
    last_error = "公开页尚未生成可核验正文"
    try:
        for _ in range(5):
            await page.goto(
                public_url,
                wait_until="domcontentloaded",
                timeout=30_000,
            )
            await page.wait_for_timeout(1500)
            selectors: tuple[str, ...]
            if channel_id == "sohu":
                selectors = ("article",)
            elif channel_id == "netease":
                selectors = (
                    ".post_body",
                    ".post_text",
                    ".article-content",
                    "article",
                    '[class*="article"] [class*="content"]',
                )
            elif channel_id == "penguin":
                selectors = (
                    "article",
                    ".article-content",
                    '[class*="article"] [class*="content"]',
                    '[class*="detail"] [class*="content"]',
                )
            elif channel_id == "yidian":
                selectors = (
                    "article",
                    ".article-content",
                    ".content-detail",
                    '[class*="article"] [class*="content"]',
                    '[class*="content"] [class*="detail"]',
                )
            else:
                selectors = (
                    '[data-testid="article"]',
                    ".article-content",
                    "#ssr-content",
                    "article",
                    '[class*="article"] [class*="content"]',
                )
            article = await _first_visible(page, selectors)
            if article is not None:
                public_body = await article.inner_text(timeout=5000)
                image_count = await article.locator("img").count()
                if channel_id == "sohu":
                    max_images = SOHU_PUBLIC_IMAGE_LIMIT
                elif channel_id == "netease":
                    max_images = NETEASE_PUBLIC_IMAGE_LIMIT
                elif channel_id == "penguin":
                    max_images = PENGUIN_PUBLIC_IMAGE_LIMIT
                elif channel_id == "yidian":
                    max_images = YIDIAN_PUBLIC_IMAGE_LIMIT
                else:
                    max_images = BAIJIA_PUBLIC_IMAGE_LIMIT
                last_error = (
                    _public_article_integrity_error(
                        expected_body,
                        public_body,
                        image_count=image_count,
                        max_images=max_images,
                    )
                    or ""
                )
                if not last_error:
                    return None
            await page.wait_for_timeout(1500)
        return last_error
    finally:
        await page.close()


async def _generic_confirmation_button(page: Any, channel_id: str) -> Any:
    labels = PLATFORM_CONFIRMATION_LABELS[channel_id]
    label_pattern = "|".join(re.escape(label) for label in labels)
    confirmation_pattern = re.compile(rf"^\s*(?:{label_pattern})\s*$")
    for selector in (
        '[role="dialog"]',
        '.ant-modal:not([style*="display: none"])',
        ".win-mask:visible",
        '[class*="modal"]:visible',
        '[class*="dialog"]:visible',
    ):
        scope = page.locator(selector).last
        if not await scope.count() or not await scope.is_visible():
            continue
        button = await _first_visible_locator(
            scope.get_by_role(
                "button",
                name=confirmation_pattern,
            ),
        )
        if button is not None:
            return button
        text_button = await _first_visible_locator(
            scope.get_by_text(
                confirmation_pattern,
            ),
        )
        if text_button is not None:
            return text_button
    return None


async def _wait_for_generic_confirmation_button(
    page: Any,
    channel_id: str,
    *,
    attempts: int = 20,
    delay_ms: int = 250,
) -> Any | None:
    for attempt in range(attempts):
        button = await _generic_confirmation_button(page, channel_id)
        if button is not None:
            return button
        if attempt < attempts - 1:
            await page.wait_for_timeout(delay_ms)
    return None


async def publish_with_browser_adapter(
    settings: Settings,
    *,
    channel_id: str,
    account_id: UUID,
    document_id: UUID,
    version_id: UUID,
    title: str,
    body_markdown: str,
    cover_path: Path,
    body_image_paths: list[Path] | None = None,
    topic_candidates: list[str] | None = None,
    content_type: str | None = None,
) -> PublishResult:
    if channel_id == "toutiao":
        return await publish_to_toutiao(
            settings,
            account_id=account_id,
            document_id=document_id,
            version_id=version_id,
            title=title,
            body_markdown=body_markdown,
            cover_path=cover_path,
            body_image_paths=body_image_paths,
        )
    platform = PUBLISHING_PLATFORMS_BY_ID[channel_id]
    if settings.publishing_execution_mode == "fixed_mock":
        return PublishResult(
            status="published",
            public_url=f"{platform['official_url']}mock/{version_id.hex}",
            platform_post_id=f"mock-{account_id.hex}-{version_id.hex}",
        )
    if channel_id == "yidian":
        return PublishResult(
            status="failed",
            error_message=(
                "一点号首个真实账号尚未完成发布页字段验证，系统已停止最终提交。"
                "请先在渠道配置完成登录，并执行一次只填充验证后再开放真实发布"
            ),
        )
    try:
        from playwright.async_api import async_playwright
    except ImportError:
        return PublishResult(status="failed", error_message="自动发布组件未安装")
    selectors = GENERIC_PUBLISH_SELECTORS[channel_id]
    try:
        async with async_playwright() as playwright:
            context = await playwright.chromium.launch_persistent_context(
                str(_browser_profile_path(settings, channel_id, account_id)),
                executable_path=str(_browser_executable(settings)),
                headless=True,
                args=["--disable-blink-features=AutomationControlled"],
            )
            try:
                page = context.pages[0] if context.pages else await context.new_page()
                await page.goto(
                    _publishing_editor_url(channel_id),
                    wait_until="domcontentloaded",
                    timeout=30_000,
                )
                await page.wait_for_timeout(1800)
                page_text = await page.locator("body").inner_text(timeout=5000)
                if _looks_logged_out(page.url, page_text):
                    return PublishResult(
                        status="needs_login",
                        error_message=f"{platform['name']}登录已失效，请到渠道配置重新登录",
                    )
                if _has_security_verification(page_text):
                    return PublishResult(
                        status="needs_verification",
                        error_message=f"{platform['name']}要求完成安全验证，请打开登录窗口处理",
                    )
                if channel_id == "baijia":
                    title_input, editor = await _wait_for_baijia_editors(page)
                elif channel_id == "netease":
                    title_input, editor = await _wait_for_netease_editors(page)
                elif channel_id == "penguin":
                    title_input, editor = await _wait_for_penguin_editors(page)
                else:
                    title_input = await _first_visible(page, selectors["title"])
                    editor = await _first_visible(page, selectors["editor"])
                if title_input is None or editor is None:
                    return PublishResult(
                        status="failed",
                        error_message=f"{platform['name']}发布页结构已变化，未找到标题或正文输入区域",
                    )
                normalized_title = _platform_submission_title(channel_id, title)
                normalized_body = _markdown_to_plain_text(body_markdown)
                platform_spec = get_publishing_platform_spec(channel_id)
                if platform_spec is None:
                    return PublishResult(
                        status="failed",
                        error_message=f"{platform['name']}尚未配置发布规范",
                    )
                if channel_id == "baijia":
                    title_error = _baijia_title_error(title)
                    if title_error is not None:
                        return PublishResult(status="failed", error_message=title_error)
                elif channel_id == "netease":
                    title_error = _netease_title_error(title)
                    if title_error is not None:
                        return PublishResult(status="failed", error_message=title_error)
                if (
                    len(normalized_title) < platform_spec.title_min_characters
                    or len(normalized_title) > platform_spec.title_max_characters
                    or len(normalized_body) < platform_spec.minimum_body_characters
                ):
                    return PublishResult(
                        status="failed",
                        error_message=(
                            f"文章未满足{platform['name']}发布规格，标题需"
                            f"{platform_spec.title_min_characters}—"
                            f"{platform_spec.title_max_characters}字，正文不少于"
                            f"{platform_spec.minimum_body_characters}个有效字符"
                        ),
                    )
                await title_input.fill(normalized_title)
                if channel_id == "netease":
                    await _fill_netease_editor(page, editor, normalized_body)
                else:
                    await _fill_generic_editor(editor, normalized_body)
                await page.wait_for_timeout(500)

                if channel_id == "baijia":
                    title_text = (await title_input.inner_text()).strip()
                    editor_text = (await editor.inner_text()).strip()
                    if title_text != normalized_title:
                        return PublishResult(
                            status="failed",
                            error_message="百家号标题填写不完整，已停止发布",
                        )
                    editor_error = _public_article_integrity_error(
                        normalized_body,
                        editor_text,
                        image_count=0,
                        max_images=BAIJIA_BODY_IMAGE_COUNT,
                    )
                    if editor_error is not None:
                        return PublishResult(
                            status="failed",
                            error_message=editor_error.replace("公开页", "百家号发布编辑器"),
                        )
                    # Configure declarations before opening upload modals.  The
                    # Baijia cover workflow can re-render or collapse the lower
                    # settings panel after confirmation.
                    settings_error = await _set_baijia_work_settings(page)
                    if settings_error is not None:
                        return PublishResult(status="failed", error_message=settings_error)
                    image_error = await _insert_baijia_body_images(
                        page,
                        editor,
                        body_image_paths,
                    )
                    if image_error is not None:
                        return PublishResult(status="failed", error_message=image_error)
                    cover_error = await _upload_baijia_cover(page, cover_path)
                    if cover_error is not None:
                        return PublishResult(status="failed", error_message=cover_error)
                elif channel_id == "sohu":
                    if len(normalized_title) < 5:
                        return PublishResult(
                            status="failed",
                            error_message="搜狐号文章标题至少需要 5 个字",
                        )
                    image_error = await _insert_sohu_body_images(
                        page,
                        editor,
                        body_image_paths,
                    )
                    if image_error is not None:
                        return PublishResult(status="failed", error_message=image_error)
                    cover_error = await _upload_sohu_cover(page, cover_path)
                    if cover_error is not None:
                        return PublishResult(status="failed", error_message=cover_error)
                    await _fill_sohu_summary(page, normalized_body)
                    await _select_sohu_topics(page, topic_candidates or [])
                    attribute_error = await _select_sohu_attribute(
                        page,
                        title=normalized_title,
                        content_type=content_type,
                    )
                    if attribute_error is not None:
                        return PublishResult(
                            status="failed",
                            error_message=attribute_error,
                        )
                    await _select_sohu_existing_column(
                        page,
                        topic_candidates or [],
                    )
                    editor_text = await editor.inner_text(timeout=5000)
                    editor_image_count = await editor.locator("img").count()
                    editor_error = _public_article_integrity_error(
                        normalized_body,
                        editor_text,
                        image_count=editor_image_count,
                        max_images=SOHU_BODY_IMAGE_COUNT,
                    )
                    if editor_error is not None:
                        return PublishResult(
                            status="failed",
                            error_message=editor_error.replace("公开页", "搜狐号发布编辑器"),
                        )
                elif channel_id == "netease":
                    title_value = (await title_input.input_value()).strip()
                    editor_text = (await editor.inner_text()).strip()
                    if title_value != normalized_title:
                        return PublishResult(
                            status="failed",
                            error_message="网易号标题填写不完整，已停止发布",
                        )
                    editor_error = _public_article_integrity_error(
                        normalized_body,
                        editor_text,
                        image_count=0,
                        max_images=NETEASE_BODY_IMAGE_COUNT,
                    )
                    if editor_error is not None:
                        return PublishResult(
                            status="failed",
                            error_message=editor_error.replace("公开页", "网易号发布编辑器"),
                        )
                    image_error = await _insert_netease_body_images(
                        page,
                        editor,
                        cover_path=cover_path,
                        body_image_paths=body_image_paths,
                    )
                    if image_error is not None:
                        return PublishResult(status="failed", error_message=image_error)
                    cover_error = await _upload_netease_cover(page)
                    if cover_error is not None:
                        return PublishResult(status="failed", error_message=cover_error)
                    await _set_netease_optional_statement(page)
                    editor_image_count = await editor.locator("img").count()
                    minimum_images = PUBLISHING_PLATFORM_SPECS["netease"].image.minimum_body_images
                    if (
                        editor_image_count < minimum_images
                        or editor_image_count > NETEASE_BODY_IMAGE_COUNT
                    ):
                        return PublishResult(
                            status="failed",
                            error_message=(
                                f"网易号正文图片数量异常，必须保留 {minimum_images} 张相关图片"
                            ),
                        )
                elif channel_id == "penguin":
                    title_tag = (
                        await title_input.evaluate("element => element.tagName")
                    ).casefold()
                    title_value = (
                        await title_input.input_value()
                        if title_tag in {"input", "textarea"}
                        else await title_input.inner_text()
                    ).strip()
                    editor_text = (await editor.inner_text()).strip()
                    if title_value != normalized_title:
                        return PublishResult(
                            status="failed",
                            error_message="企鹅号标题填写不完整，已停止发布",
                        )
                    editor_error = _public_article_integrity_error(
                        normalized_body,
                        editor_text,
                        image_count=0,
                        max_images=PENGUIN_BODY_IMAGE_COUNT,
                    )
                    if editor_error is not None:
                        return PublishResult(
                            status="failed",
                            error_message=editor_error.replace("公开页", "企鹅号发布编辑器"),
                        )
                    image_error = await _insert_penguin_body_images(
                        page,
                        editor,
                        body_image_paths,
                    )
                    if image_error is not None:
                        return PublishResult(status="failed", error_message=image_error)
                    cover_error = await _select_penguin_cover_from_body(page)
                    if cover_error is not None:
                        return PublishResult(status="failed", error_message=cover_error)
                    declaration_error = await _set_penguin_ai_declaration(page)
                    if declaration_error is not None:
                        return PublishResult(
                            status="failed",
                            error_message=declaration_error,
                        )
                    editor_image_count = await editor.locator("img").count()
                    if editor_image_count != PENGUIN_BODY_IMAGE_COUNT:
                        return PublishResult(
                            status="failed",
                            error_message=(
                                "企鹅号正文图片数量异常，必须保留 "
                                f"{PENGUIN_BODY_IMAGE_COUNT} 张相关图片"
                            ),
                        )
                else:
                    cover_error = await _upload_platform_cover(
                        page,
                        channel_id=channel_id,
                        cover_path=cover_path,
                    )
                    if cover_error is not None:
                        return PublishResult(status="failed", error_message=cover_error)

                prepublish_text = await page.locator("body").inner_text(timeout=5000)
                if channel_id == "netease":
                    prerequisite_error = _netease_publish_prerequisite_error(
                        prepublish_text,
                    )
                    if prerequisite_error is not None:
                        return PublishResult(
                            status="rejected",
                            error_message=prerequisite_error,
                        )
                validation_error = _platform_validation_error(
                    channel_id,
                    prepublish_text,
                )
                if validation_error is not None:
                    return PublishResult(
                        status="failed",
                        error_message=validation_error,
                    )

                publish_button = await _generic_publish_button(page, channel_id)
                if publish_button is None:
                    return PublishResult(
                        status="failed",
                        error_message=f"{platform['name']}发布流程已变化，未找到发布按钮",
                    )
                if channel_id == "sohu":
                    publish_classes = await publish_button.get_attribute("class") or ""
                    publish_enabled = "active" in publish_classes
                else:
                    publish_enabled = await publish_button.is_enabled()
                if not publish_enabled:
                    return PublishResult(
                        status="failed",
                        error_message=f"{platform['name']}发布前校验未通过，请检查页面提示",
                    )
                # Do not force-click Baijia controls. A forced click can bypass
                # the page's actionability checks without creating a platform
                # submission, which previously produced a false review state.
                await publish_button.click(timeout=10_000)
                if channel_id not in {"sohu", "netease"}:
                    confirm = await _wait_for_generic_confirmation_button(page, channel_id)
                    if confirm is not None:
                        for _ in range(20):
                            if await confirm.is_enabled():
                                break
                            await page.wait_for_timeout(250)
                        else:
                            return PublishResult(
                                status="failed",
                                error_message=(
                                    f"{platform['name']}最终确认按钮不可用，本次文章没有提交到平台"
                                ),
                            )
                        await confirm.click(timeout=10_000)
                netease_receipt: PublishResult | None = None
                if channel_id == "netease":
                    netease_receipt = await _wait_for_netease_submission_receipt(
                        page,
                        before_text=prepublish_text,
                    )
                    if netease_receipt.status != "pending_review":
                        return netease_receipt
                else:
                    await page.wait_for_timeout(3500)
                result_text = await page.locator("body").inner_text(timeout=5000)
                if _has_security_verification(result_text):
                    return PublishResult(
                        status="needs_verification",
                        error_message=f"{platform['name']}发布前要求完成安全验证",
                    )
                if any(
                    word in result_text
                    for word in ("内容违规", "审核不通过", "发布失败", "提交失败")
                ):
                    return PublishResult(
                        status="rejected",
                        error_message=f"{platform['name']}拒绝了本次发布，请登录平台查看具体原因",
                    )
                result_validation_error = _platform_validation_error(
                    channel_id,
                    result_text,
                )
                if result_validation_error is not None:
                    return PublishResult(
                        status="failed",
                        error_message=result_validation_error,
                    )
                public_url = (
                    None
                    if channel_id == "sohu"
                    else await _first_public_article_url(page, channel_id)
                )
                management_result = await _generic_management_status(
                    context,
                    channel_id=channel_id,
                    title=normalized_title,
                )
                if management_result is not None:
                    if management_result.status in {
                        "rejected",
                        "needs_login",
                        "needs_verification",
                    }:
                        return management_result
                    public_url = management_result.public_url or public_url
                    if management_result.status == "pending_review":
                        return management_result
                if public_url is None and _has_new_pending_review_marker(
                    channel_id,
                    before_text=prepublish_text,
                    after_text=result_text,
                ):
                    return PublishResult(status="pending_review")
                if public_url is None and netease_receipt is not None:
                    return netease_receipt
                if public_url is None:
                    return _missing_submission_receipt_result(channel_id)
                if public_url is not None:
                    integrity_error = await _verify_public_article(
                        context,
                        channel_id=channel_id,
                        public_url=public_url,
                        expected_body=normalized_body,
                    )
                    if integrity_error is not None:
                        return PublishResult(
                            status="failed",
                            public_url=public_url,
                            error_message=(
                                f"{platform['name']}已提交，但公开页验收失败，"
                                f"{integrity_error}。请到平台删除或修正该文章。"
                            ),
                        )
                post_id = None
                if public_url:
                    match = re.search(
                        r"(?:article/|/a/|rain/a/|page/|[?&]id=)([0-9A-Za-z_-]+)",
                        public_url,
                    )
                    post_id = match.group(1) if match else None
                return PublishResult(
                    status="published",
                    public_url=public_url,
                    platform_post_id=post_id,
                )
            finally:
                await context.close()
    except Exception as error:
        message = str(error)
        if _browser_profile_in_use_error(message):
            message = f"{platform['name']}账号正在使用，请关闭登录窗口后重试"
        return PublishResult(status="failed", error_message=message[:500])


def _account_data(
    account: PublishingAccount,
    *,
    now: datetime | None = None,
) -> dict[str, object]:
    health = publishing_session_health(account, now=now)
    return {
        "id": str(account.id),
        "channel_id": account.channel_id,
        "display_name": account.display_name,
        "enabled": account.enabled,
        "connection_status": account.connection_status,
        "account_name": account.account_name,
        "last_checked_at": (
            account.last_checked_at.isoformat() if account.last_checked_at else None
        ),
        "last_error": account.last_error,
        "session_health": health.status,
        "session_health_label": health.label,
        "session_health_message": health.message,
        "next_automatic_check_at": (
            health.next_check_at.isoformat() if health.next_check_at else None
        ),
        "automatic_check_interval_hours": 24,
        "version": account.version,
        "created_at": account.created_at.isoformat(),
        "updated_at": account.updated_at.isoformat(),
    }


def _platform_data(
    platform: PublishingPlatformEntry,
    accounts: list[PublishingAccount],
) -> dict[str, object]:
    now = datetime.now(UTC)
    health_by_account = {
        account.id: publishing_session_health(account, now=now) for account in accounts
    }
    return {
        **platform,
        "generation_spec": platform_prompt_contract(platform["id"]),
        "can_configure": True,
        "max_accounts": MAX_ACCOUNTS_PER_PLATFORM,
        "account_count": len(accounts),
        "connected_count": sum(account.connection_status == "connected" for account in accounts),
        "enabled_count": sum(account.enabled for account in accounts),
        "attention_count": sum(
            health.status not in {"healthy", "check_due_soon"}
            for health in health_by_account.values()
        ),
        "accounts": [_account_data(account, now=now) for account in accounts],
    }


async def _publishing_account(
    database: AsyncSession,
    account_id: UUID,
    *,
    for_update: bool = False,
) -> PublishingAccount | None:
    statement = select(PublishingAccount).where(PublishingAccount.id == account_id)
    if for_update:
        statement = statement.with_for_update()
    return cast(PublishingAccount | None, await database.scalar(statement))


_ACCOUNT_LOCKS: dict[UUID, asyncio.Lock] = {}


def _profile_is_busy(result: ConnectionResult) -> bool:
    message = result.error_message or ""
    return result.status in {"error", "awaiting_login"} and (
        "登录窗口" in message or _browser_profile_in_use_error(message)
    )


def _apply_connection_result(
    account: PublishingAccount,
    result: ConnectionResult,
    *,
    checked_at: datetime,
) -> None:
    account.connection_status = result.status
    account.account_name = result.account_name or account.account_name
    account.last_checked_at = checked_at
    account.last_error = result.error_message
    if result.status != "connected":
        account.enabled = False
    account.version += 1
    account.updated_at = checked_at


async def check_due_publishing_accounts(
    session_factory: async_sessionmaker[AsyncSession],
    settings: Settings,
    *,
    now: datetime | None = None,
    limit: int = 5,
) -> int:
    """Check a small batch of connected accounts whose 24-hour check is due."""

    current = _as_utc(now or datetime.now(UTC))
    cutoff = current - PUBLISHING_SESSION_CHECK_INTERVAL
    async with session_factory() as database:
        account_ids = list(
            (
                await database.scalars(
                    select(PublishingAccount.id)
                    .where(
                        PublishingAccount.connection_status == "connected",
                        (
                            PublishingAccount.last_checked_at.is_(None)
                            | (PublishingAccount.last_checked_at <= cutoff)
                        ),
                    )
                    .order_by(
                        PublishingAccount.last_checked_at.asc(),
                        PublishingAccount.created_at.asc(),
                    )
                    .limit(max(1, min(limit, 5))),
                )
            ).all(),
        )

    checked_count = 0
    for account_id in account_ids:
        account_lock = _ACCOUNT_LOCKS.setdefault(account_id, asyncio.Lock())
        async with account_lock:
            async with session_factory() as database:
                account = await database.get(PublishingAccount, account_id)
                if account is None or account.connection_status != "connected":
                    continue
                if account.last_checked_at and _as_utc(account.last_checked_at) > cutoff:
                    continue
                channel_id = account.channel_id

            result = await verify_publishing_account(
                settings,
                channel_id=channel_id,
                account_id=account_id,
            )
            if _profile_is_busy(result):
                LOGGER.info(
                    "publishing_session_check_deferred",
                    extra={
                        "event": "publishing_session_check_deferred",
                        "publishing_account_id": str(account_id),
                        "channel_id": channel_id,
                    },
                )
                continue

            async with session_factory() as database:
                account = await database.get(PublishingAccount, account_id)
                if account is None or account.connection_status != "connected":
                    continue
                if account.last_checked_at and _as_utc(account.last_checked_at) > cutoff:
                    continue
                _apply_connection_result(account, result, checked_at=current)
                await database.commit()
                checked_count += 1
                LOGGER.info(
                    "publishing_session_checked",
                    extra={
                        "event": "publishing_session_checked",
                        "publishing_account_id": str(account_id),
                        "channel_id": channel_id,
                        "connection_status": result.status,
                    },
                )
    return checked_count


async def _lookup_pending_publication(
    settings: Settings,
    *,
    account: PublishingAccount,
    version: ContentVersion,
    submitted_at: datetime | None,
    now: datetime,
) -> PublishResult:
    platform = PUBLISHING_PLATFORMS_BY_ID[account.channel_id]
    if settings.publishing_execution_mode == "fixed_mock":
        return PublishResult(
            status="published",
            public_url=f"{platform['official_url']}mock/{version.id.hex}",
            platform_post_id=f"mock-{account.id.hex}-{version.id.hex}",
        )
    try:
        from playwright.async_api import async_playwright
    except ImportError:
        return _missing_management_record_result(
            account.channel_id,
            submitted_at=submitted_at,
            now=now,
        )
    try:
        async with async_playwright() as playwright:
            context = await playwright.chromium.launch_persistent_context(
                str(_browser_profile_path(settings, account.channel_id, account.id)),
                executable_path=str(_browser_executable(settings)),
                headless=True,
                args=["--disable-blink-features=AutomationControlled"],
            )
            try:
                result = await _generic_management_status(
                    context,
                    channel_id=account.channel_id,
                    title=_platform_submission_title(account.channel_id, version.title),
                )
                if result is None:
                    return _missing_management_record_result(
                        account.channel_id,
                        submitted_at=submitted_at,
                        now=now,
                    )
                if result.status != "published" or result.public_url is None:
                    return result
                integrity_error = await _verify_public_article(
                    context,
                    channel_id=account.channel_id,
                    public_url=result.public_url,
                    expected_body=_markdown_to_plain_text(version.body_markdown),
                )
                if integrity_error is not None:
                    return PublishResult(
                        status="failed",
                        public_url=result.public_url,
                        error_message=(
                            f"{platform['name']}已发布，但公开页验收失败，"
                            f"{integrity_error}。请到平台修正该文章。"
                        )[:500],
                    )
                post_id = None
                match = re.search(
                    r"(?:article/|/a/|rain/a/|page/|[?&]id=)([0-9A-Za-z_-]+)",
                    result.public_url,
                )
                if match:
                    post_id = match.group(1)
                return PublishResult(
                    status="published",
                    public_url=result.public_url,
                    platform_post_id=post_id,
                )
            finally:
                await context.close()
    except Exception as error:
        if not _browser_profile_in_use_error(str(error)):
            LOGGER.warning(
                "pending_publication_check_failed",
                extra={
                    "event": "pending_publication_check_failed",
                    "publication_version_id": str(version.id),
                    "channel_id": account.channel_id,
                },
            )
        return _missing_management_record_result(
            account.channel_id,
            submitted_at=submitted_at,
            now=now,
        )


async def check_pending_publications(
    session_factory: async_sessionmaker[AsyncSession],
    settings: Settings,
    *,
    now: datetime | None = None,
    limit: int = 5,
) -> int:
    """Reconcile submitted articles with the platform content-management page."""

    current = _as_utc(now or datetime.now(UTC))
    cutoff = current - PENDING_PUBLICATION_CHECK_INTERVAL
    async with session_factory() as database:
        publication_ids = list(
            (
                await database.scalars(
                    select(ContentPublication.id)
                    .where(
                        ContentPublication.status == "pending_review",
                        ContentPublication.updated_at <= cutoff,
                    )
                    .order_by(ContentPublication.updated_at.asc())
                    .limit(max(1, min(limit, 5))),
                )
            ).all(),
        )

    checked_count = 0
    for publication_id in publication_ids:
        async with session_factory() as database:
            publication = await database.get(ContentPublication, publication_id)
            if publication is None or publication.status != "pending_review":
                continue
            account = (
                await database.get(PublishingAccount, publication.publishing_account_id)
                if publication.publishing_account_id is not None
                else None
            )
            version = await database.get(ContentVersion, publication.version_id)
            if account is None or version is None:
                publication.status = "failed"
                publication.error_message = "审核状态复查所需的账号或文章版本不存在"
                publication.updated_at = current
                await database.commit()
                checked_count += 1
                continue
            account_id = account.id

        account_lock = _ACCOUNT_LOCKS.setdefault(account_id, asyncio.Lock())
        async with account_lock:
            result = await _lookup_pending_publication(
                settings,
                account=account,
                version=version,
                submitted_at=publication.submitted_at,
                now=current,
            )

        async with session_factory() as database:
            publication = await database.get(ContentPublication, publication_id)
            account = await database.get(PublishingAccount, account_id)
            document = (
                await database.get(ContentDocument, publication.document_id)
                if publication is not None
                else None
            )
            if publication is None or publication.status != "pending_review":
                continue
            if result.status in {"needs_login", "needs_verification"}:
                if account is not None:
                    _apply_connection_result(
                        account,
                        ConnectionResult(
                            status=result.status,
                            account_name=account.account_name,
                            error_message=result.error_message,
                        ),
                        checked_at=current,
                    )
                publication.updated_at = current
            elif result.status == "pending_review":
                publication.error_message = None
                publication.updated_at = current
            else:
                publication.status = result.status
                publication.public_url = result.public_url
                publication.platform_post_id = result.platform_post_id
                publication.error_message = result.error_message
                publication.updated_at = current
                if result.status == "published":
                    publication.published_at = current
                    if document is not None:
                        document.version += 1
                        document.updated_at = current
                elif document is not None:
                    document.updated_at = current
                if account is not None and _publication_result_requires_account_pause(result):
                    account.connection_status = "error"
                    account.enabled = False
                    account.last_error = result.error_message
                    account.version += 1
            await database.commit()
            checked_count += 1
    return checked_count


async def process_publication_job(
    session_factory: async_sessionmaker[AsyncSession],
    job: Job,
    settings: Settings,
) -> bool:
    async with session_factory() as database:
        current = await database.scalar(
            select(Job).where(Job.id == job.id).with_for_update(),
        )
        if current is None or current.status != "running":
            return True
        document_id = UUID(str(current.payload["document_id"]))
        version_id = UUID(str(current.payload["version_id"]))
        publication_id = UUID(str(current.payload["publication_id"]))
        account_id = UUID(str(current.payload["publishing_account_id"]))
        document = await database.get(ContentDocument, document_id)
        version = await database.get(ContentVersion, version_id)
        publication = await database.get(ContentPublication, publication_id)
        account = await database.get(PublishingAccount, account_id)
        if (
            document is None
            or version is None
            or publication is None
            or account is None
            or version.document_id != document.id
            or publication.publishing_account_id != account.id
        ):
            current.status = "failed"
            current.error_message = "文章发布数据不存在"
            current.completed_at = utc_now()
            current.lease_until = None
            await database.commit()
            return True
        platform = PUBLISHING_PLATFORMS_BY_ID.get(account.channel_id)
        if platform is None:
            publication.status = "failed"
            publication.error_message = "发布平台不存在或已停用"
            current.status = "failed"
            current.error_message = publication.error_message
            current.progress = 100
            current.completed_at = utc_now()
            current.lease_until = None
            await database.commit()
            return True
        if not account.enabled or account.connection_status != "connected":
            publication.status = "needs_login"
            publication.error_message = (
                f"请先在渠道配置连接并启用{platform['name']}账号“{account.display_name}”"
            )
            current.status = "failed"
            current.error_message = publication.error_message
            current.progress = 100
            current.completed_at = utc_now()
            current.lease_until = None
            await database.commit()
            return True

        publishing_spec = get_publishing_platform_spec(account.channel_id)
        if publishing_spec is None:
            publication.status = "failed"
            publication.error_message = f"{platform['name']}尚未配置发布规范"
            current.status = "failed"
            current.error_message = publication.error_message
            current.progress = 100
            current.completed_at = utc_now()
            current.lease_until = None
            await database.commit()
            return True
        if publishing_spec.daily_publication_limit is not None:
            local_now = datetime.now(ZoneInfo("Asia/Shanghai"))
            local_day_start = local_now.replace(hour=0, minute=0, second=0, microsecond=0)
            submitted_count = int(
                await database.scalar(
                    select(func.count(ContentPublication.id)).where(
                        ContentPublication.publishing_account_id == account.id,
                        ContentPublication.submitted_at >= local_day_start.astimezone(UTC),
                        ContentPublication.status.in_(
                            ("publishing", "pending_review", "published"),
                        ),
                    ),
                )
                or 0
            )
            limit_error = _publishing_daily_limit_error(
                account.channel_id,
                submitted_count,
            )
            if limit_error is not None:
                publication.status = "failed"
                publication.error_message = limit_error
                current.status = "failed"
                current.error_message = limit_error
                current.progress = 100
                current.completed_at = utc_now()
                current.lease_until = None
            await database.commit()
            return True

        if settings.publishing_execution_mode != "fixed_mock" and account.channel_id == "toutiao":
            cadence_message = await toutiao_publication_guard(
                database,
                account.id,
                exclude_publication_id=publication.id,
            )
            if cadence_message is not None:
                publication.status = "failed"
                publication.error_message = cadence_message
                current.status = "failed"
                current.error_message = cadence_message
                current.progress = 100
                current.completed_at = utc_now()
                current.lease_until = None
                await database.commit()
                return True

        account_lock = _ACCOUNT_LOCKS.setdefault(account.id, asyncio.Lock())
        async with account_lock:
            connection = await verify_publishing_account(
                settings,
                channel_id=account.channel_id,
                account_id=account.id,
            )
        if _profile_is_busy(connection):
            publication.status = "failed"
            publication.error_message = connection.error_message
            current.status = "failed"
            current.error_message = connection.error_message
            current.progress = 100
            current.completed_at = utc_now()
            current.lease_until = None
            await database.commit()
            return True

        checked_at = datetime.now(UTC)
        _apply_connection_result(account, connection, checked_at=checked_at)
        if connection.status != "connected":
            publication.status = (
                connection.status
                if connection.status in {"needs_login", "needs_verification"}
                else "failed"
            )
            publication.error_message = (
                connection.error_message or f"{platform['name']}发布前登录状态检测未通过"
            )
            current.status = "failed"
            current.error_message = publication.error_message
            current.progress = 100
            current.completed_at = checked_at
            current.lease_until = None
            await database.commit()
            return True

        publication.status = "publishing"
        publication.submitted_at = utc_now()
        publication.error_message = None
        current.progress = 30
        selected_image_ids = await select_content_image_ids(
            database,
            document.client_id,
            count=publishing_spec.image.target_body_images,
        )
        version.image_material_ids = list(
            dict.fromkeys(
                [*list(version.image_material_ids or []), *selected_image_ids],
            ),
        )[: publishing_spec.image.target_body_images]
        body_image_paths = await resolve_content_image_paths(
            database,
            storage_root=settings.storage_root,
            client_id=document.client_id,
            material_ids=list(version.image_material_ids or []),
        )
        await database.commit()
        snapshot = await database.get(FactSnapshot, version.fact_snapshot_id)
        client = await database.get(Client, document.client_id)
        brief = await database.get(ContentBrief, document.brief_id)
        if snapshot is None or client is None:
            result = PublishResult(status="failed", error_message="文章封面所需资料不存在")
        else:
            from app.content import _article_cover_context

            brand_name, context_line = _article_cover_context(client, snapshot)
            cover = article_cover_path(
                settings.storage_root,
                document_id=document.id,
                version_id=version.id,
                style="azure",
            )
            await asyncio.to_thread(
                ensure_article_cover,
                cover,
                title=version.title,
                brand_name=brand_name,
                context_line=context_line,
                style="azure",
                background_path=body_image_paths[0] if body_image_paths else None,
            )
            prepared_root = (
                settings.storage_root
                / "publishing"
                / "prepared"
                / account.channel_id
                / str(version.id)
            )
            try:
                prepared_cover = await asyncio.to_thread(
                    prepare_publishing_image,
                    cover,
                    prepared_root / "cover",
                    channel_id=account.channel_id,
                    role="cover",
                )
                prepared_body_images = [
                    await asyncio.to_thread(
                        prepare_publishing_image,
                        image_path,
                        prepared_root / f"body-{index}",
                        channel_id=account.channel_id,
                        role="body",
                    )
                    for index, image_path in enumerate(body_image_paths, start=1)
                ]
            except PublishingImageError as error:
                result = PublishResult(
                    status="failed",
                    error_message=f"{platform['name']}发布图片处理失败: {error}",
                )
            else:
                topics = _sohu_topic_candidates(
                    brand_name=client.short_name or client.standard_name,
                    target_keywords=list(brief.target_keywords) if brief is not None else [],
                )
                async with account_lock:
                    result = await publish_with_browser_adapter(
                        settings,
                        channel_id=account.channel_id,
                        account_id=account.id,
                        document_id=document.id,
                        version_id=version.id,
                        title=version.title,
                        body_markdown=version.body_markdown,
                        cover_path=prepared_cover,
                        body_image_paths=prepared_body_images,
                        topic_candidates=topics,
                        content_type=brief.content_type if brief is not None else None,
                    )
        publication = await database.get(ContentPublication, publication_id)
        current = await database.get(Job, job.id)
        account = await database.get(PublishingAccount, account_id)
        if publication is None or current is None or account is None:
            return True
        publication.status = result.status
        publication.public_url = result.public_url
        publication.platform_post_id = result.platform_post_id
        publication.error_message = result.error_message
        publication.updated_at = utc_now()
        current.progress = 100
        current.lease_until = None
        current.completed_at = utc_now()
        if result.status in {"published", "pending_review"}:
            current.status = "succeeded"
            if result.status == "published":
                publication.published_at = utc_now()
                document.version += 1
                document.updated_at = utc_now()
        else:
            current.status = "failed"
            current.error_message = result.error_message or "发布失败"
            if _publication_result_requires_account_pause(result):
                account.connection_status = (
                    result.status
                    if result.status in {"needs_login", "needs_verification"}
                    else "error"
                )
                account.enabled = False
                account.last_error = result.error_message
                account.version += 1
        await database.commit()
        return True


def build_publishing_router(settings: Settings) -> APIRouter:
    router = APIRouter(prefix="/api/v1/publishing", tags=["publishing"])

    @router.get("/channels")
    async def list_publishing_channels(
        request: Request,
        database: DatabaseSession,
        authentication: Authenticated,
    ) -> Response:
        accounts = list(
            (
                await database.scalars(
                    select(PublishingAccount).order_by(
                        PublishingAccount.channel_id,
                        PublishingAccount.created_at,
                    ),
                )
            ).all(),
        )
        await asyncio.to_thread(_claim_legacy_toutiao_profile, settings, accounts)
        accounts_by_channel = {
            platform["id"]: [
                account for account in accounts if account.channel_id == platform["id"]
            ]
            for platform in PUBLISHING_PLATFORM_CATALOG
        }
        return success_response(
            request,
            {
                "items": [
                    _platform_data(platform, accounts_by_channel[platform["id"]])
                    for platform in PUBLISHING_PLATFORM_CATALOG
                ],
            },
        )

    @router.post("/channels/{channel_id}/accounts")
    async def create_publishing_account(
        request: Request,
        channel_id: str,
        body: PublishingAccountCreate,
        database: DatabaseSession,
        authentication: CsrfAuthenticated,
    ) -> Response:
        platform = PUBLISHING_PLATFORMS_BY_ID.get(channel_id)
        if platform is None:
            return error_response(
                request,
                status_code=422,
                code=42202,
                message="该渠道未接入自动发布",
            )
        account_count = await database.scalar(
            select(func.count(PublishingAccount.id)).where(
                PublishingAccount.channel_id == channel_id,
            ),
        )
        if int(account_count or 0) >= MAX_ACCOUNTS_PER_PLATFORM:
            return error_response(
                request,
                status_code=409,
                code=40902,
                message=f"{platform['name']}最多连接 {MAX_ACCOUNTS_PER_PLATFORM} 个账号",
            )
        account = PublishingAccount(
            channel_id=channel_id,
            display_name=body.display_name.strip(),
        )
        database.add(account)
        try:
            await database.commit()
        except IntegrityError:
            await database.rollback()
            return error_response(
                request,
                status_code=409,
                code=40902,
                message="同一平台内账号备注不能重复",
            )
        return success_response(request, _account_data(account), status_code=201)

    @router.patch("/accounts/{account_id}")
    async def update_publishing_account(
        request: Request,
        account_id: UUID,
        body: PublishingAccountUpdate,
        database: DatabaseSession,
        authentication: CsrfAuthenticated,
    ) -> Response:
        account = await _publishing_account(database, account_id, for_update=True)
        if account is None:
            return error_response(request, status_code=404, code=40401, message="发布账号不存在")
        if account.version != body.version:
            return error_response(
                request,
                status_code=409,
                code=40901,
                message="账号配置已更新，请刷新后重试",
            )
        if body.enabled is True and account.connection_status != "connected":
            return error_response(
                request,
                status_code=422,
                code=42202,
                message="请先登录并检测连接，再启用自动发布",
            )
        if body.display_name is not None:
            account.display_name = body.display_name.strip()
        if body.enabled is not None:
            account.enabled = body.enabled
        account.version += 1
        account.updated_at = utc_now()
        try:
            await database.commit()
        except IntegrityError:
            await database.rollback()
            return error_response(
                request,
                status_code=409,
                code=40902,
                message="同一平台内账号备注不能重复",
            )
        return success_response(request, _account_data(account))

    @router.post("/accounts/{account_id}/login-window")
    async def launch_account_login(
        request: Request,
        account_id: UUID,
        database: DatabaseSession,
        authentication: CsrfAuthenticated,
    ) -> Response:
        account = await _publishing_account(database, account_id, for_update=True)
        if account is None:
            return error_response(request, status_code=404, code=40401, message="发布账号不存在")
        try:
            await asyncio.to_thread(
                open_login_window,
                settings,
                account.channel_id,
                account.id,
            )
        except RuntimeError as error:
            account.connection_status = "error"
            account.last_error = str(error)[:500]
            account.enabled = False
            account.version += 1
            await database.commit()
            return error_response(
                request,
                status_code=422,
                code=42202,
                message=str(error),
            )
        account.connection_status = "awaiting_login"
        account.last_error = None
        account.enabled = False
        account.version += 1
        account.updated_at = utc_now()
        await database.commit()
        return success_response(request, _account_data(account))

    @router.post("/accounts/{account_id}/test")
    async def test_account_connection(
        request: Request,
        account_id: UUID,
        database: DatabaseSession,
        authentication: CsrfAuthenticated,
    ) -> Response:
        account = await _publishing_account(database, account_id, for_update=True)
        if account is None:
            return error_response(request, status_code=404, code=40401, message="发布账号不存在")
        result = await verify_publishing_account(
            settings,
            channel_id=account.channel_id,
            account_id=account.id,
        )
        _apply_connection_result(account, result, checked_at=datetime.now(UTC))
        await database.commit()
        return success_response(request, _account_data(account))

    return router


async def queue_document_publication(
    *,
    database: AsyncSession,
    document: ContentDocument,
    version: ContentVersion,
    account: PublishingAccount,
    idempotency_key: str,
) -> Job:
    publication = await database.scalar(
        select(ContentPublication).where(
            ContentPublication.document_id == document.id,
            ContentPublication.version_id == version.id,
            ContentPublication.publishing_account_id == account.id,
        ),
    )
    if publication is None:
        publication = ContentPublication(
            document_id=document.id,
            version_id=version.id,
            publishing_account_id=account.id,
            channel_id=account.channel_id,
            status="queued",
        )
        database.add(publication)
        await database.flush()
    else:
        publication.status = "queued"
        publication.error_message = None
        publication.updated_at = utc_now()
    job = Job(
        id=uuid4(),
        client_id=document.client_id,
        material_id=None,
        job_type="content_publish",
        status="queued",
        idempotency_key=f"{idempotency_key}:{account.id}"[:200],
        payload={
            "document_id": str(document.id),
            "version_id": str(version.id),
            "publication_id": str(publication.id),
            "channel_id": account.channel_id,
            "publishing_account_id": str(account.id),
        },
        progress=0,
        attempts=0,
        max_attempts=1,
    )
    database.add(job)
    try:
        await database.commit()
    except IntegrityError:
        await database.rollback()
        existing = await database.scalar(
            select(Job).where(
                Job.client_id == document.client_id,
                Job.job_type == "content_publish",
                Job.idempotency_key == f"{idempotency_key}:{account.id}"[:200],
            ),
        )
        if existing is None:
            raise
        return existing
    return job
