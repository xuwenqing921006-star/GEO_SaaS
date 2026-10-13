import hmac
from collections import defaultdict, deque
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from threading import Lock
from time import monotonic
from typing import Annotated

from fastapi import APIRouter, Cookie, Depends, Header, Request, Response, Security
from fastapi.security import APIKeyCookie
from pydantic import BaseModel, Field
from sqlalchemy import delete, select

from app.config import Settings
from app.database import DatabaseSession, Owner, OwnerSession
from app.responses import ApiFailure, error_response, success_response
from app.security import create_secret, hash_password, secret_digest, verify_password

SESSION_IDLE = timedelta(hours=12)
SESSION_ABSOLUTE = timedelta(days=7)
LOGIN_WINDOW_SECONDS = 300.0
LOGIN_ATTEMPTS = 5
MAX_LOGIN_BUCKETS = 10_000
DUMMY_PASSWORD_HASH = hash_password("TimingOnlyPassword2026!")
SESSION_COOKIE = APIKeyCookie(name="geo_session", auto_error=False)


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


class LoginInput(BaseModel):
    username: str = Field(min_length=3, max_length=64)
    password: str = Field(min_length=12, max_length=128)


class PasswordInput(BaseModel):
    current_password: str = Field(min_length=12, max_length=128)
    new_password: str = Field(min_length=12, max_length=128)


@dataclass(frozen=True)
class AuthenticatedSession:
    owner: Owner
    session: OwnerSession
    csrf_token: str | None


class LoginRateLimiter:
    def __init__(self) -> None:
        self._attempts: dict[str, deque[float]] = defaultdict(deque)
        self._inflight: dict[str, int] = defaultdict(int)
        self._lock = Lock()

    def reserve(self, key: str) -> bool:
        with self._lock:
            now = monotonic()
            if key not in self._attempts and len(self._attempts) >= MAX_LOGIN_BUCKETS:
                expired_keys = [
                    bucket_key
                    for bucket_key, bucket in self._attempts.items()
                    if self._inflight[bucket_key] == 0
                    and (not bucket or now - bucket[-1] > LOGIN_WINDOW_SECONDS)
                ]
                for bucket_key in expired_keys:
                    self._attempts.pop(bucket_key, None)
                    self._inflight.pop(bucket_key, None)
                if len(self._attempts) >= MAX_LOGIN_BUCKETS:
                    return False
            attempts = self._attempts[key]
            while attempts and now - attempts[0] > LOGIN_WINDOW_SECONDS:
                attempts.popleft()
            if len(attempts) + self._inflight[key] >= LOGIN_ATTEMPTS:
                return False
            self._inflight[key] += 1
            return True

    def complete(self, key: str, *, failed: bool | None) -> None:
        with self._lock:
            self._inflight[key] = max(0, self._inflight[key] - 1)
            if failed is True:
                self._attempts[key].append(monotonic())
            elif failed is False:
                self._attempts.pop(key, None)
            if not self._attempts[key] and self._inflight[key] == 0:
                self._attempts.pop(key, None)
                self._inflight.pop(key, None)


async def require_session(
    request: Request,
    database: DatabaseSession,
    geo_session: Annotated[str | None, Security(SESSION_COOKIE)],
    geo_csrf: str | None = Cookie(default=None),
) -> AuthenticatedSession:
    if not geo_session:
        raise ApiFailure(
            status_code=401,
            code=40101,
            message="登录已失效，请重新登录",
        )
    token_hash = secret_digest(geo_session)
    row = await database.execute(
        select(OwnerSession, Owner)
        .join(Owner, Owner.id == OwnerSession.owner_id)
        .where(OwnerSession.token_hash == token_hash),
    )
    pair = row.one_or_none()
    now = datetime.now(UTC)
    if pair is None:
        raise ApiFailure(
            status_code=401,
            code=40101,
            message="登录已失效，请重新登录",
        )
    owner_session, owner = pair
    if (
        now >= _aware(owner_session.idle_expires_at)
        or now
        >= _aware(
            owner_session.absolute_expires_at,
        )
        or owner_session.session_version != owner.session_version
    ):
        await database.delete(owner_session)
        await database.commit()
        raise ApiFailure(
            status_code=401,
            code=40101,
            message="登录已失效，请重新登录",
        )
    owner_session.last_seen_at = now
    owner_session.idle_expires_at = min(
        now + SESSION_IDLE,
        _aware(owner_session.absolute_expires_at),
    )
    await database.commit()
    csrf_token = (
        geo_csrf
        if geo_csrf and hmac.compare_digest(owner_session.csrf_hash, secret_digest(geo_csrf))
        else None
    )
    return AuthenticatedSession(owner=owner, session=owner_session, csrf_token=csrf_token)


async def require_csrf(
    request: Request,
    authentication: Annotated[
        AuthenticatedSession,
        Depends(require_session),
    ],
    csrf_token: str | None = Header(default=None, alias="X-CSRF-Token"),
) -> AuthenticatedSession:
    if not csrf_token or not hmac.compare_digest(
        authentication.session.csrf_hash,
        secret_digest(csrf_token),
    ):
        raise ApiFailure(
            status_code=403,
            code=40301,
            message="安全校验失败，请刷新页面",
        )
    return AuthenticatedSession(
        owner=authentication.owner,
        session=authentication.session,
        csrf_token=csrf_token,
    )


Authenticated = Annotated[
    AuthenticatedSession,
    Depends(require_session),
]
CsrfAuthenticated = Annotated[
    AuthenticatedSession,
    Depends(require_csrf),
]


def _session_data(authentication: AuthenticatedSession, csrf_token: str) -> dict[str, object]:
    return {
        "user": {
            "id": str(authentication.owner.id),
            "username": authentication.owner.username,
            "display_name": authentication.owner.display_name,
        },
        "csrf_token": csrf_token,
        "expires_at": _aware(authentication.session.idle_expires_at).isoformat(),
    }


def build_auth_router(settings: Settings) -> APIRouter:
    router = APIRouter(prefix="/api/v1/auth", tags=["auth"])
    limiter = LoginRateLimiter()

    @router.post("/login")
    async def login(request: Request, body: LoginInput, database: DatabaseSession) -> Response:
        client_key = request.client.host if request.client else "unknown"
        if not limiter.reserve(client_key):
            return error_response(
                request,
                status_code=429,
                code=42901,
                message="登录尝试过多，请稍后再试",
                retryable=True,
            )
        credential_failed: bool | None = None
        try:
            owner = await database.scalar(
                select(Owner).where(Owner.username == body.username).with_for_update(),
            )
            candidate_hash = owner.password_hash if owner is not None else DUMMY_PASSWORD_HASH
            password_valid = verify_password(body.password, candidate_hash)
            if owner is None or not password_valid:
                credential_failed = True
                return error_response(
                    request,
                    status_code=401,
                    code=40102,
                    message="用户名或密码错误",
                )
            credential_failed = False
            session_token = create_secret()
            csrf_token = create_secret()
            now = datetime.now(UTC)
            owner_session = OwnerSession(
                token_hash=secret_digest(session_token),
                owner_id=owner.id,
                csrf_hash=secret_digest(csrf_token),
                session_version=owner.session_version,
                created_at=now,
                last_seen_at=now,
                idle_expires_at=now + SESSION_IDLE,
                absolute_expires_at=now + SESSION_ABSOLUTE,
            )
            database.add(owner_session)
            await database.commit()
        finally:
            limiter.complete(client_key, failed=credential_failed)
        authentication = AuthenticatedSession(owner, owner_session, csrf_token)
        response = success_response(request, _session_data(authentication, csrf_token))
        response.set_cookie(
            "geo_session",
            session_token,
            max_age=int(SESSION_ABSOLUTE.total_seconds()),
            httponly=True,
            secure=settings.app_env == "production",
            samesite="lax",
            path="/",
        )
        response.set_cookie(
            "geo_csrf",
            csrf_token,
            max_age=int(SESSION_ABSOLUTE.total_seconds()),
            httponly=False,
            secure=settings.app_env == "production",
            samesite="lax",
            path="/",
        )
        return response

    @router.get("/session")
    async def session(
        request: Request,
        database: DatabaseSession,
        authentication: Authenticated,
    ) -> Response:
        csrf_token = authentication.csrf_token or create_secret()
        response = success_response(request, _session_data(authentication, csrf_token))
        if authentication.csrf_token is None:
            authentication.session.csrf_hash = secret_digest(csrf_token)
            await database.commit()
            response.set_cookie(
                "geo_csrf",
                csrf_token,
                max_age=int(SESSION_ABSOLUTE.total_seconds()),
                httponly=False,
                secure=settings.app_env == "production",
                samesite="lax",
                path="/",
            )
        return response

    @router.delete("/session")
    async def logout(
        request: Request,
        database: DatabaseSession,
        authentication: CsrfAuthenticated,
    ) -> Response:
        await database.delete(authentication.session)
        await database.commit()
        response = success_response(request, {"logged_out": True})
        response.delete_cookie("geo_session", path="/")
        response.delete_cookie("geo_csrf", path="/")
        return response

    @router.put("/password")
    async def change_password(
        request: Request,
        body: PasswordInput,
        database: DatabaseSession,
        authentication: CsrfAuthenticated,
    ) -> Response:
        owner = await database.scalar(
            select(Owner)
            .where(Owner.id == authentication.owner.id)
            .with_for_update()
            .execution_options(populate_existing=True),
        )
        if owner is None:
            raise ApiFailure(
                status_code=401,
                code=40101,
                message="登录已失效，请重新登录",
            )
        if body.new_password == body.current_password or not verify_password(
            body.current_password,
            owner.password_hash,
        ):
            return error_response(
                request,
                status_code=422,
                code=40001,
                message="新密码不符合安全要求",
            )
        owner.password_hash = hash_password(body.new_password)
        owner.session_version += 1
        await database.execute(
            delete(OwnerSession).where(OwnerSession.owner_id == authentication.owner.id),
        )
        await database.commit()
        response = success_response(
            request,
            {"changed": True, "relogin_required": True},
        )
        response.delete_cookie("geo_session", path="/")
        response.delete_cookie("geo_csrf", path="/")
        return response

    return router
