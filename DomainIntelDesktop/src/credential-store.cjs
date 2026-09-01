'use strict'

const fs = require('node:fs')
const path = require('node:path')

const PROVIDER_ID = /^[a-z][a-z0-9_-]{0,79}$/
const AUTH_TYPES = new Set(['bearer', 'api_key_header'])
// Read-only migration contract for provider-config v1. These are the fixed
// authentication modes declared by capability_manifest; explicit/generic
// providers are intentionally absent because their mode cannot be inferred.
const LEGACY_V1_AUTH_TYPE_BY_PROVIDER = Object.freeze({
  openai: 'bearer', deepseek: 'bearer', qwen: 'bearer', azure: 'api_key_header',
})

function configPath(userData) { return path.join(userData, 'provider-config.json') }

function secureStorageAvailable(safeStorage) {
  if (!safeStorage || !safeStorage.isEncryptionAvailable()) return false
  return typeof safeStorage.getSelectedStorageBackend !== 'function' ||
    safeStorage.getSelectedStorageBackend() !== 'basic_text'
}

function publicStatus(userData, safeStorage) {
  const stored = readConfig(userData, safeStorage)
  return { secureStorage: secureStorageAvailable(safeStorage),
    configured: Boolean(stored?.apiKey), provider: stored?.provider || '',
    model: stored?.model || '', apiBase: stored?.apiBase || '',
    authType: stored?.authType || '' }
}

function validate(input) {
  const provider = String(input?.provider || '').trim().toLowerCase()
  const model = String(input?.model || '').trim()
  const apiKey = String(input?.apiKey || '').trim()
  const apiBase = String(input?.apiBase || '').trim()
  const authType = String(input?.authType || '').trim().toLowerCase()
  if (!PROVIDER_ID.test(provider)) throw new Error('API Provider ID 无效')
  if (!model) throw new Error('模型名称不能为空')
  if (!apiKey) throw new Error('API Key 不能为空')
  if (!AUTH_TYPES.has(authType)) throw new Error('认证类型必须是 bearer 或 api_key_header')
  const fixedAuthType = LEGACY_V1_AUTH_TYPE_BY_PROVIDER[provider]
  if (fixedAuthType && authType !== fixedAuthType) {
    throw new Error(`${provider} 认证类型必须是 ${fixedAuthType}`)
  }
  if (apiBase) {
    const parsed = new URL(apiBase)
    const local = ['localhost', '127.0.0.1', '::1'].includes(parsed.hostname)
    if (parsed.protocol !== 'https:' && !(parsed.protocol === 'http:' && local)) {
      throw new Error('非本机 API Base 必须使用 HTTPS')
    }
  }
  return { provider, model, apiKey, apiBase: apiBase.replace(/\/$/, ''), authType }
}

function saveConfig(userData, safeStorage, input) {
  if (!secureStorageAvailable(safeStorage)) throw new Error('系统安全存储不可用，拒绝保存 API Key')
  const value = validate(input)
  fs.mkdirSync(userData, { recursive: true })
  const target = configPath(userData)
  const temporary = `${target}.tmp`
  const payload = { version: 2, provider: value.provider, model: value.model,
    apiBase: value.apiBase, authType: value.authType,
    encryptedKey: safeStorage.encryptString(value.apiKey).toString('base64') }
  fs.writeFileSync(temporary, JSON.stringify(payload, null, 2), { mode: 0o600 })
  fs.renameSync(temporary, target)
  return publicStatus(userData, safeStorage)
}

function readConfig(userData, safeStorage) {
  const target = configPath(userData)
  if (!secureStorageAvailable(safeStorage) || !fs.existsSync(target)) return null
  try {
    const payload = JSON.parse(fs.readFileSync(target, 'utf8'))
    const authType = AUTH_TYPES.has(payload.authType) ? payload.authType :
      (payload.version === 1 ? LEGACY_V1_AUTH_TYPE_BY_PROVIDER[payload.provider] : '')
    if (!PROVIDER_ID.test(payload.provider) || !payload.model || !payload.encryptedKey ||
        !AUTH_TYPES.has(authType)) return null
    return { provider: payload.provider, model: payload.model,
      apiBase: String(payload.apiBase || ''), authType,
      apiKey: safeStorage.decryptString(Buffer.from(payload.encryptedKey, 'base64')) }
  } catch { return null }
}

function clearConfig(userData) {
  const target = configPath(userData)
  if (fs.existsSync(target)) fs.unlinkSync(target)
  return { configured: false }
}

module.exports = { clearConfig, publicStatus, readConfig, saveConfig,
  secureStorageAvailable, validate }
