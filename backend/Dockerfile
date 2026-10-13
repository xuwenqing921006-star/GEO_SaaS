FROM python:3.13-slim@sha256:6771159cd4fa5d9bba1258caf0b82e6b73458c694d178ad97c5e925c2d0e1a91

COPY --from=ghcr.io/astral-sh/uv:0.11.30@sha256:93b61e21202b1dab861092748e46bbd6e0e41dd84f59b9174efd2353186e1b47 /uv /uvx /bin/

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

RUN apt-get update \
    && apt-get install --yes --no-install-recommends fonts-wqy-zenhei \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --gid 10001 app \
    && useradd --uid 10001 --gid app --create-home --shell /usr/sbin/nologin app \
    && mkdir -p /app /data \
    && chown 10001:10001 /app /data

WORKDIR /app
USER app

COPY --chown=app:app pyproject.toml uv.lock ./
COPY --chown=app:app app app
COPY --chown=app:app migrations migrations
COPY --chown=app:app alembic.ini ./
RUN uv sync --frozen --no-dev

USER root
RUN rm -f /bin/uv /bin/uvx \
    && dpkg --purge --force-depends --force-remove-essential perl-base

ENV PATH="/app/.venv/bin:${PATH}"
EXPOSE 8000

USER app
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
