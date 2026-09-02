'use strict'

const test = require('node:test')
const assert = require('node:assert/strict')
const fs = require('node:fs')
const path = require('node:path')
const { clearConfig, publicStatus, readConfig, saveConfig, validate } = require('../src/credential-store.cjs')

function storage(available = true) {
  return { isEncryptionAvailable: () => available,
    getSelectedStorageBackend: () => available ? 'kwallet' : 'basic_text',
    encryptString: value => Buffer.from(`sealed:${value}`),
    decryptString: value => value.toString().replace(/^sealed:/, '') }
}

test('persists only an encrypted API key and returns redaction-safe status', () => {
  const directory = fs.mkdtempSync(path.join(__dirname, '.tmp-credential-'))
  const status = saveConfig(directory, storage(), { provider:'deepseek',
    model:'deepseek-chat', apiKey:'never-plaintext', apiBase:'https://api.deepseek.com/',
    authType:'bearer' })
  const file = fs.readFileSync(path.join(directory, 'provider-config.json'), 'utf8')
  assert.equal(file.includes('never-plaintext'), false)
  assert.deepEqual(status, { secureStorage:true, configured:true, provider:'deepseek',
    model:'deepseek-chat', apiBase:'https://api.deepseek.com', authType:'bearer' })
  assert.equal(readConfig(directory, storage()).apiKey, 'never-plaintext')
  assert.equal(readConfig(directory, storage()).authType, 'bearer')
  fs.rmSync(directory, { recursive:true })
})

test('updates metadata for the same provider without decrypting or replacing its key', t => {
  const directory = fs.mkdtempSync(path.join(__dirname, '.tmp-credential-'))
  t.after(() => fs.rmSync(directory, {recursive:true, force:true}))
  const safeStorage = storage()
  saveConfig(directory, safeStorage, {provider:'openai',model:'gpt-5',apiKey:'secret',
    apiBase:'https://api.openai.com/v1',authType:'bearer'})
  const target = path.join(directory, 'provider-config.json')
  const before = JSON.parse(fs.readFileSync(target, 'utf8'))
  safeStorage.decryptString = () => { throw new Error('metadata update must not decrypt') }

  const status = saveConfig(directory, safeStorage, {provider:'openai',model:'gpt-5.1',
    apiKey:'',apiBase:'https://api.openai.com/v1',authType:'bearer'})
  const after = JSON.parse(fs.readFileSync(target, 'utf8'))

  assert.equal(after.encryptedKey, before.encryptedKey)
  assert.equal(status.model, 'gpt-5.1')
  assert.equal(status.configured, true)
})

test('requires a new key when changing the configured provider', t => {
  const directory = fs.mkdtempSync(path.join(__dirname, '.tmp-credential-'))
  t.after(() => fs.rmSync(directory, {recursive:true, force:true}))
  saveConfig(directory, storage(), {provider:'openai',model:'gpt-5',apiKey:'secret',
    apiBase:'https://api.openai.com/v1',authType:'bearer'})
  assert.throws(() => saveConfig(directory, storage(), {provider:'deepseek',
    model:'deepseek-chat',apiKey:'',apiBase:'https://api.deepseek.com',authType:'bearer'}),
  /更换 Provider.*API Key/)
})

test('reads known legacy v1 providers with manifest-compatible auth without rewriting', t => {
  const directory = fs.mkdtempSync(path.join(__dirname, '.tmp-credential-'))
  t.after(() => fs.rmSync(directory, {recursive:true, force:true}))
  const safeStorage = storage()
  const expected = {
    openai:'bearer', deepseek:'bearer', qwen:'bearer', azure:'api_key_header',
  }
  for (const [provider, authType] of Object.entries(expected)) {
    const secret = `legacy-${provider}-secret`
    const payload = {version:1, provider, model:`${provider}-model`,
      apiBase:`https://${provider}.example/v1`,
      encryptedKey:safeStorage.encryptString(secret).toString('base64')}
    const original = JSON.stringify(payload, null, 2)
    const target = path.join(directory, 'provider-config.json')
    fs.writeFileSync(target, original)
    const value = readConfig(directory, safeStorage)
    assert.equal(value.authType, authType)
    assert.equal(value.apiKey, secret)
    assert.equal(fs.readFileSync(target, 'utf8'), original)
    assert.equal(JSON.stringify(publicStatus(directory, safeStorage)).includes(secret), false)
  }
})

test('requires reconfiguration for legacy generic compatible authentication', t => {
  const directory = fs.mkdtempSync(path.join(__dirname, '.tmp-credential-'))
  t.after(() => fs.rmSync(directory, {recursive:true, force:true}))
  const safeStorage = storage()
  const target = path.join(directory, 'provider-config.json')
  const original = JSON.stringify({version:1, provider:'compatible_api', model:'custom',
    apiBase:'https://models.example/v1',
    encryptedKey:safeStorage.encryptString('generic-secret').toString('base64')}, null, 2)
  fs.writeFileSync(target, original)
  assert.equal(readConfig(directory, safeStorage), null)
  assert.deepEqual(publicStatus(directory, safeStorage), {secureStorage:true,
    configured:false,provider:'',model:'',apiBase:'',authType:''})
  assert.equal(fs.readFileSync(target, 'utf8'), original)
})

test('refuses storage when OS encryption is unavailable', () => {
  const directory = fs.mkdtempSync(path.join(__dirname, '.tmp-credential-'))
  assert.throws(() => saveConfig(directory, storage(false), {
    provider:'openai', model:'gpt', apiKey:'secret' }), /安全存储不可用/)
  assert.equal(publicStatus(directory, storage(false)).configured, false)
  fs.rmSync(directory, { recursive:true })
})

test('does not report an existing encrypted key as usable without OS encryption', t => {
  const directory = fs.mkdtempSync(path.join(__dirname, '.tmp-credential-'))
  t.after(() => fs.rmSync(directory, {recursive:true, force:true}))
  saveConfig(directory, storage(), {provider:'openai',model:'gpt',apiKey:'secret',
    authType:'bearer'})

  const status = publicStatus(directory, storage(false))

  assert.equal(status.secureStorage, false)
  assert.equal(status.configured, false)
  assert.equal(status.provider, 'openai')
})

test('rejects insecure remote API bases', () => {
  assert.throws(() => validate({provider:'qwen',model:'qwen',apiKey:'x',
    apiBase:'http://remote.example/v1',authType:'bearer'}), /HTTPS/)
})

test('rejects an unknown authentication type', () => {
  assert.throws(() => validate({provider:'compatible_api',model:'model',apiKey:'x',
    authType:'shell-secret'}), /认证类型/)
})

test('rejects authentication overrides for fixed providers', () => {
  assert.throws(() => validate({provider:'deepseek',model:'deepseek-chat',apiKey:'x',
    authType:'api_key_header'}), /认证类型/)
  assert.throws(() => validate({provider:'azure',model:'deployment',apiKey:'x',
    authType:'bearer'}), /认证类型/)
})

test('clears only the provider credential file', () => {
  const directory = fs.mkdtempSync(path.join(__dirname, '.tmp-credential-'))
  saveConfig(directory, storage(), {provider:'openai',model:'gpt',apiKey:'secret',
    authType:'bearer'})
  assert.deepEqual(clearConfig(directory), {configured:false})
  assert.equal(fs.existsSync(path.join(directory, 'provider-config.json')), false)
  fs.rmSync(directory, {recursive:true})
})
