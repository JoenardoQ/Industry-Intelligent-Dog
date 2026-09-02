const { mkdirSync } = require('node:fs')
const { tmpdir } = require('node:os')
const { join } = require('node:path')
const { spawnSync } = require('node:child_process')

const temporary = process.platform === 'win32' ? join(tmpdir(), 'intdog-vitest') : '/tmp/intdog-vitest'
mkdirSync(temporary, { recursive: true })
const webRoot = join(__dirname, '..')
const executable = join(webRoot, 'node_modules', 'vitest', 'vitest.mjs')
const result = spawnSync(process.execPath, [executable, 'run'], {
  cwd: webRoot,
  stdio: 'inherit',
  env: { ...process.env, TMPDIR: temporary, TMP: temporary, TEMP: temporary },
})
process.exit(result.status === null ? 1 : result.status)
