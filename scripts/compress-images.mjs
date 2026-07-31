/**
 * compress-images.mjs
 * Compresses images in place — same filename, same extension, same folder.
 * Never resizes dimensions (safe for the PWA icon set), only re-encodes with
 * better compression. Skips a file if the "compressed" version isn't
 * actually smaller (already-optimized files are left untouched).
 *
 * Usage:
 *   node scripts/compress-images.mjs
 *
 * Prerequisites (already installed — same package generate-icons.mjs uses):
 *   npm install sharp --save-dev
 */

import sharp from 'sharp'
import { readdir, stat, rename, unlink } from 'fs/promises'
import path from 'path'
import { fileURLToPath } from 'url'

const __dirname = path.dirname(fileURLToPath(import.meta.url))
const ROOT = path.resolve(__dirname, '..')

// Folders to scan — add more paths here if you keep images elsewhere
const TARGET_DIRS = [
  path.join(ROOT, 'public'),
  path.join(ROOT, 'src', 'assets'),
]

const EXTENSIONS = new Set(['.jpg', '.jpeg', '.png', '.webp'])
const JPEG_QUALITY = 82
const PNG_COMPRESSION_LEVEL = 9

async function* walk(dir) {
  let entries
  try {
    entries = await readdir(dir, { withFileTypes: true })
  } catch {
    return // folder doesn't exist, skip quietly
  }
  for (const entry of entries) {
    const full = path.join(dir, entry.name)
    if (entry.isDirectory()) {
      yield* walk(full)
    } else if (EXTENSIONS.has(path.extname(entry.name).toLowerCase())) {
      yield full
    }
  }
}

async function compressOne(filePath) {
  const ext = path.extname(filePath).toLowerCase()
  const before = (await stat(filePath)).size
  const tmpPath = filePath + '.tmp'

  let pipeline = sharp(filePath)
  if (ext === '.png') {
    pipeline = pipeline.png({ compressionLevel: PNG_COMPRESSION_LEVEL, palette: true })
  } else if (ext === '.webp') {
    pipeline = pipeline.webp({ quality: JPEG_QUALITY })
  } else {
    pipeline = pipeline.jpeg({ quality: JPEG_QUALITY, mozjpeg: true })
  }

  await pipeline.toFile(tmpPath)
  const after = (await stat(tmpPath)).size

  if (after < before) {
    await rename(tmpPath, filePath) // same name, same extension — overwrite
    const savedPct = (((before - after) / before) * 100).toFixed(0)
    console.log(`✓ ${path.relative(ROOT, filePath)}  ${(before / 1024).toFixed(0)}KB → ${(after / 1024).toFixed(0)}KB  (-${savedPct}%)`)
  } else {
    await unlink(tmpPath)
    console.log(`· ${path.relative(ROOT, filePath)}  already optimal, left unchanged`)
  }
}

let count = 0
for (const dir of TARGET_DIRS) {
  for await (const file of walk(dir)) {
    await compressOne(file)
    count++
  }
}
console.log(`\nDone — checked ${count} image(s).`)
