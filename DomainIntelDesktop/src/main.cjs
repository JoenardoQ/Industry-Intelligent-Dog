'use strict'

const { app, BrowserWindow, dialog, ipcMain, safeStorage, session, shell } = require('electron')
const { spawn } = require('node:child_process')
const crypto = require('node:crypto')
const fs = require('node:fs')
const http = require('node:http')
const net = require('node:net')
const path = require('node:path')
const { backendExecutable, runtimeEnvironment, isAllowedExternalUrl } = require('./runtime.cjs')
const { clearConfig, publicStatus, readConfig, saveConfig, secureStorageAvailable } = require('./credential-store.cjs')
const { backgroundServiceStatus, encodeCredentialFrame, installBackgroundService,
  launchBackgroundWorker, removeBackgroundService, writeCredentialFrame } = require('./background-service.cjs')
const { InstallNonceStore, assertTrustedIpcEvent, stableBackgroundExecutable,
  validateInstallRequest } = require('./ipc-security.cjs')

let mainWindow = null
let backend = null
let backendOrigin = ''
let capability = ''
let stopping = false
const installNonces = new InstallNonceStore()

function privileged(handler) {
  return (event,...args) => {
    assertTrustedIpcEvent(event,{mainWindow,backendOrigin})
    return handler(...args)
  }
}

function writeE2EMarker(state, extra = {}) {
  const marker = process.env.INTDOG_E2E_MARKER
  if (marker) {
    let previous = {}
    try { previous = JSON.parse(fs.readFileSync(marker, 'utf8')) } catch { /* first write */ }
    fs.writeFileSync(marker, JSON.stringify({ ...previous, ...extra, state, at: new Date().toISOString() }))
  }
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

function requestJson(method, target, headers = {}, body = null) {
  return new Promise((resolve, reject) => {
    const payload = body === null ? null : Buffer.from(JSON.stringify(body))
    const req = http.request(target, { method, headers: { ...headers,
      ...(payload ? { 'Content-Type':'application/json', 'Content-Length':payload.length } : {}) },
      timeout: 5000 }, response => {
      const chunks = []
      response.on('data', chunk => chunks.push(chunk))
      response.once('end', () => {
        const text = Buffer.concat(chunks).toString('utf8')
        let value = null
        try { value = text ? JSON.parse(text) : null } catch { /* handled below */ }
        if ((response.statusCode || 500) >= 400) return reject(new Error(`HTTP ${response.statusCode}: ${text}`))
        resolve(value)
      })
    })
    req.once('timeout', () => req.destroy(new Error('timeout')))
    req.once('error', reject)
    if (payload) req.write(payload)
    req.end()
  })
}

async function runE2EWorkflow() {
  const headers = { 'X-IntDog-Session': capability }
  const setup = await requestJson('GET', `${backendOrigin}/api/setup`, headers)
  if (!setup?.runtime_ready || !setup?.taskpack_ready) throw new Error('setup contract is not ready')
  const referenceAgentContract = Array.isArray(setup.mcp_command) && setup.mcp_command.length >= 2
    && Array.isArray(setup.mcp_configs)
    && ['codex','claude','workbuddy','generic'].every(id => setup.mcp_configs.some(row => row.id === id))
  const referenceApiContract = Array.isArray(setup.api_providers)
    && setup.api_providers.every(row => row.id && row.auth_type && row.default_model !== undefined)
  if (!referenceAgentContract || !referenceApiContract) throw new Error('reference connection contract failed')
  let credentialLifecycle = 'unavailable'
  if (secureStorageAvailable(safeStorage)) {
    const dummy = 'intdog-e2e-secret-must-not-leak'
    const userData = app.getPath('userData')
    const status = saveConfig(userData, safeStorage, {
      provider:'openai', model:'e2e-model', apiKey:dummy,
      apiBase:'https://api.openai.com/v1', authType:'bearer' })
    const storedText = fs.readFileSync(path.join(userData, 'provider-config.json'), 'utf8')
    if (!status.configured || storedText.includes(dummy)) throw new Error('secure credential lifecycle failed')
    clearConfig(userData)
    if (publicStatus(userData, safeStorage).configured) throw new Error('secure credential clear failed')
    credentialLifecycle = 'passed'
  }
  const industries = await requestJson('GET', `${backendOrigin}/api/industries`, headers)
  const industryPreexisting = industries.some(row => row.folder === 'E2E')
  if (!industryPreexisting) {
    const operated = await mainWindow.webContents.executeJavaScript(`(async()=>{
      const wait=async(test)=>{const end=Date.now()+30000;while(Date.now()<end){const value=test();if(value)return value;await new Promise(r=>setTimeout(r,100))}throw new Error('renderer onboarding timeout')}
      await wait(()=>document.querySelector('#setup-title'))
      const click=label=>{const button=[...document.querySelectorAll('button')].find(node=>node.textContent.includes(label));if(!button||button.disabled)throw new Error('missing action '+label);button.click()}
      click('继续：选择连接');await wait(()=>document.querySelector('#connection-title'))
      const taskpack=[...document.querySelectorAll('.agent-options label')].find(node=>node.textContent.includes('无模型任务包'))?.querySelector('input')
      if(!taskpack)throw new Error('task-package option missing');taskpack.click();click('继续：选择行业');await wait(()=>document.querySelector('#industry-title'))
      const createMode=[...document.querySelectorAll('button')].find(node=>node.textContent.trim()==='新建行业');if(createMode)createMode.click()
      const set=(name,value)=>{const input=document.querySelector('[name="'+name+'"]');if(!input)throw new Error('missing '+name);const setter=Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,'value').set;setter.call(input,value);input.dispatchEvent(new Event('input',{bubbles:true}));input.dispatchEvent(new Event('change',{bubbles:true}))}
      set('name','发行验收行业');set('folder','E2E')
      click('创建并开始研究');await wait(()=>document.querySelector('#bootstrap-title'));return true
    })()`)
    if (!operated) throw new Error('renderer did not submit onboarding')
  }
  const deadline = Date.now() + 60000
  let final = null
  while (Date.now() < deadline) {
    const jobs = await requestJson('GET', `${backendOrigin}/api/jobs`, headers)
    final = jobs.find(row => row.operation === 'bootstrap') || null
    if (final && !['queued','running','cancelling'].includes(final.status)) break
    if (industryPreexisting) break
    await new Promise(resolve => setTimeout(resolve, 250))
  }
  if (!industryPreexisting && (!final || final.status !== 'completed')) throw new Error(`first task failed: ${final?.status || 'timeout'} ${final?.error || ''}`)
  if (!industryPreexisting) await mainWindow.webContents.executeJavaScript(`(async()=>{const end=Date.now()+15000;while(Date.now()<end){const button=[...document.querySelectorAll('button')].find(node=>node.textContent.includes('进入行业概览'));if(button){button.click();return true}await new Promise(r=>setTimeout(r,100))}throw new Error('onboarding completion unavailable')})()`)
  const overview = await requestJson('GET', `${backendOrigin}/api/industries/E2E/overview`, headers)
  if (!overview?.industry || !Array.isArray(overview.chain)) throw new Error('first overview contract failed')
  const rendererReady = await mainWindow.webContents.executeJavaScript(`(async()=>{
    location.hash='#/jobs';const end=Date.now()+15000;while(Date.now()<end){
      const nav=document.querySelector('[aria-label="主要导航"]');const option=document.querySelector('.industry-select option[value="E2E"]');
      const text=document.body.innerText||'';if(nav&&option&&${industryPreexisting ? 'true' : "text.includes('初始化行业研究')"})return true;
      await new Promise(r=>setTimeout(r,100))}return false
  })()`)
  if (!rendererReady) throw new Error('renderer product contract failed')
  writeE2EMarker('workflow-ready', { workflow:'completed', taskpack:true,
    firstTask:industryPreexisting ? 'persisted' : final.status,
    rendererReady:true, credentialLifecycle, referenceAgentContract,
    referenceApiContract, sourceCount:overview.stats?.sources || 0,
    industryPreexisting })
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
  const providerConfig = readConfig(app.getPath('userData'), safeStorage)
  backend = spawn(executable, ['serve', '--port', String(port)], {
    env: runtimeEnvironment({ resourcesPath: process.resourcesPath,
      userData: app.getPath('userData'), token: capability, executable }),
    windowsHide: true,
    stdio: ['pipe', log, log], shell: false,
  })
  try {
    await writeCredentialFrame(backend.stdin, encodeCredentialFrame(providerConfig || {}))
  } catch (error) {
    try { backend.kill('SIGTERM') } catch { /* already exited */ }
    throw new Error(`无法安全传递 Provider 凭据：${error.name || 'PipeError'}`)
  } finally {
    if (providerConfig) for (const key of Object.keys(providerConfig)) providerConfig[key] = ''
  }
  fs.closeSync(log)
  await waitUntilReady(backendOrigin, backend)
  session.defaultSession.setPermissionRequestHandler((_contents, _permission, callback) => callback(false))
  session.defaultSession.setPermissionCheckHandler(() => false)
  mainWindow = new BrowserWindow({
    width: 1440, height: 960, minWidth: 1040, minHeight: 720,
    show: false, backgroundColor: '#f5f5f2',
    webPreferences: { nodeIntegration: false, contextIsolation: true, sandbox: true,
      preload: path.join(__dirname, 'preload.cjs') },
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
  if (process.env.INTDOG_E2E_FULL_WORKFLOW === '1') await runE2EWorkflow()
  const closeAfter = Number(process.env.INTDOG_E2E_AUTO_CLOSE_MS || 0)
  if (closeAfter > 0) setTimeout(() => app.quit(), closeAfter)
}

async function startBackgroundWorker() {
  const executable = backendExecutable(process.resourcesPath)
  if (!fs.existsSync(executable)) throw new Error(`缺少运行组件：${executable}`)
  const userData = app.getPath('userData')
  const status = await launchBackgroundWorker({ executable,
    resourcesPath:process.resourcesPath, userData, safeStorage,
    readCredential:(root, storage) => {
      const encrypted = path.join(root, 'provider-config.json')
      if (fs.existsSync(encrypted) && !secureStorageAvailable(storage)) {
        throw new Error('secure storage locked')
      }
      return readConfig(root, storage)
    } })
  writeE2EMarker('background-finished', {backgroundStatus:status.status,
    backgroundErrorCategory:status.errorCategory})
  if (!['completed','paused'].includes(status.status)) process.exitCode = 1
  return status
}

async function runE2EServiceCommand(action) {
  if (process.env.INTDOG_NATIVE_SMOKE_ALLOW_SERVICE !== '1') {
    throw new Error('native service mutation was not explicitly enabled')
  }
  const options = {platform:process.platform, executable:stableBackgroundExecutable({}),
    userData:app.getPath('userData'), intervalMinutes:15}
  let status
  if (action === 'install') {
    status = await installBackgroundService(options)
  } else if (action === 'remove') {
    status = await removeBackgroundService(options)
  } else {
    status = await backgroundServiceStatus(options)
  }
  writeE2EMarker(`service-${action}-finished`, {serviceAction:action,
    serviceInstalled:Boolean(status.installed),serviceEnabled:Boolean(status.enabled),
    servicePlatform:status.platform || process.platform})
  return status
}

const backgroundMode = process.argv.includes('--background-worker')
const serviceMode = process.argv.includes('--e2e-service-install') ? 'install'
  : process.argv.includes('--e2e-service-remove') ? 'remove'
    : process.argv.includes('--e2e-service-status') ? 'status' : ''

if (serviceMode) {
  app.whenReady().then(() => runE2EServiceCommand(serviceMode))
    .catch(() => { process.exitCode = 1 }).finally(() => app.quit())
} else if (backgroundMode) {
  app.whenReady().then(startBackgroundWorker).catch(() => { process.exitCode = 1 })
    .finally(() => app.quit())
} else if (!app.requestSingleInstanceLock()) {
  app.quit()
} else {
  ipcMain.handle('intdog:credential-status', privileged(() =>
    publicStatus(app.getPath('userData'), safeStorage)))
  ipcMain.handle('intdog:save-provider', privileged(value =>
    saveConfig(app.getPath('userData'), safeStorage, value)))
  ipcMain.handle('intdog:clear-provider', privileged(() =>
    clearConfig(app.getPath('userData'))))
  ipcMain.handle('intdog:select-agent-executable', privileged(async () => {
    const result = await dialog.showOpenDialog(mainWindow, {
      title:'选择已安装的 Agent 命令', properties:['openFile'],
      filters:process.platform==='win32'
        ? [{name:'Agent 命令',extensions:['exe','cmd','bat']},{name:'所有文件',extensions:['*']}]
        : [{name:'所有文件',extensions:['*']}],
    })
    return {canceled:result.canceled,path:result.filePaths[0]||''}
  }))
  ipcMain.handle('intdog:background-status', privileged(() => backgroundServiceStatus({
    platform:process.platform,executable:stableBackgroundExecutable({}),
    userData:app.getPath('userData') })))
  ipcMain.handle('intdog:background-request-install', privileged(async () => {
    const result = await dialog.showMessageBox(mainWindow, {type:'warning',
      title:'启用 IntDog 后台运行',buttons:['确认启用','取消'],defaultId:1,cancelId:1,
      message:'允许操作系统在关闭窗口后定期唤醒 IntDog？',
      detail:'只有已单独授权的行业、Provider 与任务可以使用模型或联网能力。'})
    if (result.response !== 0) throw new Error('background installation was not approved')
    return {nonce:installNonces.issue()}
  }))
  ipcMain.handle('intdog:background-install', privileged((value = {}) => {
    const request = validateInstallRequest(value,installNonces)
    return installBackgroundService({platform:process.platform,
      executable:stableBackgroundExecutable({}),userData:app.getPath('userData'),
      intervalMinutes:request.intervalMinutes})
  }))
  ipcMain.handle('intdog:background-remove', privileged(() => removeBackgroundService({
    platform:process.platform,executable:stableBackgroundExecutable({}),
    userData:app.getPath('userData') })))
  ipcMain.handle('intdog:relaunch', privileged(() => {
    app.relaunch(); app.quit(); return true
  }))
  ipcMain.handle('intdog:close', privileged(() => {
    setImmediate(() => app.quit()); return true
  }))
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
