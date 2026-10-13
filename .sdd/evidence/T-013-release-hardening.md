# T-013 Release Hardening Evidence

Date: 2026-07-28  
Release candidate: `0.1.0-rc13`

## Contract and automated verification

- 66/66 API operations are checked against the approved endpoint contract.
- Each operation verifies method/path, its concrete success DTO, the exact
  documented error statuses and typed envelope, cookie authentication
  exclusions and CSRF requirements. Named DTO properties and required fields
  are compared to `api-contracts.md`; monitoring request-body properties and
  requiredness are exact. Undocumented framework-generated responses are
  removed from the published schema.
- Backend: 150 passed, 5 environment-gated tests skipped.
- Frontend: 40 unit tests passed.
- Whole-backend statements: 84.83% in the independent isolated rerun (gate
  75%; the Developer run reported 84.86%, so this evidence keeps the lower
  reproducible value).
- Fixed core-module branches: 88.27% (gate 85%, measured from the explicit
  branch metric rather than combined coverage).

## Production recovery drill

An isolated production Compose stack was started behind HTTPS. The drill:

1. confirmed readiness and the private metrics endpoint;
2. created an encrypted daily and forced-weekly backup;
3. removed the daily backup;
4. verified the weekly ciphertext checksum;
5. restored the weekly archive with transactional database restore;
6. submitted a checksum-valid archive with deliberately wrong database counts,
   confirmed that restore failed, and confirmed that the pre-restore database
   was automatically recovered;
7. revalidated application readiness and HSTS.

Result:

- `production_drill=passed`
- `weekly_backup_after_daily_removal=passed`
- `transactional_restore=passed`
- `post_validation_database_rollback=passed`
- `internal_metrics=passed`
- `https_hsts=passed`

## Container SBOM and vulnerability scan

Docker Scout indexed the SBOM and scanned the final local release images:

| Component | Image digest | Critical | High |
| --- | --- | ---: | ---: |
| API | `sha256:3794ec01cb0e50398faa401c0c0562e14c0fb99914370604d20f89bffe79605a` | 0 | 0 |
| Worker | `sha256:60033a07d20e4352fb107578a6d0ef71469ade5df5f954d6a535440b44cd3f8d` | 0 | 0 |
| Web | `sha256:17843c9824ca66908baf2c2847e9b467fb6153e9c0354d3cdb48ab4018c5c6ba` | 0 | 0 |
| Backup / Restore | `sha256:2f273587707614679a5e7bda40d5f56ad7cfc98450ef74f9c9f1fe1ed19296f0` | 0 | 0 |
| Caddy | `sha256:cc34d94a8f5d84c4649a60395c0f4d6192cf5a5ed200e60c7e058a2ec9b4ab3a` | 0 | 0 |
| PostgreSQL | `sha256:9def43566adf47cd1d4006e488b56300deb812ee494cf70e4356fafbdb5c1fd0` | 0 | 0 |

All build bases are digest-pinned. Runtime images use only the required
artifacts, and production services are version-tagged.

## Operational observability

The private `/internal/metrics` endpoint exports:

- request counts, error counts and duration totals;
- readiness failures;
- queue depth and oldest queued job;
- provider calls, successes, fallback use, token/cost totals and budget ratio;
- storage bytes/capacity ratio;
- backup state and age.

The Worker actively probes API readiness, then logs first trigger and
resolution for readiness, queue delay, budget, disk and backup alerts without
repeated alert spam. Caddy and the Web proxy do not expose this endpoint
publicly.
