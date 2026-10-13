# T-050 Developer Verification — 2026-08-04

## Reproduction evidence

- Old recorded URL: `https://www.sohu.com/a/1056188288_122960875`.
- Actual 2026-08-04 URL: `https://www.sohu.com/a/1058760902_122960875`.
- Actual public `<article>` contained about 77 visible text characters and 4 `<img>` nodes.
- Intercepted pre-submit Sohu payload contained the full article and 2 image tags, locating the
  loss after submission rather than in the initial editor fill.
- Toutiao business response and platform notice reported a 7-day mute for repeated batch
  publication of low-quality content.

## Automated checks

- `pytest tests/publishing/test_publishing_adapter.py tests/content/test_content_api.py -q`
  — 91 passed.
- `ruff check app/publishing.py app/content.py app/prompt_templates.py ...` — passed.
- `mypy app/publishing.py app/content.py app/prompt_templates.py` — passed.

## Runtime checks

- `GET /api/v1/health/ready` — ready.
- Worker process count — 1; heartbeat current.
- Prompt templates contain the new information-increment and anti-template rules.
- Sohu local record points to the actual URL and is `failed`, not `published`.
- The affected Sohu document is `blocked` by the new platform-quality check.
- Toutiao default account is disabled and marked `error` during the mute period.

## External-side-effect boundary

No additional external article was published during the final verification. The existing broken
Sohu article was not deleted because external deletion is destructive and requires a separate
explicit decision.

## Verification ownership

This is developer evidence only. Independent Tester verification and Product Manager acceptance
remain outstanding.
