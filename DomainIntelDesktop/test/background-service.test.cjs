'use strict'

const test = require('node:test')
const assert = require('node:assert/strict')
const { EventEmitter } = require('node:events')
const fs = require('node:fs')
const { tmpdir } = require('node:os')
const path = require('node:path')
const { PassThrough } = require('node:stream')

const {
  backgroundServiceStatus,
  encodeCredentialFrame,
  installBackgroundService,
  launchBackgroundWorker,
  removeBackgroundService,
  serviceDefinition,
  writeCredentialFrame,
} = require('../src/background-service.cjs')

function tempRoot(t) {
  const root = fs.mkdtempSync(path.join(tmpdir(), 'intdog-background-'))
  t.after(() => fs.rmSync(root, { recursive:true, force:true }))
  return root
}

test('three platform definitions preserve Unicode/space paths without a shell', () => {
  const executable = path.join('/Applications', '研究 工具', 'IntDog')
  const userData = path.join('/Users', '研究者', 'IntDog Data')
  const win = serviceDefinition({ platform:'win32', executable, userData, intervalMinutes:15 })
  assert.equal(win.install.program.toLowerCase().endsWith('schtasks.exe'), true)
  assert.equal(win.install.args.includes('/Create'), true)
  assert.match(win.install.args[win.install.args.indexOf('/TR') + 1], /--background-worker/)
  assert.equal(win.install.shell, false)

  const mac = serviceDefinition({ platform:'darwin', executable, userData,
    intervalMinutes:15, serviceRoot:path.join(userData, 'launch agents') })
  assert.match(mac.files[0].content, /<string>--background-worker<\/string>/)
  assert.match(mac.files[0].content, /研究 工具/)
  assert.equal(mac.files[0].content.includes('apiKey'), false)

  const linux = serviceDefinition({ platform:'linux', executable, userData,
    intervalMinutes:15, serviceRoot:path.join(userData, 'systemd user') })
  assert.equal(linux.files.length, 2)
  assert.match(linux.files[0].content, /^ExecStart=.*--background-worker/m)
  assert.match(linux.files[1].content, /OnUnitActiveSec=15min/)
  assert.equal(linux.files.some(item => item.content.includes('Environment=')), false)
})

test('install is repeatable and remove preserves industry data', async t => {
  const root = tempRoot(t)
  const userData = path.join(root, '用户 数据')
  const serviceRoot = path.join(root, 'systemd')
  fs.mkdirSync(path.join(userData, 'data', 'AI'), { recursive:true })
  const knowledge = path.join(userData, 'data', 'AI', 'knowledge.json')
  fs.writeFileSync(knowledge, '{"keep":true}')
  const calls = []
  const runner = async (program, args) => { calls.push([program, [...args]]); return {code:0,stdout:'enabled'} }
  const options = { platform:'linux', executable:path.join(root, 'Int Dog'), userData,
    serviceRoot, intervalMinutes:20, runner }
  await installBackgroundService(options)
  await installBackgroundService(options)
  assert.equal((await backgroundServiceStatus(options)).installed, true)
  assert.equal(fs.existsSync(path.join(serviceRoot, 'intdog-background.service')), true)
  await removeBackgroundService(options)
  assert.equal(fs.existsSync(knowledge), true)
  assert.equal((await backgroundServiceStatus(options)).installed, false)
  assert.equal(calls.every(([, args]) => Array.isArray(args)), true)
})

test('length-prefixed credential frame closes once and wipes its source buffer', async () => {
  const secret = 'background-canary-77f1a933'
  const frame = encodeCredentialFrame({provider:'deepseek', model:'chat', apiKey:secret,
    apiBase:'https://api.deepseek.com', authType:'bearer'})
  assert.equal(frame.readUInt32BE(0), frame.length - 4)
  const stream = new PassThrough()
  const chunks = []
  stream.on('data', value => chunks.push(Buffer.from(value)))
  await writeCredentialFrame(stream, frame)
  assert.equal(stream.writableEnded, true)
  assert.equal(frame.every(byte => byte === 0), true)
  const sent = Buffer.concat(chunks)
  assert.equal(JSON.parse(sent.subarray(4).toString()).apiKey, secret)
  assert.equal(stream.writable, false)
})

test('background launch keeps credential canary out of argv/env/state and classifies exits', async t => {
  const root = tempRoot(t)
  const canary = 'background-canary-298c5d11'
  const captures = []
  const spawnProcess = (program, args, options) => {
    const child = new EventEmitter()
    child.stdin = new PassThrough()
    child.stdin.resume()
    child.kill = () => { child.emit('close', null, 'SIGTERM'); return true }
    captures.push({program,args:[...args],env:{...options.env},child})
    queueMicrotask(() => child.emit('close', 0, null))
    return child
  }
  const status = await launchBackgroundWorker({ executable:path.join(root, 'IntDog Runtime'),
    resourcesPath:path.join(root, 'resources'), userData:root, safeStorage:{},
    readCredential:() => ({provider:'openai',model:'gpt',apiKey:canary,
      apiBase:'https://api.openai.com/v1',authType:'bearer'}), spawnProcess })
  assert.equal(status.status, 'completed')
  assert.deepEqual(captures[0].args, ['worker','--once'])
  assert.equal(JSON.stringify(captures[0].args).includes(canary), false)
  assert.equal(JSON.stringify(captures[0].env).includes(canary), false)
  const state = fs.readFileSync(path.join(root, 'background-worker-state.json'), 'utf8')
  assert.equal(state.includes(canary), false)
  assert.equal(fs.readdirSync(root).some(name => name.includes('credential')), false)

  const revoked = await launchBackgroundWorker({ executable:'unused', resourcesPath:root,
    userData:root, authorizationAllowed:false, spawnProcess:() => {
      throw new Error('must not spawn') } })
  assert.equal(revoked.status, 'paused')
  assert.equal(revoked.errorCategory, 'authorization_revoked')
})

test('launch failure and interrupted credential write become redaction-safe terminal state', async t => {
  const root = tempRoot(t)
  const canary = 'background-canary-c5570241'
  const failed = await launchBackgroundWorker({ executable:'missing', resourcesPath:root,
    userData:root, readCredential:() => ({provider:'openai',model:'gpt',apiKey:canary,
      authType:'bearer'}), spawnProcess:() => { throw new Error(`launch ${canary}`) } })
  assert.equal(failed.status, 'failed')
  assert.equal(failed.errorCategory, 'launch_failed')
  assert.equal(JSON.stringify(failed).includes(canary), false)
  assert.equal(fs.readFileSync(path.join(root, 'background-worker-state.json'), 'utf8').includes(canary), false)

  const child = new EventEmitter()
  child.stdin = new PassThrough({ write() { throw new Error(`pipe ${canary}`) } })
  let killed = false
  child.kill = () => { killed = true; return true }
  const interrupted = await launchBackgroundWorker({ executable:'runtime', resourcesPath:root,
    userData:root, readCredential:() => ({provider:'openai',model:'gpt',apiKey:canary,
      authType:'bearer'}), spawnProcess:() => child })
  assert.equal(interrupted.errorCategory, 'credential_pipe_error')
  assert.equal(killed, true)
  assert.equal(JSON.stringify(interrupted).includes(canary), false)
})
