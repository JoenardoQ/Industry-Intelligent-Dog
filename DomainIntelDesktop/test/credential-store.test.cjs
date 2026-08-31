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
    model:'deepseek-chat', apiKey:'never-plaintext', apiBase:'https://api.deepseek.com/' })
  const file = fs.readFileSync(path.join(directory, 'provider-config.json'), 'utf8')
  assert.equal(file.includes('never-plaintext'), false)
  assert.deepEqual(status, { secureStorage:true, configured:true, provider:'deepseek',
    model:'deepseek-chat', apiBase:'https://api.deepseek.com' })
  assert.equal(readConfig(directory, storage()).apiKey, 'never-plaintext')
  fs.rmSync(directory, { recursive:true })
})

test('refuses storage when OS encryption is unavailable', () => {
  const directory = fs.mkdtempSync(path.join(__dirname, '.tmp-credential-'))
  assert.throws(() => saveConfig(directory, storage(false), {
    provider:'openai', model:'gpt', apiKey:'secret' }), /安全存储不可用/)
  assert.equal(publicStatus(directory, storage(false)).configured, false)
  fs.rmSync(directory, { recursive:true })
})

test('rejects insecure remote API bases', () => {
  assert.throws(() => validate({provider:'qwen',model:'qwen',apiKey:'x',
    apiBase:'http://remote.example/v1'}), /HTTPS/)
})

test('clears only the provider credential file', () => {
  const directory = fs.mkdtempSync(path.join(__dirname, '.tmp-credential-'))
  saveConfig(directory, storage(), {provider:'openai',model:'gpt',apiKey:'secret'})
  assert.deepEqual(clearConfig(directory), {configured:false})
  assert.equal(fs.existsSync(path.join(directory, 'provider-config.json')), false)
  fs.rmSync(directory, {recursive:true})
})
