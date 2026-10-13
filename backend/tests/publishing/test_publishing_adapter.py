from collections.abc import Iterable
from typing import Any

import pytest

import app.publishing as publishing_module
from app.publishing import (
    BAIJIA_COVER_CONFIRM_PATTERN,
    ConnectionResult,
    _baijia_title_error,
    _browser_profile_in_use_error,
    _classify_management_publication,
    _confirm_toutiao_logged_out,
    _has_new_pending_review_marker,
    _insert_sohu_body_images,
    _markdown_to_plain_text,
    _missing_management_record_result,
    _missing_submission_receipt_result,
    _netease_publish_prerequisite_error,
    _netease_scan_requires_final_submit,
    _netease_title_error,
    _platform_submission_title,
    _platform_validation_error,
    _profile_is_busy,
    _public_article_integrity_error,
    _publication_result_requires_account_pause,
    _publishing_daily_limit_error,
    _select_management_public_url,
    _set_baijia_work_settings,
    _set_toutiao_work_declaration,
    _sohu_article_attribute,
    _sohu_topic_candidates,
    _sohu_upload_images_from_dialog,
    _toutiao_business_result,
    _toutiao_cover_is_configured,
    _toutiao_image_paragraph_index,
    _toutiao_validation_error,
    _upload_platform_cover,
    _wait_for_toutiao_confirm_button,
    _wait_for_toutiao_cover_entry,
)


@pytest.mark.unit
def test_penguin_title_is_not_silently_truncated_and_daily_limit_is_explicit() -> None:
    title = "即墨孩子学画画前可以先观察的五个课堂细节与家庭配合方法"

    assert _platform_submission_title("penguin", title) == title
    assert _publishing_daily_limit_error("penguin", 4) is None
    assert _publishing_daily_limit_error("penguin", 5) == (
        "企鹅号账号今日已提交 5 篇文章，达到平台每日上限"
    )


class FakeLocator:
    def __init__(
        self,
        *,
        texts: Iterable[str] = (),
        visibility: Iterable[bool] = (True,),
    ) -> None:
        self._texts = iter(texts)
        self._visibility = iter(visibility)
        self._last_visibility = False

    @property
    def first(self) -> "FakeLocator":
        return self

    async def count(self) -> int:
        return 1

    async def is_visible(self) -> bool:
        try:
            self._last_visibility = next(self._visibility)
        except StopIteration:
            pass
        return self._last_visibility

    async def inner_text(self, **_kwargs: Any) -> str:
        return next(self._texts)


class FakePage:
    def __init__(self, locators: dict[str, FakeLocator]) -> None:
        self.url = "https://mp.toutiao.com/profile_v4/graphic/publish"
        self.locators = locators
        self.wait_calls = 0

    def locator(self, selector: str) -> FakeLocator:
        return self.locators[selector]

    async def wait_for_timeout(self, _milliseconds: int) -> None:
        self.wait_calls += 1


class FakeCheckbox:
    def __init__(self, checked: bool = False) -> None:
        self.checked = checked

    async def count(self) -> int:
        return 1

    async def is_checked(self) -> bool:
        return self.checked


class FakeDeclarationLabel:
    def __init__(self, checkbox: FakeCheckbox) -> None:
        self.checkbox = checkbox

    @property
    def first(self) -> "FakeDeclarationLabel":
        return self

    async def count(self) -> int:
        return 1

    async def is_visible(self) -> bool:
        return True

    def locator(self, selector: str) -> "FakeDeclarationLabel | FakeCheckbox":
        if selector.startswith("xpath=") and "input" not in selector:
            return self
        return self.checkbox

    async def click(self, **kwargs: Any) -> None:
        assert not kwargs or kwargs == {"force": True, "timeout": 5000}
        self.checkbox.checked = not self.checkbox.checked


class FakeDeclarationPage:
    def __init__(self) -> None:
        self.ai_checkbox = FakeCheckbox()
        self.viewpoint_checkbox = FakeCheckbox()
        self.wait_calls = 0
        self.labels = {
            "引用AI": FakeDeclarationLabel(self.ai_checkbox),
            "个人观点，仅供参考": FakeDeclarationLabel(self.viewpoint_checkbox),
        }

    def get_by_text(self, text: str, *, exact: bool) -> FakeDeclarationLabel:
        assert exact
        return self.labels[text]

    async def wait_for_timeout(self, _milliseconds: int) -> None:
        self.wait_calls += 1


class FakeBaijiaSettingsPage(FakeDeclarationPage):
    def __init__(self) -> None:
        super().__init__()
        self.podcast_checkbox = FakeCheckbox(checked=True)
        self.dynamic_checkbox = FakeCheckbox(checked=False)
        self.labels.update(
            {
                "采用AI生成内容": FakeDeclarationLabel(self.ai_checkbox),
                "自动生成播客": FakeDeclarationLabel(self.podcast_checkbox),
                "图文转动态": FakeDeclarationLabel(self.dynamic_checkbox),
            },
        )


class FakeConfirmLocator:
    def __init__(self, visibility: Iterable[bool]) -> None:
        self._visibility = iter(visibility)
        self._last_visibility = False

    async def count(self) -> int:
        return 1

    def nth(self, _index: int) -> "FakeConfirmLocator":
        return self

    async def is_visible(self) -> bool:
        try:
            self._last_visibility = next(self._visibility)
        except StopIteration:
            pass
        return self._last_visibility


class FakeConfirmPage:
    def __init__(self) -> None:
        self.confirm = FakeConfirmLocator((False, False, True))
        self.absent = FakeConfirmLocator((False,))
        self.wait_calls = 0

    def get_by_role(self, _role: str, *, name: Any) -> FakeConfirmLocator:
        return self.confirm if name.pattern == r"^\s*确认发布\s*$" else self.absent

    async def wait_for_timeout(self, _milliseconds: int) -> None:
        self.wait_calls += 1


class FakeSohuImageCounter:
    def __init__(self) -> None:
        self.calls = 0

    async def count(self) -> int:
        self.calls += 1
        return 0 if self.calls == 1 else 1


class FakeSohuEditor:
    def __init__(self) -> None:
        self.images = FakeSohuImageCounter()

    def locator(self, selector: str) -> FakeSohuImageCounter:
        assert selector == "img"
        return self.images


class FakeSohuImageButton:
    def __init__(self) -> None:
        self.clicked = False

    async def click(self) -> None:
        self.clicked = True


class FakeSohuPage:
    def __init__(self) -> None:
        self.wait_calls = 0

    async def wait_for_timeout(self, _milliseconds: int) -> None:
        self.wait_calls += 1


class FakeSohuUploadLocator:
    def __init__(self, selector: str = "dialog") -> None:
        self.selector = selector
        self.uploaded: list[str] = []
        self.clicked = False

    @property
    def last(self) -> "FakeSohuUploadLocator":
        return self

    def locator(self, selector: str) -> "FakeSohuUploadLocator":
        return FakeSohuUploadLocator(f"{self.selector} {selector}")

    def filter(self, **_kwargs: object) -> "FakeSohuUploadLocator":
        return self

    async def count(self) -> int:
        return 1

    async def is_visible(self) -> bool:
        return True

    async def set_input_files(self, paths: list[str]) -> None:
        self.uploaded = paths

    async def get_attribute(self, name: str) -> str:
        assert name == "class"
        return "button positive-button"

    async def click(self) -> None:
        self.clicked = True

    async def wait_for(self, **_kwargs: object) -> None:
        return None


class FakeSohuUploadPage:
    def __init__(self) -> None:
        self.dialog = FakeSohuUploadLocator()

    def locator(self, selector: str) -> FakeSohuUploadLocator:
        assert selector == ".win-mask:visible"
        return self.dialog

    async def wait_for_timeout(self, _milliseconds: int) -> None:
        return None


class FakePlatformCoverLocator:
    def __init__(self, page: "FakePlatformCoverPage", selector: str) -> None:
        self.page = page
        self.selector = selector

    @property
    def first(self) -> "FakePlatformCoverLocator":
        return self

    @property
    def last(self) -> "FakePlatformCoverLocator":
        return self

    async def count(self) -> int:
        if "cover" in self.selector and 'input[type="file"]' in self.selector:
            return 1
        if "cover" in self.selector and (
            " img" in self.selector or "background-image" in self.selector
        ):
            return int(self.page.uploaded)
        return 0

    async def is_visible(self) -> bool:
        return bool(await self.count())

    async def set_input_files(self, path: str) -> None:
        self.page.uploaded = True
        self.page.uploaded_path = path


class FakePlatformCoverPage:
    def __init__(self) -> None:
        self.uploaded = False
        self.uploaded_path: str | None = None
        self.queried: list[str] = []

    def locator(self, selector: str) -> FakePlatformCoverLocator:
        self.queried.append(selector)
        return FakePlatformCoverLocator(self, selector)

    async def wait_for_timeout(self, _milliseconds: int) -> None:
        return None


def test_sohu_uses_the_real_article_editor_instead_of_content_management() -> None:
    assert publishing_module._publishing_editor_url("sohu").endswith(
        "/contentManagement/news/addarticle?contentStatus=1",
    )


def test_baijia_uses_the_article_editor_instead_of_the_home_page() -> None:
    assert publishing_module._publishing_editor_url("baijia").endswith(
        "/builder/rc/edit?type=news",
    )


def test_netease_uses_the_current_article_publisher_and_management_routes() -> None:
    assert publishing_module._publishing_editor_url("netease") == (
        "https://mp.163.com/#/article-publish"
    )
    platform = publishing_module.PUBLISHING_PLATFORMS_BY_ID["netease"]
    assert platform["login_url"] == "https://mp.163.com/"
    assert platform["manage_url"] == "https://mp.163.com/#/content-manage"


def test_baijia_title_uses_the_live_editor_limit_without_silent_truncation() -> None:
    assert _baijia_title_error("百家号") is None
    assert _baijia_title_error("标题" * 32) is None
    assert _baijia_title_error("标题" * 32 + "多") == "百家号标题最多支持 64 个字"


def test_netease_title_uses_safe_live_limit_without_silent_truncation() -> None:
    title = "即墨孩子第一次学画画，家长先看课堂反馈是否具体再决定"

    assert _netease_title_error(title) is None
    assert _platform_submission_title("netease", title) == title
    assert _netease_title_error("网易" * 32) is None
    assert _netease_title_error("网易" * 32 + "号") == "网易号标题最多支持 64 个字"


@pytest.mark.asyncio
async def test_baijia_enables_ai_declaration_and_disables_unrequested_derivatives() -> None:
    page = FakeBaijiaSettingsPage()

    error = await _set_baijia_work_settings(page)

    assert error is None
    assert page.ai_checkbox.checked
    assert not page.podcast_checkbox.checked
    assert not page.dynamic_checkbox.checked


@pytest.mark.parametrize("channel_id", ("baijia",))
@pytest.mark.asyncio
async def test_unverified_platform_cover_upload_never_uses_a_global_file_input(
    channel_id: str,
    tmp_path,
) -> None:
    cover = tmp_path / "cover.jpg"
    cover.write_bytes(b"prepared-cover")
    page = FakePlatformCoverPage()

    error = await _upload_platform_cover(
        page,
        channel_id=channel_id,
        cover_path=cover,
    )

    assert error is None
    assert page.uploaded_path == str(cover)
    assert 'input[type="file"]' not in page.queried


@pytest.mark.parametrize(
    ("channel_id", "page_text", "expected"),
    (
        ("baijia", "请选择封面", "百家号文章封面未设置"),
        ("netease", "正文不能为空", "网易号未识别到文章正文"),
        ("sohu", "请选择属性", "搜狐号要求选择文章属性"),
    ),
)
def test_platform_validation_reports_the_specific_publish_step(
    channel_id: str,
    page_text: str,
    expected: str,
) -> None:
    assert _platform_validation_error(channel_id, page_text) == expected


@pytest.mark.parametrize(
    ("page_text", "expected"),
    (
        ("账号被禁言", "网易号账号已被禁言，当前无法发布文章"),
        ("请先通过实名认证再发布内容", "网易号账号需要先完成实名认证"),
        ("今日发布数量已达最大值", "网易号账号今日发布数量已达上限"),
        ("您的账号已被下线", "网易号账号已被下线，当前无法发布文章"),
    ),
)
def test_netease_reports_account_prerequisites_before_submission(
    page_text: str,
    expected: str,
) -> None:
    assert _netease_publish_prerequisite_error(page_text) == expected


@pytest.mark.asyncio
async def test_sohu_image_upload_confirms_the_visible_local_upload_panel(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    image = tmp_path / "image.jpg"
    image.write_bytes(b"image")
    page = FakeSohuUploadPage()
    captured_selector = ""

    async def first_visible(locator: FakeSohuUploadLocator) -> FakeSohuUploadLocator:
        nonlocal captured_selector
        captured_selector = locator.selector
        return locator

    monkeypatch.setattr(publishing_module, "_first_visible_locator", first_visible)

    error = await _sohu_upload_images_from_dialog(page, [image], purpose="正文")

    assert error is None
    assert ".local-upload .bottom-buttons .positive-button" in captured_selector


def test_sohu_topics_use_search_keyword_and_brand_without_question_suffixes() -> None:
    assert _sohu_topic_candidates(
        brand_name="莱恩美术",
        target_keywords=["即墨少儿美术哪家好"],
    ) == ["即墨少儿美术", "莱恩美术"]


@pytest.mark.parametrize(
    ("content_type", "expected"),
    (
        ("local_recommendation", "测评盘点"),
        ("practical_guide", "经验教程"),
        ("faq", "知识科普"),
        ("case_study", "见闻记录"),
    ),
)
def test_sohu_attribute_matches_article_form(content_type: str, expected: str) -> None:
    assert _sohu_article_attribute(title="本地服务文章", content_type=content_type) == expected


@pytest.mark.asyncio
async def test_sohu_inserts_one_body_image_to_avoid_image_flooding(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    first = tmp_path / "first.png"
    second = tmp_path / "second.png"
    extra = tmp_path / "extra.png"
    for path in (first, second, extra):
        path.write_bytes(b"test-image")
    page = FakeSohuPage()
    editor = FakeSohuEditor()
    image_button = FakeSohuImageButton()
    positioned = False
    uploaded: list[object] = []

    async def position(*_args: object, **_kwargs: object) -> None:
        nonlocal positioned
        positioned = True

    async def first_visible(*_args: object, **_kwargs: object) -> FakeSohuImageButton:
        return image_button

    async def upload(
        _page: object,
        image_paths: list[object],
        *,
        purpose: str,
    ) -> None:
        assert purpose == "正文"
        uploaded.extend(image_paths)
        return None

    monkeypatch.setattr(publishing_module, "_position_toutiao_image_cursor", position)
    monkeypatch.setattr(publishing_module, "_first_visible", first_visible)
    monkeypatch.setattr(publishing_module, "_sohu_upload_images_from_dialog", upload)

    error = await _insert_sohu_body_images(
        page,
        editor,
        [first, second, extra],
    )

    assert error is None
    assert positioned is True
    assert image_button.clicked is True
    assert uploaded == [first]


@pytest.mark.asyncio
async def test_sohu_stops_before_publish_when_body_image_is_not_available(tmp_path) -> None:

    error = await _insert_sohu_body_images(
        FakeSohuPage(),
        FakeSohuEditor(),
        [],
    )

    assert error == "搜狐号发布需要 1 张企业图片，当前未找到可用图片"


def test_sohu_management_link_must_match_the_exact_article_title() -> None:
    old_url = "https://www.sohu.com/a/1056188288_122960875"
    current_url = "https://www.sohu.com/a/1058760902_122960875"

    selected = _select_management_public_url(
        [
            (old_url, "在即墨选少儿美术培训，先看清这五个匹配维度"),
            (current_url, "在即墨给孩子选美术班，先看这五个标准再决定"),
        ],
        channel_id="sohu",
        title="在即墨给孩子选美术班，先看这五个标准再决定",
        excluded_urls=set(),
    )

    assert selected == current_url


def test_sohu_management_link_never_falls_back_to_an_old_article() -> None:
    old_url = "https://www.sohu.com/a/1056188288_122960875"

    selected = _select_management_public_url(
        [(old_url, "另一篇旧文章")],
        channel_id="sohu",
        title="今天的新文章",
        excluded_urls=set(),
    )

    assert selected is None


def test_sohu_management_record_distinguishes_pending_review_from_failure() -> None:
    result = _classify_management_publication(
        channel_id="sohu",
        row_text="在即墨给孩子选美术班 审核中 2026-08-04 21:30",
        public_url=None,
    )

    assert result.status == "pending_review"
    assert result.error_message is None


def test_sohu_management_record_only_marks_published_with_public_url() -> None:
    public_url = "https://www.sohu.com/a/1058760902_122960875"
    result = _classify_management_publication(
        channel_id="sohu",
        row_text="在即墨给孩子选美术班 已发布",
        public_url=public_url,
    )

    assert result.status == "published"
    assert result.public_url == public_url


def test_sohu_management_record_preserves_rejection_reason() -> None:
    result = _classify_management_publication(
        channel_id="sohu",
        row_text="在即墨给孩子选美术班 审核未通过 原因: 营销推广信息过多",
        public_url=None,
    )

    assert result.status == "rejected"
    assert result.error_message is not None
    assert "营销推广信息过多" in result.error_message


def test_baijia_management_link_matches_the_exact_article_title() -> None:
    current_url = "https://baijiahao.baidu.com/s?id=123456789"

    selected = _select_management_public_url(
        [
            (
                "https://baijiahao.baidu.com/s?id=987654321",
                "另一篇旧文章",
            ),
            (current_url, "即墨孩子学美术，第一次试听重点观察什么"),
        ],
        channel_id="baijia",
        title="即墨孩子学美术，第一次试听重点观察什么",
        excluded_urls=set(),
    )

    assert selected == current_url


def test_baijia_exact_title_management_record_is_pending_during_review() -> None:
    result = _classify_management_publication(
        channel_id="baijia",
        row_text="即墨孩子学美术，第一次试听重点观察什么 审核中",
        public_url=None,
    )

    assert result.status == "pending_review"


def test_netease_management_link_matches_exact_title_and_extracts_post_id() -> None:
    current_url = "https://www.163.com/dy/article/K6ABCDEF0514R9P4.html"
    selected = _select_management_public_url(
        [
            (
                "https://www.163.com/dy/article/K5OLD0000514R9P4.html",
                "另一篇旧文章",
            ),
            (current_url, "即墨孩子第一次学画画，试听时重点观察什么"),
        ],
        channel_id="netease",
        title="即墨孩子第一次学画画，试听时重点观察什么",
        excluded_urls=set(),
    )
    result = _classify_management_publication(
        channel_id="netease",
        row_text="即墨孩子第一次学画画，试听时重点观察什么 已发布",
        public_url=selected,
    )

    assert selected == current_url
    assert result.status == "published"
    assert result.platform_post_id == "K6ABCDEF0514R9P4"


def test_netease_success_receipt_is_detected_only_after_publish_action() -> None:
    success = "发布成功,即将跳转到内容管理页"

    assert _has_new_pending_review_marker(
        "netease",
        before_text="发布设置",
        after_text=success,
    )
    assert not _has_new_pending_review_marker(
        "netease",
        before_text=success,
        after_text=success,
    )


def test_netease_assistant_scan_requires_one_final_submit() -> None:
    before = "今日已发布0/6 预览 定时发布 发布"
    after = (
        "发文助手小易 为你提供1条建议 重新检测 "
        "标题 诊断通过 正文 建议正文包含3张以上图片展现效果更佳 封面图 诊断通过"
    )

    assert _netease_scan_requires_final_submit(before_text=before, after_text=after)
    assert not _netease_scan_requires_final_submit(before_text=after, after_text=after)


def test_baijia_published_management_record_extracts_platform_post_id() -> None:
    result = _classify_management_publication(
        channel_id="baijia",
        row_text="即墨孩子学美术，第一次试听重点观察什么 已发布",
        public_url="https://baijiahao.baidu.com/s?id=1873065780842414370",
    )

    assert result.status == "published"
    assert result.platform_post_id == "1873065780842414370"


def test_baijia_review_marker_must_appear_after_publish_action() -> None:
    assert _has_new_pending_review_marker(
        "baijia",
        before_text="发布设置",
        after_text="文章已提交，审核中",
    )
    assert not _has_new_pending_review_marker(
        "baijia",
        before_text="历史文章 审核中",
        after_text="历史文章 审核中",
    )


def test_baijia_missing_management_record_eventually_becomes_failed() -> None:
    now = publishing_module.datetime(2026, 8, 10, 0, tzinfo=publishing_module.UTC)

    recent = _missing_management_record_result(
        "baijia",
        submitted_at=now - publishing_module.timedelta(minutes=20),
        now=now,
    )
    expired = _missing_management_record_result(
        "baijia",
        submitted_at=now - publishing_module.timedelta(minutes=31),
        now=now,
    )
    sohu = _missing_management_record_result(
        "sohu",
        submitted_at=now - publishing_module.timedelta(hours=2),
        now=now,
    )

    assert recent.status == "pending_review"
    assert expired.status == "failed"
    assert expired.error_message is not None
    assert "未找到对应文章" in expired.error_message
    assert sohu.status == "pending_review"


def test_netease_missing_management_record_eventually_becomes_failed() -> None:
    now = publishing_module.datetime(2026, 8, 10, 0, tzinfo=publishing_module.UTC)

    recent = _missing_management_record_result(
        "netease",
        submitted_at=now - publishing_module.timedelta(minutes=20),
        now=now,
    )
    expired = _missing_management_record_result(
        "netease",
        submitted_at=now - publishing_module.timedelta(minutes=31),
        now=now,
    )

    assert recent.status == "pending_review"
    assert expired.status == "failed"
    assert expired.error_message is not None
    assert "内容管理" in expired.error_message


def test_penguin_management_link_and_two_hour_review_window() -> None:
    title = "孩子第一次学画画，家长可以观察哪些课堂细节"
    public_url = "https://new.qq.com/rain/a/20260810A01ABC00"
    selected = _select_management_public_url(
        [(public_url, title)],
        channel_id="penguin",
        title=title,
        excluded_urls=set(),
    )
    published = _classify_management_publication(
        channel_id="penguin",
        row_text=f"{title} 已发布",
        public_url=selected,
    )
    now = publishing_module.datetime(2026, 8, 10, 4, tzinfo=publishing_module.UTC)
    reviewing = _missing_management_record_result(
        "penguin",
        submitted_at=now - publishing_module.timedelta(minutes=90),
        now=now,
    )
    expired = _missing_management_record_result(
        "penguin",
        submitted_at=now - publishing_module.timedelta(hours=2, minutes=1),
        now=now,
    )

    assert published.status == "published"
    assert published.public_url == public_url
    assert published.platform_post_id == "20260810A01ABC00"
    assert reviewing.status == "pending_review"
    assert expired.status == "failed"


def test_baijia_without_submission_receipt_is_failed_not_pending() -> None:
    baijia = _missing_submission_receipt_result("baijia")
    sohu = _missing_submission_receipt_result("sohu")

    assert baijia.status == "failed"
    assert baijia.error_message is not None
    assert "没有找到对应文章" in baijia.error_message
    assert sohu.status == "pending_review"


def test_public_article_readback_rejects_truncated_body_and_excess_images() -> None:
    expected = "第一段提供判断方法。" + "这是有实际信息增量的正文。" * 80
    actual = "选择机构时可以先了解课程，再结合实际体验决定。"

    error = _public_article_integrity_error(
        expected,
        actual,
        image_count=4,
        max_images=2,
    )

    assert error is not None
    assert "正文不完整" in error


def test_public_article_readback_accepts_complete_article() -> None:
    expected = "第一段直接回答问题。" + "每一段都有新的判断信息。" * 60

    assert (
        _public_article_integrity_error(
            expected,
            expected,
            image_count=2,
            max_images=2,
        )
        is None
    )


@pytest.mark.parametrize("label", ("确定", "确定 (1)", "确定(2)"))
def test_baijia_cover_confirmation_accepts_live_selected_count(label: str) -> None:
    assert BAIJIA_COVER_CONFIRM_PATTERN.fullmatch(label)


@pytest.mark.parametrize("label", ("取消", "确认", "确定上传"))
def test_baijia_cover_confirmation_rejects_unrelated_actions(label: str) -> None:
    assert not BAIJIA_COVER_CONFIRM_PATTERN.fullmatch(label)


def test_platform_mute_result_pauses_the_publishing_account() -> None:
    assert _publication_result_requires_account_pause(
        publishing_module.PublishResult(
            status="rejected",
            error_message="头条号已被禁言，当前无法发布文章",
        ),
    )


@pytest.mark.parametrize(
    "browser_error",
    (
        (
            "BrowserType.launch_persistent_context: Target page, context or browser "
            "has been closed. Browser logs: Opening in existing browser session."
        ),
        (
            "BrowserType.launch_persistent_context: Target page, context or browser "
            "has been closed. Browser logs: process did exit: exitCode=21, signal=null"
        ),
    ),
)
def test_existing_login_window_is_reported_as_recoverable_profile_occupancy(
    browser_error: str,
) -> None:
    assert _browser_profile_in_use_error(browser_error)
    assert _profile_is_busy(
        ConnectionResult(
            status="awaiting_login",
            error_message="搜狐号登录窗口仍在打开，请关闭窗口后再次检测连接",
        ),
    )


def test_markdown_to_plain_text_preserves_article_meaning() -> None:
    rendered = _markdown_to_plain_text(
        "# 即墨少儿美术\n\n- 先看年龄匹配\n- 再看课程方向\n\n[了解机构](https://example.com)\n",
    )

    assert rendered == ("即墨少儿美术\n• 先看年龄匹配\n• 再看课程方向\n\n了解机构")


def test_toutiao_validation_error_reports_specific_missing_fields() -> None:
    assert _toutiao_validation_error("正文内容不能为空") == "头条号未识别到文章正文"
    assert _toutiao_validation_error("还需输入 2 个字") == "头条号标题还需输入 2 个字"
    assert _toutiao_validation_error("封面上传失败") == "头条号封面上传失败"
    assert _toutiao_validation_error("预览 确认发布") is None


def test_two_body_images_are_spaced_across_article_paragraphs() -> None:
    assert (
        _toutiao_image_paragraph_index(
            paragraph_count=6,
            image_index=0,
            image_count=2,
        )
        == 1
    )
    assert (
        _toutiao_image_paragraph_index(
            paragraph_count=6,
            image_index=1,
            image_count=2,
        )
        == 3
    )


@pytest.mark.asyncio
async def test_login_check_does_not_fail_on_a_transient_login_screen() -> None:
    page = FakePage(
        {
            "body": FakeLocator(
                texts=("扫码登录", "头条号创作中心"),
            ),
        },
    )

    assert not await _confirm_toutiao_logged_out(
        page,
        attempts=2,
        delay_ms=1,
    )
    assert page.wait_calls == 1


@pytest.mark.asyncio
async def test_login_check_requires_repeated_logged_out_observations() -> None:
    page = FakePage(
        {
            "body": FakeLocator(
                texts=("扫码登录", "手机号登录"),
            ),
        },
    )

    assert await _confirm_toutiao_logged_out(
        page,
        attempts=2,
        delay_ms=1,
    )


@pytest.mark.asyncio
async def test_cover_entry_waits_for_the_editor_to_render_it() -> None:
    entry = FakeLocator(visibility=(False, False, True))
    page = FakePage(
        {
            ".article-cover-add": entry,
            '.article-cover-images [class*="add"]': FakeLocator(visibility=(False,)),
            '.article-cover button:has-text("上传")': FakeLocator(visibility=(False,)),
            '.article-cover [aria-label*="上传"], .article-cover [title*="上传"]': FakeLocator(
                visibility=(False,),
            ),
        },
    )

    result = await _wait_for_toutiao_cover_entry(
        page,
        attempts=3,
        delay_ms=1,
    )

    assert result is entry
    assert page.wait_calls == 2


@pytest.mark.asyncio
async def test_existing_cover_is_a_valid_ready_state() -> None:
    page = FakePage(
        {
            ".article-cover-images img": FakeLocator(visibility=(True,)),
            '.article-cover-images [style*="background-image"]': FakeLocator(
                visibility=(False,),
            ),
        },
    )

    assert await _toutiao_cover_is_configured(page)


@pytest.mark.asyncio
async def test_ai_generated_article_keeps_required_platform_declaration() -> None:
    page = FakeDeclarationPage()

    await _set_toutiao_work_declaration(page)

    assert page.ai_checkbox.checked
    assert page.viewpoint_checkbox.checked
    assert page.wait_calls == 2


@pytest.mark.asyncio
async def test_confirm_step_waits_for_asynchronous_dialog() -> None:
    page = FakeConfirmPage()

    button = await _wait_for_toutiao_confirm_button(
        page,
        attempts=3,
        delay_ms=1,
    )

    assert button is page.confirm
    assert page.wait_calls == 2


def test_toutiao_business_error_reports_muted_account() -> None:
    result = _toutiao_business_result(
        [
            {"code": 7050, "message": "保存失败"},
            {"err_no": 3102, "message": "账号已被禁言无法发布文章，请先保存草稿"},
        ],
    )

    assert result is not None
    assert result.status == "rejected"
    assert result.error_message is not None
    assert "账号已被禁言" in result.error_message


def test_toutiao_business_error_reports_draft_save_failure() -> None:
    result = _toutiao_business_result(
        [{"err_no": 7050, "message": "保存失败"}],
    )

    assert result is not None
    assert result.status == "failed"
    assert result.error_message is not None
    assert "平台代码 7050" in result.error_message
