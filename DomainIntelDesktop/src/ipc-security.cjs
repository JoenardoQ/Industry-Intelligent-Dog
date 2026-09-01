'use strict'

const crypto = require('node:crypto')
const fs = require('node:fs')
const path = require('node:path')

class InstallNonceStore {
  constructor({random=()=>crypto.randomBytes(24).toString('base64url'),
    now=()=>Date.now(),ttlMs=60_000}={}) {
    this.random = random
    this.now = now
    this.ttlMs = Math.max(1_000,Math.min(300_000,Number(ttlMs)||60_000))
    this.values = new Map()
  }

  issue() {
    const nonce = String(this.random())
    this.values.set(nonce,this.now()+this.ttlMs)
    return nonce
  }

  consume(nonce) {
    const key = String(nonce||'')
    const expires = this.values.get(key)
    this.values.delete(key)
    if (!expires || expires < this.now()) throw new Error('background install nonce is invalid or expired')
  }
}

function assertTrustedIpcEvent(event,{mainWindow,backendOrigin}) {
  if (!mainWindow || event?.sender !== mainWindow.webContents) {
    throw new Error('untrusted IPC sender')
  }
  let origin = ''
  try { origin = new URL(String(event?.senderFrame?.url||'')).origin } catch { /* invalid */ }
  if (!backendOrigin || origin !== new URL(backendOrigin).origin) {
    throw new Error('untrusted IPC origin')
  }
  if (!event.senderFrame || event.senderFrame !== mainWindow.webContents.mainFrame) {
    throw new Error('privileged IPC requires the top frame')
  }
}

function validateInstallRequest(value,nonceStore) {
  const intervalMinutes = Number(value?.intervalMinutes)
  if (!Number.isInteger(intervalMinutes) || intervalMinutes < 5 || intervalMinutes > 1440) {
    throw new Error('background interval must be an integer from 5 to 1440 minutes')
  }
  nonceStore.consume(value?.nonce)
  return {intervalMinutes}
}

function stableBackgroundExecutable({platform=process.platform,execPath=process.execPath,
  appImage=process.env.APPIMAGE}) {
  const selected = platform === 'linux' && appImage ? String(appImage) : String(execPath)
  if (!path.isAbsolute(selected)) throw new Error('background executable must be absolute')
  const resolved = path.resolve(selected)
  let stat
  try { stat = fs.statSync(resolved) } catch { /* reported below */ }
  if (!stat?.isFile()) throw new Error('background executable must be a regular file')
  return resolved
}

module.exports = {InstallNonceStore,assertTrustedIpcEvent,stableBackgroundExecutable,
  validateInstallRequest}
