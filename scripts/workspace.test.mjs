import assert from 'node:assert/strict'
import { existsSync, readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import test from 'node:test'

const projectRoot = resolve(import.meta.dirname, '..')

const requiredFiles = [
  'compose.yaml',
  'compose.production.yaml',
  '.env.example',
  '.env.production.example',
  'ops/Caddyfile',
  'ops/Dockerfile.backup',
  'ops/Dockerfile.caddy',
  'ops/backup.sh',
  'ops/restore.sh',
  'docs/delivery/Operations-Runbook.md',
  'THIRD_PARTY_NOTICES.md',
  'frontend/Dockerfile',
  'frontend/src/App.vue',
  'backend/Dockerfile',
  'backend/postgres/Dockerfile',
  'backend/app/main.py',
  'backend/app/worker.py',
  'backend/migrations/versions/0001_empty_baseline.py',
]

test('contains the complete Web production baseline', () => {
  for (const relativePath of requiredFiles) {
    assert.equal(existsSync(resolve(projectRoot, relativePath)), true, `${relativePath} is required`)
  }
})

test('defines exactly the approved Compose services', () => {
  const compose = readFileSync(resolve(projectRoot, 'compose.yaml'), 'utf8')
  const serviceNames = [...compose.matchAll(/^  ([a-z][a-z0-9_-]+):\s*$/gm)].map((match) => match[1])

  assert.deepEqual(serviceNames, ['web', 'api', 'worker', 'db'])
  assert.match(compose, /geo-saas}\/postgres:\${APP_VERSION/)
  assert.match(compose, /dockerfile: backend\/postgres\/Dockerfile/)
})

test('defines the production HTTPS and encrypted backup baseline', () => {
  const productionCompose = readFileSync(
    resolve(projectRoot, 'compose.production.yaml'),
    'utf8',
  )
  const caddyfile = readFileSync(resolve(projectRoot, 'ops/Caddyfile'), 'utf8')
  const backupScript = readFileSync(resolve(projectRoot, 'ops/backup.sh'), 'utf8')
  const restoreScript = readFileSync(resolve(projectRoot, 'ops/restore.sh'), 'utf8')

  assert.match(productionCompose, /^  caddy:/m)
  assert.match(productionCompose, /^  backup:/m)
  assert.match(productionCompose, /^  restore:/m)
  assert.match(productionCompose, /"80:80"/)
  assert.match(productionCompose, /"443:443"/)
  assert.doesNotMatch(productionCompose, /5432:5432/)
  assert.match(caddyfile, /Strict-Transport-Security/)
  assert.match(caddyfile, /reverse_proxy web:8080/)
  assert.match(backupScript, /\bage\b/)
  assert.match(backupScript, /files\.sha256/)
  assert.match(backupScript, /backup-status\.json/)
  assert.match(backupScript, /BACKUP_FORCE_WEEKLY/)
  assert.doesNotMatch(backupScript, /\brclone\b/)
  assert.match(restoreScript, /CONFIRM_RESTORE/)
  assert.match(restoreScript, /sha256sum --check/)
  assert.match(restoreScript, /database_counts_mismatch/)
  assert.match(restoreScript, /--single-transaction/)
})

test('does not create an unapproved client', () => {
  const unapprovedClients = ['mobile', 'desktop', 'electron', 'miniprogram', 'miniapp']

  for (const client of unapprovedClients) {
    assert.equal(existsSync(resolve(projectRoot, client)), false, `${client} is outside the Web-only scope`)
  }
})
