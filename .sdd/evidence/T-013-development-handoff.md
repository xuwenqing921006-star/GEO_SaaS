# T-013 Developer Handoff

Date: 2026-07-28  
Role: Developer  
Status: ready for independent review; Developer does not mark PASS

## Scope completed

- OpenAPI contract checks cover all current 66 API operations, including each
  operation's concrete success DTO, exact documented error set, cookie
  authentication and CSRF headers. Named response DTOs are compared against
  the documented field and required-field sets; monitoring and provider
  request bodies are also checked at field and requiredness level.
- Production security headers, HTTPS Caddy entry, read-only/minimum-privilege containers, log rotation and digest-pinned infrastructure images.
- Version-tagged Web/API/Worker/backup images and documented compatible-image rollback procedure.
- Encrypted PostgreSQL + business-file backup, retention, host-managed off-site
  ciphertext copy and guarded transactional restore.
- Internal Prometheus metrics and Worker-evaluated alerts cover readiness, queues,
  provider success/fallback/cost, budget, storage and backup health. The Worker
  actively probes the API readiness endpoint rather than evaluating a separate
  empty in-process request counter.
- Secret hygiene scan, dependency upgrades and Python/Node vulnerability audits.
- Opt-in 100,000-sample PostgreSQL capacity test.
- Production-like HTTPS smoke test for Chromium and Microsoft Edge.
- Release notes, operator user guide, known limitations and operations runbook.

## Defects found and fixed during hardening

1. Monitoring metrics loaded 100,000 sample IDs into an `IN` query and exceeded asyncpg's 32,767 argument limit. The endpoint now uses one selected-column outer join; the real 100,000-sample test returns 200 and satisfies the under-three-second endpoint assertion.
2. The production PostgreSQL wrapper returned the final strong-password predicate's `1` as the whole validation result, so `set -e` stopped every strong-password production startup. `validate_environment` now explicitly returns success after all checks.
3. Production images previously used implicit `latest` tags. Production Compose now uses `GEO_IMAGE_PREFIX` + `APP_VERSION`; the runbook records digest verification and compatible rollback.
4. The operations guide omitted Compose-based first-owner creation and exact master-key encoding. Both are now documented.
5. Weekly backup checksum files referenced the daily directory, so weekly-only
   recovery could not verify after daily retention removed the source. Weekly
   checksums are now generated relative to the weekly directory and verified in
   a forced weekly restore drill.
6. Restore could leave a partially restored database or file tree. PostgreSQL
   restore is now single-transaction; the existing database and business files
   are snapshotted and rolled back if any post-restore validation fails.
7. A restore with every Linux capability removed could not read the
   administrator-only decryption key or replace application-owned files. The
   one-shot restore profile now adds only `CHOWN` and `DAC_OVERRIDE`, extracts
   without inheriting archive owners, and explicitly returns restored files to
   the non-root application identity.
8. The monitoring action could be clicked a few milliseconds before the
   locked-question query completed, producing a false prerequisite error. The
   action now refreshes and awaits the client, question set, strategy and
   platform inputs before creating a monitoring batch.
9. Content briefs did not receive the platform recommendations created by the
   channel task, leaving channel-version generation unavailable. Strategy
   generation now provides safe defaults and the completed recommendation job
   writes the top four operator-publishable channels back to every brief.
10. Monitoring creation selected only P0 platforms. The Web now selects all
    active P0 and P1 platforms by default, supports all/P0/per-platform scope
    selection, and creates manual samples for Quark, WeChat, Douyin and Nami
    together with the existing consumer platforms.

## Reproducible evidence

- `pnpm check`: PASS
  - structure 4/4
  - frontend unit 40/40
  - backend 150 passed, 5 environment-gated tests skipped
  - format, lint, typecheck, frontend production build, Python compile and Compose config passed
- `pnpm --dir frontend test:e2e`: 11/11 Chromium Web journeys passed,
  including the monitoring prerequisite race regression
  against an isolated temporary database with `VITE_USE_MOCK=false`
- Capacity: `TEST_POSTGRES_DATABASE_URL=... pytest tests/performance/test_monitoring_capacity.py -m performance`
  - PASS with 100,000 real PostgreSQL samples and endpoint `< 3s` assertion
- Production images: Web, API, Worker, backup, Caddy and PostgreSQL build PASS as `0.1.0-rc13`
- Docker Scout SBOM/CVE indexing: every shipped image has 0 Critical and 0 High
  known vulnerabilities; image digests are recorded in
  `T-013-release-hardening.md`
- Production-like stack: PostgreSQL/API/Worker/Web healthy behind Caddy HTTPS
- T-013 Playwright production smoke: Chromium PASS, Microsoft Edge PASS
- Encrypted backup and isolated restore: PASS
  - outer encrypted checksum, archive checksum, database counts, schema `0013` and file SHA-256 verified
  - weekly archive remains independently restorable after daily archive removal
  - a deliberately inconsistent but checksum-valid archive is rejected and the
    pre-restore database is recovered
  - backup success/failure status is exported to internal metrics
- Compatible previous-image rollback:
  - previous schema-0013-compatible Web/API/Worker images healthy
  - Chromium HTTPS login smoke PASS
  - switched back to `0.1.0-rc13`; Chromium and Edge smoke PASS
- Incompatible older image:
  - correctly refused because it did not know schema revision `0013`; no downgrade was attempted
- `bandit -r backend/app -q`: PASS
- `pip-audit 2.10.1 --path backend/.venv/Lib/site-packages`: no known vulnerabilities; local project package skipped because it is not published to PyPI
- `pnpm audit --prod --audit-level high`: no known vulnerabilities
- Secret hygiene, typed OpenAPI contract and observability tests: PASS
- ECC V2 `pnpm doctor`: PASS
- Current local API `/api/v1/health/ready`: ready; database, storage and Worker all `ok`

## Coverage

`scripts/verify_backend_coverage.py` runs two reproducible passes:

- Whole backend statement coverage with Python 3.13 `sys.monitoring`: **84.83%**
  against the Test Plan gate of 75%.
- Fixed core module branch coverage with the branch tracer: **88.27%**
  against the Test Plan gate of 85%.

The split is required because Python 3.13's default tracer does not attribute
Starlette TestClient portal-thread endpoint execution correctly, while the
`sys.monitoring` core currently does not support branch measurement. The fixed
core boundary and commands are documented in `docs/delivery/Test-Plan.md`.

## Cleanup and data safety

- All T-013 temporary databases, Compose stacks, volumes, encrypted backups and ephemeral age private keys were removed.
- Existing `geo_saas_t008` customer data and configured provider keys were not changed.
- No production deployment, paid service activation or external write was performed.
