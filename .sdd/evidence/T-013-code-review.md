# T-013 Independent Code Review

Date: 2026-07-28  
Role: Reviewer  
Round: 5 (final)  
Verdict: **PASS**

## Findings

No P0, P1, or P2 findings remain in the reviewed T-013 scope.

## Final blocking issue rechecked

The fourth-round nested request-contract drift is closed:

- `docs/api-contracts.md:512-527` now defines input-specific
  `QuestionInput` and `ManualSampleInput` DTOs that match the payloads accepted
  by the application.
- `docs/api-contracts.md:1078-1106` uses those input DTOs for question-set
  create/patch and manual-sample requests, including the conditional
  `raw_answer` / `failure_reason` business rules.
- `backend/tests/test_openapi_contract.py:190-203,339-364` recursively
  dereferences the nested request arrays for:
  - question-set create `questions[]`;
  - nullable question-set patch `questions[]`;
  - manual-sample `items[]`.
- Each nested component is checked for exact title, property set, and required
  set against the documented DTO.

Independent generated-OpenAPI verification confirmed:

| Request item | Properties | Required |
| --- | --- | --- |
| `QuestionInput` | `id`, `text`, `family`, `is_brand_query`, `target_level`, `priority` | `text`, `family` |
| `ManualSampleInput` | `sample_id`, `status`, `raw_answer`, `failure_reason`, `asked_at` | `sample_id`, `status`, `asked_at` |

The PATCH nullable `anyOf` wrapper is correctly unwrapped to the array before
the item component is checked.

## Contract and automated verification

- Generated OpenAPI contains the approved 66 operations.
- Named success DTO properties and required fields are checked against
  `api-contracts.md`.
- Success statuses, exact documented error sets, cookie-authentication
  exclusions, and CSRF header presence are checked.
- `EvaluationRequest`, `ProviderSettingRequest`, and the three nested
  monitoring request-item contracts are checked at field and requiredness
  level.
- `SuggestedMonitoringActionData` is concrete; the monitoring response path no
  longer uses a generic dictionary for suggested actions.
- Targeted contract and monitoring run: **5 passed**.
- `ruff` on the changed contract test: **pass**.
- `mypy` on the changed contract test: **pass**.
- Supplied full gate evidence:
  - frontend unit: **40 passed**;
  - backend: **150 passed**, 5 environment-gated skips;
  - format, lint, typecheck, build, and Compose validation: pass;
  - full Web E2E: **11/11 passed**.

The Starlette/httpx deprecation warning emitted by the targeted run is
non-blocking for this release candidate; it does not change test behavior or
the published contract.

## Coverage, security, and release package

- Whole-backend statement coverage: **84.6498%** (gate 75%).
- Fixed core-module branch coverage: **88.2716%** (gate 85%).
- Final API/Worker digest:
  `sha256:03feb5e36a0d76415413b2875836f394f34cd00a6d6fe756cdc095da63771aab`.
- Docker Scout evidence for the final shipped images remains 0 Critical and
  0 High.
- Build bases are digest-pinned and production services are version-tagged.

## Recovery, observability, and UI regression

Previously reviewed release-hardening paths remain closed:

- weekly backup remains independently restorable after daily retention;
- restore uses the documented versioned Backup/Restore image;
- PostgreSQL restore is transactional and post-validation failure restores the
  pre-restore database;
- file replacement failure restores the previous file tree;
- restore drops all capabilities except `CHOWN` and `DAC_OVERRIDE`, uses a
  read-only root filesystem, avoids inherited archive ownership, and returns
  business files to UID/GID 10001;
- the drill uses a random Compose project and guarded cleanup;
- Worker actively probes API readiness and evaluates readiness, queue, budget,
  storage, and backup alerts;
- `/internal/metrics` remains private;
- MonitoringView refreshes and awaits all prerequisite queries before creating
  a monitoring batch.

The supplied final isolated production drill reports:

- `production_drill=passed`
- `weekly_backup_after_daily_removal=passed`
- `transactional_restore=passed`
- `post_validation_database_rollback=passed`
- `internal_metrics=passed`
- `https_hsts=passed`

## Reviewer conclusion

T-013 meets its stated engineering acceptance criteria and is ready for
independent Tester verification. Reviewer has not changed task status and has
not performed a production deployment, paid-service activation, or external
write.
