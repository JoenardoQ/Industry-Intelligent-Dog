'use strict'

const test = require('node:test')
const assert = require('node:assert/strict')
const fs = require('node:fs')
const path = require('node:path')

const root = path.resolve(__dirname, '../..')
const read = relative => fs.readFileSync(path.join(root, relative), 'utf8')

test('architecture changes trigger all three native packages from the same revision', () => {
  const gate = read('.github/workflows/platform-gates.yml')
  for (const pathFilter of ['DomainIntelDesktop/**', 'DomainIntelApp/packaging/**',
    'DomainIntelApp/runtime/**', 'DomainIntelSearch/pyproject.toml',
    'DomainIntelSearch/src/**', 'DomainIntelSearch/intdog_core/**',
    'DomainIntelSearch/requirements.txt', 'DomainIntelSearch/scripts/**',
    'DomainIntelSearch/config/**', 'DomainIntelSearch/evaluation/**',
    'DomainIntelSearch/skills/**', 'DomainIntelWeb/api/**', 'DomainIntelWeb/src/**',
    'DomainIntelWeb/scripts/**', 'DomainIntelWeb/vite.config.*',
    'DomainIntelWeb/tsconfig*.json', 'DomainIntelWeb/index.html',
    'DomainIntelWeb/package.json', 'DomainIntelWeb/package-lock.json']) {
    assert.match(gate, new RegExp(pathFilter.replaceAll('*', '\\*')))
  }
  for (const platform of ['windows', 'macos', 'linux']) {
    assert.match(gate, new RegExp(`platform: ${platform}`))
  }
  assert.match(gate, /github\.sha/)
})

test('native package emits platform-scoped hashes reports and lifecycle evidence', () => {
  const workflow = read('.github/workflows/_native-package.yml')
  for (const contract of ['smoke_sidecar.py', 'worker --once', 'smoke_desktop.py',
    'native-smoke.json', 'sha256', 'test-results', 'inputs.revision']) {
    assert.ok(workflow.toLowerCase().includes(contract.toLowerCase()), contract)
  }
  assert.match(workflow, /name: intdog-\$\{\{ inputs\.platform \}\}/)
  assert.match(workflow, /if-no-files-found: error/)
})

test('beta remains prerelease and formal Windows and macOS builds require signing', () => {
  const reusable = read('.github/workflows/_native-package.yml')
  const release = read('.github/workflows/release-test.yml')
  assert.match(release, /release_candidate: true/)
  assert.match(release, /--draft=false --prerelease/)
  assert.match(release, /gh release view/)
  assert.match(release, /gh release upload.*--clobber/)
  assert.match(reusable, /inputs\.formal_release && inputs\.platform == 'windows'/)
  assert.match(reusable, /WINDOWS_CSC_LINK/)
  assert.match(reusable, /inputs\.formal_release && inputs\.platform == 'macos'/)
  for (const key of ['MACOS_CSC_LINK', 'APPLE_ID', 'APPLE_APP_SPECIFIC_PASSWORD', 'APPLE_TEAM_ID']) {
    assert.ok(reusable.includes(key), key)
  }
})

test('release issues are found reused or created and read back idempotently', () => {
  const reusable = read('.github/workflows/release-test.yml')
  for (const token of ['gh issue list', 'gh issue create', 'gh issue view',
    'platform-release:', '--state all']) assert.ok(reusable.includes(token), token)
  assert.match(reusable, /gh issue comment/)
})
