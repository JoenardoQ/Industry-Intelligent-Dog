'use strict'

const test = require('node:test')
const assert = require('node:assert/strict')
const fs = require('node:fs')
const { tmpdir } = require('node:os')
const path = require('node:path')

const {
  InstallNonceStore,
  assertTrustedIpcEvent,
  stableBackgroundExecutable,
  validateInstallRequest,
} = require('../src/ipc-security.cjs')

test('privileged IPC accepts only the main top frame at the random backend origin', () => {
  const webContents = {id:7}
  const mainFrame = {url:'http://127.0.0.1:43127/system'}
  webContents.mainFrame = mainFrame
  const mainWindow = {webContents}
  assert.doesNotThrow(() => assertTrustedIpcEvent(
    {sender:webContents,senderFrame:mainFrame}, {mainWindow,backendOrigin:'http://127.0.0.1:43127'}))
  assert.throws(() => assertTrustedIpcEvent(
    {sender:{id:8},senderFrame:mainFrame}, {mainWindow,backendOrigin:'http://127.0.0.1:43127'}),
  /untrusted IPC sender/)
  assert.throws(() => assertTrustedIpcEvent(
    {sender:webContents,senderFrame:{url:'http://127.0.0.1:43127/frame'}},
    {mainWindow,backendOrigin:'http://127.0.0.1:43127'}), /top frame/)
  assert.throws(() => assertTrustedIpcEvent(
    {sender:webContents,senderFrame:{...mainFrame,url:'http://127.0.0.1:43128/'}},
    {mainWindow,backendOrigin:'http://127.0.0.1:43127'}), /origin/)
})

test('background installation requires one bounded request and consumes its nonce once', () => {
  const store = new InstallNonceStore({random:()=> 'nonce-1',now:()=>1000,ttlMs:5000})
  const nonce = store.issue()
  assert.deepEqual(validateInstallRequest({nonce,intervalMinutes:15}, store),
    {intervalMinutes:15})
  assert.throws(() => validateInstallRequest({nonce,intervalMinutes:15}, store), /nonce/)
  const second = store.issue()
  assert.throws(() => validateInstallRequest({nonce:second,intervalMinutes:4}, store), /interval/)
  assert.throws(() => validateInstallRequest({nonce:'made-up',intervalMinutes:15}, store), /nonce/)
})

test('Linux AppImage background service uses a stable absolute regular file', t => {
  const root = fs.mkdtempSync(path.join(tmpdir(), 'intdog-appimage-'))
  t.after(()=>fs.rmSync(root,{recursive:true,force:true}))
  const appImage = path.join(root,'IntDog.AppImage')
  fs.writeFileSync(appImage,'app')
  const temporaryMount = path.join(root,'.mount-intdog','intdog')
  assert.equal(stableBackgroundExecutable({platform:'linux',execPath:temporaryMount,
    appImage}), appImage)
  assert.throws(() => stableBackgroundExecutable({platform:'linux',execPath:temporaryMount,
    appImage:'relative.AppImage'}), /absolute/)
  assert.throws(() => stableBackgroundExecutable({platform:'linux',execPath:temporaryMount,
    appImage:path.join(root,'missing.AppImage')}), /regular file/)
})
