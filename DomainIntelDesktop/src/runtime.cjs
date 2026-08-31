'use strict'

const path = require('node:path')

function backendExecutable(resourcesPath, platform = process.platform) {
  const name = platform === 'win32' ? 'intdog-runtime.exe' : 'intdog-runtime'
  return path.join(resourcesPath, 'backend', name)
}

function runtimeEnvironment({ resourcesPath, userData, token, executable, providerConfig }) {
  const projectRoot = path.join(resourcesPath, 'intdog')
  const providerEnv = providerConfig ? {
    INTDOG_LLM_PROVIDER: providerConfig.provider,
    INTDOG_LLM_MODEL: providerConfig.model,
    INTDOG_LLM_API_KEY: providerConfig.apiKey,
    ...(providerConfig.apiBase ? { INTDOG_LLM_API_BASE: providerConfig.apiBase } : {}),
  } : {}
  return {
    ...process.env,
    INTDOG_PROJECT_ROOT: projectRoot,
    INTDOG_SEARCH_ROOT: path.join(projectRoot, 'DomainIntelSearch'),
    DOMAIN_INTEL_DATA_ROOT: path.join(userData, 'data'),
    INTDOG_SEARCH_EXECUTABLE: executable,
    INTDOG_SESSION_TOKEN: token,
    INTDOG_DISABLE_EMAIL: '1',
    PYTHONUTF8: '1',
    ...providerEnv,
  }
}

function isAllowedExternalUrl(value) {
  try {
    return new URL(value).protocol === 'https:'
  } catch {
    return false
  }
}

module.exports = { backendExecutable, runtimeEnvironment, isAllowedExternalUrl }
