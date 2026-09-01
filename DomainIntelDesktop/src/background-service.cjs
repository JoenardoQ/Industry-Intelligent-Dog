'use strict'

const { execFile } = require('node:child_process')
const fs = require('node:fs')
const os = require('node:os')
const path = require('node:path')
const { runtimeEnvironment } = require('./runtime.cjs')

const SERVICE_NAME = 'intdog-background'
const TASK_NAME = 'IntDog Background Worker'
const MAX_CREDENTIAL_BYTES = 64 * 1024

function _xml(value) {
  return String(value).replaceAll('&', '&amp;').replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;').replaceAll('"', '&quot;')
}

function _systemdQuote(value) {
  return `"${String(value).replaceAll('\\', '\\\\').replaceAll('"', '\\"')}"`
}

function _windowsAction(executable) {
  return `"${String(executable).replaceAll('"', '\\"')}" --background-worker`
}

function _defaultServiceRoot(platform) {
  if (platform === 'darwin') return path.join(os.homedir(), 'Library', 'LaunchAgents')
  if (platform === 'linux') return path.join(os.homedir(), '.config', 'systemd', 'user')
  return ''
}

function serviceDefinition({ platform = process.platform, executable, userData,
  intervalMinutes = 15, serviceRoot }) {
  const interval = Math.max(5, Math.min(1440, Number(intervalMinutes) || 15))
  const binary = path.resolve(String(executable))
  const dataRoot = path.resolve(String(userData))
  if (platform === 'win32') {
    return {
      platform, files: [],
      install: { program:'schtasks.exe', shell:false,
        args:['/Create','/F','/SC','MINUTE','/MO',String(interval),'/TN',TASK_NAME,
          '/TR',_windowsAction(binary)] },
      remove: { program:'schtasks.exe', shell:false,
        args:['/Delete','/F','/TN',TASK_NAME] },
      status: { program:'schtasks.exe', shell:false,
        args:['/Query','/TN',TASK_NAME,'/FO','LIST'] },
    }
  }
  if (platform === 'darwin') {
    const root = path.resolve(serviceRoot || _defaultServiceRoot(platform))
    const target = path.join(root, 'com.intdog.background.plist')
    const domain = `gui/${typeof process.getuid === 'function' ? process.getuid() : 0}`
    const content = `<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
<key>Label</key><string>com.intdog.background</string>
<key>ProgramArguments</key><array><string>${_xml(binary)}</string><string>--background-worker</string></array>
<key>StartInterval</key><integer>${interval * 60}</integer>
<key>RunAtLoad</key><true/>
</dict></plist>
`
    return { platform, files:[{path:target,content,mode:0o600}],
      install: {program:'launchctl',shell:false,args:['bootstrap',domain,target]},
      remove: {program:'launchctl',shell:false,args:['bootout',domain,target]},
      status: {program:'launchctl',shell:false,args:['print',`${domain}/com.intdog.background`]},
      dataRoot }
  }
  if (platform === 'linux') {
    const root = path.resolve(serviceRoot || _defaultServiceRoot(platform))
    const service = path.join(root, `${SERVICE_NAME}.service`)
    const timer = path.join(root, `${SERVICE_NAME}.timer`)
    return { platform, files:[
      {path:service,mode:0o600,content:`[Unit]\nDescription=IntDog background worker\n\n[Service]\nType=oneshot\nExecStart=${_systemdQuote(binary)} --background-worker\n`},
      {path:timer,mode:0o600,content:`[Unit]\nDescription=Wake IntDog background worker\n\n[Timer]\nOnBootSec=2min\nOnUnitActiveSec=${interval}min\nPersistent=true\nUnit=${SERVICE_NAME}.service\n\n[Install]\nWantedBy=timers.target\n`},
    ],
    install: {program:'systemctl',shell:false,
      args:['--user','enable','--now',`${SERVICE_NAME}.timer`]},
    remove: {program:'systemctl',shell:false,
      args:['--user','disable','--now',`${SERVICE_NAME}.timer`]},
    status: {program:'systemctl',shell:false,
      args:['--user','is-enabled',`${SERVICE_NAME}.timer`]},
    reload: {program:'systemctl',shell:false,args:['--user','daemon-reload']},
    dataRoot }
  }
  throw new Error(`Unsupported background service platform: ${platform}`)
}

function _statePath(userData) {
  return path.join(userData, 'background-service.json')
}

function _workerStatePath(userData) {
  return path.join(userData, 'background-worker-state.json')
}

function _atomicJson(target, value) {
  fs.mkdirSync(path.dirname(target), {recursive:true})
  const temporary = `${target}.tmp`
  fs.writeFileSync(temporary, JSON.stringify(value, null, 2), {mode:0o600})
  fs.renameSync(temporary, target)
}

function _readJson(target, fallback) {
  try { return JSON.parse(fs.readFileSync(target, 'utf8')) } catch { return fallback }
}

function _defaultRunner(program, args) {
  return new Promise((resolve, reject) => {
    execFile(program, args, {windowsHide:true, shell:false}, (error, stdout, stderr) => {
      if (error) { error.stdout = stdout; error.stderr = stderr; reject(error) }
      else resolve({code:0,stdout:String(stdout || ''),stderr:String(stderr || '')})
    })
  })
}

async function _ignoreMissing(run, command) {
  try { await run(command.program, command.args) } catch { /* idempotent removal */ }
}

async function installBackgroundService(options) {
  const definition = serviceDefinition(options)
  const run = options.runner || _defaultRunner
  for (const file of definition.files) {
    fs.mkdirSync(path.dirname(file.path), {recursive:true})
    const current = fs.existsSync(file.path) ? fs.readFileSync(file.path, 'utf8') : null
    if (current !== file.content) {
      const temporary = `${file.path}.tmp`
      fs.writeFileSync(temporary, file.content, {mode:file.mode})
      fs.renameSync(temporary, file.path)
    }
  }
  if (definition.reload) await run(definition.reload.program, definition.reload.args)
  if (definition.platform === 'darwin') await _ignoreMissing(run, definition.remove)
  await run(definition.install.program, definition.install.args)
  const status = {installed:true,enabled:true,platform:definition.platform,
    intervalMinutes:Math.max(5, Math.min(1440, Number(options.intervalMinutes) || 15)),
    installedAt:new Date().toISOString(), errorCategory:''}
  _atomicJson(_statePath(options.userData), status)
  return status
}

async function removeBackgroundService(options) {
  const definition = serviceDefinition(options)
  const run = options.runner || _defaultRunner
  await _ignoreMissing(run, definition.remove)
  for (const file of definition.files) {
    try { fs.unlinkSync(file.path) } catch (error) {
      if (error.code !== 'ENOENT') throw error
    }
  }
  if (definition.reload) await run(definition.reload.program, definition.reload.args)
  const previous = _readJson(_statePath(options.userData), {})
  const status = {...previous,installed:false,enabled:false,platform:definition.platform,
    removedAt:new Date().toISOString(),errorCategory:''}
  _atomicJson(_statePath(options.userData), status)
  return status
}

async function backgroundServiceStatus(options) {
  const definition = serviceDefinition(options)
  const saved = _readJson(_statePath(options.userData), null)
  if (!saved?.installed) return {installed:false,enabled:false,
    platform:definition.platform,errorCategory:saved?.errorCategory || ''}
  const filesPresent = definition.files.every(file => fs.existsSync(file.path))
  return {...saved,installed:definition.platform === 'win32' || filesPresent,
    enabled:Boolean(saved.enabled && (definition.platform === 'win32' || filesPresent))}
}

function encodeCredentialFrame(value) {
  const payload = Buffer.from(JSON.stringify(value || {}), 'utf8')
  if (payload.length > MAX_CREDENTIAL_BYTES) {
    payload.fill(0)
    throw new Error('Credential payload exceeds 64 KiB')
  }
  const frame = Buffer.allocUnsafe(payload.length + 4)
  frame.writeUInt32BE(payload.length, 0)
  payload.copy(frame, 4)
  payload.fill(0)
  return frame
}

function writeCredentialFrame(stream, frame) {
  if (!Buffer.isBuffer(frame)) return Promise.reject(new TypeError('credential frame must be a Buffer'))
  return new Promise((resolve, reject) => {
    let settled = false
    const finish = error => {
      if (settled) return
      settled = true
      frame.fill(0)
      stream.off('error', onError)
      error ? reject(error) : resolve()
    }
    const onError = error => finish(error)
    stream.once('error', onError)
    try { stream.end(frame, () => finish()) } catch (error) { finish(error) }
  })
}

function _workerState(userData, changes) {
  const safe = {
    status:String(changes.status || 'failed'),
    errorCategory:String(changes.errorCategory || ''),
    credentialStatus:String(changes.credentialStatus || 'not_configured'),
    startedAt:changes.startedAt || new Date().toISOString(),
    finishedAt:changes.finishedAt || null,
    exitCode:Number.isInteger(changes.exitCode) ? changes.exitCode : null,
    signal:changes.signal ? String(changes.signal) : '',
  }
  _atomicJson(_workerStatePath(userData), safe)
  return safe
}

async function launchBackgroundWorker({ executable, resourcesPath, userData,
  safeStorage, readCredential = () => null, spawnProcess,
  authorizationAllowed = true }) {
  const startedAt = new Date().toISOString()
  if (!authorizationAllowed) return _workerState(userData, {status:'paused',startedAt,
    finishedAt:new Date().toISOString(),errorCategory:'authorization_revoked'})
  let credential = null
  try { credential = readCredential(userData, safeStorage) } catch {
    return _workerState(userData, {status:'paused',startedAt,
      finishedAt:new Date().toISOString(),errorCategory:'secure_storage_locked',
      credentialStatus:'locked'})
  }
  const frame = encodeCredentialFrame(credential || {})
  const env = runtimeEnvironment({resourcesPath,userData,token:'',executable})
  const spawn = spawnProcess || require('node:child_process').spawn
  let child
  try {
    child = spawn(executable, ['worker','--once'], {
      env,windowsHide:true,stdio:['pipe','ignore','ignore'],shell:false,
    })
  } catch {
    frame.fill(0)
    return _workerState(userData, {status:'failed',startedAt,
      finishedAt:new Date().toISOString(),errorCategory:'launch_failed',
      credentialStatus:credential ? 'provided' : 'not_configured'})
  }
  const terminal = new Promise(resolve => {
    child.once('error', () => resolve({code:null,signal:'',category:'launch_failed'}))
    child.once('close', (code, signal) => resolve({code,signal,
      category:signal ? 'interrupted' : code === 0 ? '' : 'worker_exit'}))
  })
  try {
    await writeCredentialFrame(child.stdin, frame)
  } catch {
    try { child.kill('SIGTERM') } catch { /* already gone */ }
    return _workerState(userData, {status:'failed',startedAt,
      finishedAt:new Date().toISOString(),errorCategory:'credential_pipe_error',
      credentialStatus:credential ? 'provided' : 'not_configured'})
  } finally {
    if (credential && typeof credential === 'object') {
      for (const key of Object.keys(credential)) credential[key] = ''
    }
    credential = null
  }
  const result = await terminal
  return _workerState(userData, {
    status:result.category ? (result.category === 'interrupted' ? 'interrupted' : 'failed') : 'completed',
    startedAt,finishedAt:new Date().toISOString(),errorCategory:result.category,
    credentialStatus:'consumed',exitCode:result.code,signal:result.signal,
  })
}

module.exports = { backgroundServiceStatus, encodeCredentialFrame,
  installBackgroundService, launchBackgroundWorker, removeBackgroundService,
  serviceDefinition, writeCredentialFrame }
