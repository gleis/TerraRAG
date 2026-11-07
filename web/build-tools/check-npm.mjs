import assert from 'node:assert/strict'
import { spawnSync } from 'node:child_process'
import { createHash } from 'node:crypto'
import { existsSync, mkdtempSync, mkdirSync, readFileSync, rmSync, writeFileSync } from 'node:fs'
import { createRequire } from 'node:module'
import { tmpdir } from 'node:os'
import path from 'node:path'

const cli = path.resolve(process.argv[2] ?? '/opt/npm/bin/npm-cli.js')
const root = mkdtempSync(path.join(tmpdir(), 'npm-cli-control-'))
const manifest = {
  name: 'npm-cli-control', version: '1.0.0', private: true,
  workspaces: ['packages/*', '!packages/excluded'],
  dependencies: { 'is-number': '7.0.0' },
  scripts: { prepare: `node -e "require('node:fs').writeFileSync('prepared.txt','ok')"` },
}
const hashLock = () => createHash('sha256').update(readFileSync(path.join(root, 'package-lock.json'))).digest('hex')
const run = (args, expectedSuccess = true) => {
  const result = spawnSync(process.execPath, [cli, ...args,
    '--userconfig', path.join(root, 'user.npmrc'), '--globalconfig', path.join(root, 'global.npmrc')], {
    cwd: root, encoding: 'utf8',
    env: { ...process.env, PATH: `${path.dirname(process.execPath)}:${process.env.PATH}`, npm_config_cache: path.join(root, 'cache') },
  })
  if (expectedSuccess) assert.equal(result.status, 0, result.stdout + result.stderr)
  else assert.notEqual(result.status, 0, 'Mismatched application lock was accepted')
}
try {
  for (const name of ['included', 'excluded']) {
    const dir = path.join(root, 'packages', name)
    mkdirSync(dir, { recursive: true })
    writeFileSync(path.join(dir, 'package.json'), JSON.stringify({ name: `fixture-${name}`, version: '1.0.0' }))
  }
  writeFileSync(path.join(root, 'package.json'), JSON.stringify(manifest))
  writeFileSync(path.join(root, 'user.npmrc'), '')
  writeFileSync(path.join(root, 'global.npmrc'), '')
  run(['install', '--package-lock-only', '--ignore-scripts'])
  const before = hashLock()
  run(['ci'])
  assert.equal(hashLock(), before)
  assert.equal(readFileSync(path.join(root, 'prepared.txt'), 'utf8'), 'ok')
  assert(existsSync(path.join(root, 'node_modules/fixture-included')))
  assert(!existsSync(path.join(root, 'node_modules/fixture-excluded')))
  const filesDir = path.join(root, 'packages/included')
  writeFileSync(path.join(filesDir, '.npmignore'), '*.log\n!keep.log\n')
  writeFileSync(path.join(filesDir, 'keep.log'), '')
  writeFileSync(path.join(filesDir, 'drop.log'), '')
  const require = createRequire(cli)
  const packlistRequire = createRequire(require.resolve('npm-packlist'))
  const files = await packlistRequire('ignore-walk')({ path: filesDir, ignoreFiles: ['.npmignore'] })
  assert(files.includes('keep.log'))
  assert(!files.includes('drop.log'))
  manifest.dependencies['is-number'] = '6.0.0'
  writeFileSync(path.join(root, 'package.json'), JSON.stringify(manifest))
  writeFileSync(path.join(root, 'node_modules/preserve-on-invalid-lock'), 'present')
  run(['ci'], false)
  assert.equal(hashLock(), before)
  assert(existsSync(path.join(root, 'node_modules/preserve-on-invalid-lock')))
  console.log('Patched npm workspace, negation, lifecycle and lock-preservation controls passed')
} finally {
  rmSync(root, { recursive: true, force: true })
}
