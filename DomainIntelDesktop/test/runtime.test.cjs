'use strict'

const test = require('node:test')
const assert = require('node:assert/strict')
const path = require('node:path')
const { backendExecutable, runtimeEnvironment, isAllowedExternalUrl } = require('../src/runtime.cjs')

test('selects exactly one native sidecar name', () => {
  assert.equal(backendExecutable('/resources', 'win32'), path.join('/resources', 'backend', 'intdog-runtime.exe'))
  assert.equal(backendExecutable('/resources', 'linux'), path.join('/resources', 'backend', 'intdog-runtime'))
  assert.equal(backendExecutable('/resources', 'darwin'), path.join('/resources', 'backend', 'intdog-runtime'))
})

test('runtime environment keeps mutable data outside application resources', () => {
  const env = runtimeEnvironment({ resourcesPath: '/app/resources', userData: '/user/intdog',
    token: 'secret', executable: '/app/resources/backend/intdog-runtime' })
  assert.equal(env.DOMAIN_INTEL_DATA_ROOT, path.join('/user/intdog', 'data'))
  assert.equal(env.INTDOG_SEARCH_ROOT, path.join('/app/resources', 'intdog', 'DomainIntelSearch'))
  assert.equal(env.INTDOG_SEARCH_EXECUTABLE, '/app/resources/backend/intdog-runtime')
  assert.equal(env.INTDOG_DISABLE_EMAIL, '1')
})

test('runtime never injects a configured provider credential into child environment', () => {
  const env = runtimeEnvironment({ resourcesPath: '/app/resources', userData: '/user/intdog',
    token: 'secret', executable: '/app/backend', providerConfig: {
      provider: 'deepseek', model: 'deepseek-chat', apiKey: 'runtime-only',
      apiBase: 'https://api.deepseek.com', authType: 'bearer' } })
  assert.equal(JSON.stringify(env).includes('runtime-only'), false)
  assert.equal(env.INTDOG_LLM_PROVIDER, undefined)
  assert.equal(env.INTDOG_LLM_API_KEY, undefined)
})

test('runtime environment drops unrelated host credentials and the API session capability', () => {
  const previous = {DATABASE_URL:process.env.DATABASE_URL,GITHUB_PAT:process.env.GITHUB_PAT,
    INTDOG_SESSION_TOKEN:process.env.INTDOG_SESSION_TOKEN}
  process.env.DATABASE_URL = 'postgres://private'
  process.env.GITHUB_PAT = 'pat-canary'
  process.env.INTDOG_SESSION_TOKEN = 'old-session'
  try {
    const env = runtimeEnvironment({ resourcesPath:'/app/resources', userData:'/user/intdog',
      token:'new-session', executable:'/app/backend' })
    assert.equal(env.DATABASE_URL, undefined)
    assert.equal(env.GITHUB_PAT, undefined)
    assert.equal(env.INTDOG_SESSION_TOKEN, 'new-session')
  } finally {
    for (const [key,value] of Object.entries(previous)) {
      if (value === undefined) delete process.env[key]
      else process.env[key] = value
    }
  }
})

test('only HTTPS external links can leave the workbench', () => {
  assert.equal(isAllowedExternalUrl('https://example.com/report'), true)
  assert.equal(isAllowedExternalUrl('http://example.com'), false)
  assert.equal(isAllowedExternalUrl('file:///etc/passwd'), false)
  assert.equal(isAllowedExternalUrl('javascript:alert(1)'), false)
  assert.equal(isAllowedExternalUrl('not a url'), false)
})
