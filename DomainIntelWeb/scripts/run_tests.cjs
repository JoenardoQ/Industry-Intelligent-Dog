const { mkdirSync } = require('node:fs')
const { tmpdir } = require('node:os')
const { join } = require('node:path')
const { spawnSync } = require('node:child_process')

const temporary = process.platform === 'win32' ? join(tmpdir(), 'intdog-vitest') : '/tmp/intdog-vitest'
mkdirSync(temporary, { recursive: true })
const executable = join(__dirname, '..', 'node_modules', '.bin', process.platform === 'win32' ? 'vitest.cmd' : 'vitest')
const result = spawnSync(executable, ['run'], {
  stdio: 'inherit',
  env: { ...process.env, TMPDIR: temporary, TMP: temporary, TEMP: temporary },
})
process.exit(result.status === null ? 1 : result.status)
