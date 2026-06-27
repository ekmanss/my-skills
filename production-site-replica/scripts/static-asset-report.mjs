#!/usr/bin/env node
import { readdir, readFile, stat } from 'node:fs/promises'
import path from 'node:path'

const projectRoot = path.resolve(process.argv[2] || process.cwd())
const jsonOutput = process.argv.includes('--json')

const skipDirs = new Set([
  '.git',
  'node_modules',
  'dist',
  'build',
  '.next',
  '.nuxt',
  '.output',
  '.vite',
  'coverage',
  '.cache',
  'cache',
  'tmp',
  'temp',
])

const textExtensions = new Set([
  '.astro',
  '.css',
  '.html',
  '.js',
  '.jsx',
  '.json',
  '.md',
  '.mjs',
  '.mts',
  '.svelte',
  '.svg',
  '.ts',
  '.tsx',
  '.vue',
])

const skipTextFileNames = new Set([
  'package-lock.json',
  'pnpm-lock.yaml',
  'yarn.lock',
  'bun.lockb',
  'license',
  'license.txt',
])

const artifactDirNames = new Set([
  '_astro',
  '_next',
  'vendor',
  'mirror',
  'mirrors',
  'scrape',
  'scrapes',
  'crawler',
  'downloads',
  '.cache',
  'cache',
])

const walk = async (dir, files = [], dirs = []) => {
  let entries = []
  try {
    entries = await readdir(dir, { withFileTypes: true })
  } catch {
    return { files, dirs }
  }

  for (const entry of entries) {
    const absolute = path.join(dir, entry.name)
    const relative = path.relative(projectRoot, absolute)
    if (entry.isDirectory()) {
      dirs.push(relative)
      if (skipDirs.has(entry.name)) continue
      await walk(absolute, files, dirs)
    } else if (entry.isFile()) {
      files.push(relative)
    }
  }
  return { files, dirs }
}

const toPosix = (value) => value.split(path.sep).join('/')
const { files, dirs } = await walk(projectRoot)

const publicAssetFiles = []
const sourceTextFiles = []
const byExtension = {}
let publicAssetBytes = 0

for (const relative of files) {
  const posix = toPosix(relative)
  const ext = path.extname(relative).toLowerCase()
  if (posix.startsWith('public/assets/')) {
    const info = await stat(path.join(projectRoot, relative))
    publicAssetBytes += info.size
    publicAssetFiles.push({ path: posix, bytes: info.size })
    byExtension[ext || '[none]'] = (byExtension[ext || '[none]'] || 0) + 1
  }
  if (textExtensions.has(ext) && !skipTextFileNames.has(path.basename(relative).toLowerCase())) {
    sourceTextFiles.push(relative)
  }
}

const textCorpus = []
const externalUrls = new Set()
for (const relative of sourceTextFiles) {
  let text = ''
  try {
    text = await readFile(path.join(projectRoot, relative), 'utf8')
  } catch {
    continue
  }
  textCorpus.push({ path: toPosix(relative), text })
  for (const match of text.matchAll(/https?:\/\/[^\s"'`)<>]+/g)) {
    externalUrls.add(match[0])
  }
}

const isReferenced = (assetPath) => {
  const publicRelative = assetPath.replace(/^public\//, '')
  const withLeadingSlash = `/${publicRelative}`
  return textCorpus.some(({ text }) => text.includes(withLeadingSlash) || text.includes(publicRelative))
}

const unreferencedPublicAssets = publicAssetFiles
  .filter((asset) => !isReferenced(asset.path))
  .map((asset) => asset.path)

const suspiciousDirectories = dirs
  .map(toPosix)
  .filter((dir) => artifactDirNames.has(path.basename(dir)))

const largePublicAssets = publicAssetFiles
  .filter((asset) => asset.bytes >= 1024 * 1024)
  .sort((a, b) => b.bytes - a.bytes)

const report = {
  projectRoot,
  publicAssets: {
    files: publicAssetFiles.length,
    bytes: publicAssetBytes,
    megabytes: Number((publicAssetBytes / 1024 / 1024).toFixed(2)),
    byExtension,
    largeFiles: largePublicAssets,
    unreferenced: unreferencedPublicAssets,
  },
  suspiciousDirectories,
  externalUrls: [...externalUrls].sort(),
}

if (jsonOutput) {
  console.log(JSON.stringify(report, null, 2))
} else {
  console.log(`Project: ${report.projectRoot}`)
  console.log(`Public assets: ${report.publicAssets.files} files, ${report.publicAssets.megabytes} MB`)
  console.log(`Unreferenced public assets: ${report.publicAssets.unreferenced.length}`)
  console.log(`Suspicious directories: ${report.suspiciousDirectories.length}`)
  console.log(`External URLs in source: ${report.externalUrls.length}`)
  if (report.publicAssets.unreferenced.length) {
    console.log('\nUnreferenced public assets:')
    for (const file of report.publicAssets.unreferenced) console.log(`- ${file}`)
  }
  if (report.suspiciousDirectories.length) {
    console.log('\nSuspicious directories:')
    for (const dir of report.suspiciousDirectories) console.log(`- ${dir}`)
  }
}
