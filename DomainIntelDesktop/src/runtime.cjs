'use strict'

const path = require('node:path')

const CHILD_ENV_ALLOWLIST = new Set([
  'PATH','PATHEXT','SYSTEMROOT','WINDIR','COMSPEC','SYSTEMDRIVE','HOME','USERPROFILE',
  'APPDATA','LOCALAPPDATA','PROGRAMDATA','XDG_CONFIG_HOME','XDG_CACHE_HOME','XDG_DATA_HOME',
  'CODEX_HOME','CLAUDE_CONFIG_DIR','TMP','TEMP','TMPDIR','LANG','LANGUAGE','LC_ALL',
  'LC_CTYPE','TZ','SSL_CERT_FILE','SSL_CERT_DIR','REQUESTS_CA_BUNDLE',
])

function backendExecutable(resourcesPath, platform = process.platform) {
  const name = platform === 'win32' ? 'intdog-runtime.exe' : 'intdog-runtime'
  return path.join(resourcesPath, 'backend', name)
}

function runtimeEnvironment({ resourcesPath, userData, token, executable }) {
  const projectRoot = path.join(resourcesPath, 'intdog')
  const environment = {
    ...Object.fromEntries(Object.entries(process.env).filter(([key]) =>
      CHILD_ENV_ALLOWLIST.has(key.toUpperCase()))),
    INTDOG_PROJECT_ROOT: projectRoot,
    INTDOG_SEARCH_ROOT: path.join(projectRoot, 'DomainIntelSearch'),
    DOMAIN_INTEL_DATA_ROOT: path.join(userData, 'data'),
    INTDOG_SEARCH_EXECUTABLE: executable,
    INTDOG_SESSION_TOKEN: token,
    INTDOG_CREDENTIAL_PIPE: '1',
    INTDOG_DISABLE_EMAIL: '1',
    PYTHONUTF8: '1',
  }
  if (!token) delete environment.INTDOG_SESSION_TOKEN
  return environment
}

function isAllowedExternalUrl(value) {
  try {
    return new URL(value).protocol === 'https:'
  } catch {
    return false
  }
}

module.exports = { backendExecutable, runtimeEnvironment, isAllowedExternalUrl }
