'use strict'

const path = require('node:path')

function backendExecutable(resourcesPath, platform = process.platform) {
  const name = platform === 'win32' ? 'intdog-runtime.exe' : 'intdog-runtime'
  return path.join(resourcesPath, 'backend', name)
}

function runtimeEnvironment({ resourcesPath, userData, token, executable }) {
  const projectRoot = path.join(resourcesPath, 'intdog')
  return {
    ...process.env,
    INTDOG_PROJECT_ROOT: projectRoot,
    INTDOG_SEARCH_ROOT: path.join(projectRoot, 'DomainIntelSearch'),
    DOMAIN_INTEL_DATA_ROOT: path.join(userData, 'data'),
    INTDOG_SEARCH_EXECUTABLE: executable,
    INTDOG_SESSION_TOKEN: token,
    INTDOG_DISABLE_EMAIL: '1',
    PYTHONUTF8: '1',
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
