'use strict'

const { app, BrowserWindow, dialog, session, shell } = require('electron')
const { spawn } = require('node:child_process')
const crypto = require('node:crypto')
const fs = require('node:fs')
const http = require('node:http')
const net = require('node:net')
const path = require('node:path')
const { backendExecutable, runtimeEnvironment, isAllowedExternalUrl } = require('./runtime.cjs')

let mainWindow = null
let backend = null
let backendOrigin = ''
let capability = ''
let stopping = false

function writeE2EMarker(state) {
  const marker = process.env.INTDOG_E2E_MARKER
  if (marker) fs.writeFileSync(marker, JSON.stringify({ state, at: new Date().toISOString() }))
}

function freePort() {
  return new Promise((resolve, reject) => {
    const server = net.createServer()
    server.once('error', reject)
    server.listen(0, '127.0.0.1', () => {
      const address = server.address()
      server.close(() => resolve(address.port))
    })
  })
}

function request(method, target, headers = {}) {
  return new Promise((resolve, reject) => {
    const req = http.request(target, { method, headers, timeout: 1000 }, response => {
      response.resume()
      response.once('end', () => resolve(response.statusCode || 0))
    })
    req.once('timeout', () => req.destroy(new Error('timeout')))
    req.once('error', reject)
    req.end()
  })
}

async function waitUntilReady(origin, child, timeoutMs = 30000) {
  const deadline = Date.now() + timeoutMs
  while (Date.now() < deadline) {
    if (child.exitCode !== null) throw new Error(`后端提前退出 (${child.exitCode})`)
    try {
      if (await request('GET', `${origin}/api/health`) === 200) return
    } catch { /* startup race */ }
    await new Promise(resolve => setTimeout(resolve, 250))
  }
  throw new Error('后端在 30 秒内未就绪')
}

async function stopBackend() {
  if (stopping || !backend) return
  stopping = true
  const child = backend
  backend = null
  try {
    await request('POST', `${backendOrigin}/api/shutdown`, { 'X-IntDog-Session': capability })
  } catch { /* process may already be gone */ }
  await Promise.race([
    new Promise(resolve => child.once('exit', resolve)),
    new Promise(resolve => setTimeout(resolve, 2500)),
  ])
  if (child.exitCode === null) child.kill('SIGTERM')
}

async function start() {
  const executable = backendExecutable(process.resourcesPath)
  if (!fs.existsSync(executable)) throw new Error(`缺少运行组件：${executable}`)
  const port = await freePort()
  capability = crypto.randomBytes(32).toString('base64url')
  backendOrigin = `http://127.0.0.1:${port}`
  const logDir = path.join(app.getPath('userData'), 'logs')
  fs.mkdirSync(logDir, { recursive: true })
  const log = fs.openSync(path.join(logDir, 'backend.log'), 'a')
  backend = spawn(executable, ['serve', '--port', String(port)], {
    env: runtimeEnvironment({ resourcesPath: process.resourcesPath,
      userData: app.getPath('userData'), token: capability, executable }),
    windowsHide: true,
    stdio: ['ignore', log, log],
  })
  fs.closeSync(log)
  await waitUntilReady(backendOrigin, backend)
  session.defaultSession.setPermissionRequestHandler((_contents, _permission, callback) => callback(false))
  session.defaultSession.setPermissionCheckHandler(() => false)
  mainWindow = new BrowserWindow({
    width: 1440, height: 960, minWidth: 1040, minHeight: 720,
    show: false, backgroundColor: '#f5f5f2',
    webPreferences: { nodeIntegration: false, contextIsolation: true, sandbox: true },
  })
  mainWindow.webContents.setWindowOpenHandler(({ url }) => {
    if (isAllowedExternalUrl(url)) void shell.openExternal(url)
    return { action: 'deny' }
  })
  mainWindow.webContents.on('will-navigate', (event, url) => {
    if (!url.startsWith(`${backendOrigin}/`)) event.preventDefault()
  })
  mainWindow.once('ready-to-show', () => mainWindow.show())
  await mainWindow.loadURL(`${backendOrigin}/#session=${encodeURIComponent(capability)}`)
  writeE2EMarker('ready')
  const closeAfter = Number(process.env.INTDOG_E2E_AUTO_CLOSE_MS || 0)
  if (closeAfter > 0) setTimeout(() => app.quit(), closeAfter)
}

if (!app.requestSingleInstanceLock()) {
  app.quit()
} else {
  app.on('second-instance', () => {
    if (mainWindow) { if (mainWindow.isMinimized()) mainWindow.restore(); mainWindow.focus() }
  })
  app.whenReady().then(start).catch(error => {
    dialog.showErrorBox('IntDog 无法启动', `${error.message}\n\n日志：${path.join(app.getPath('userData'), 'logs')}`)
    app.quit()
  })
  app.on('window-all-closed', () => app.quit())
  app.on('before-quit', event => {
    if (backend && !stopping) {
      event.preventDefault()
      void stopBackend().finally(() => { writeE2EMarker('stopped'); app.quit() })
    }
  })
}
