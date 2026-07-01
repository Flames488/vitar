/**
 * generate-icons.mjs
 * Generates all required PWA icon sizes from the Vitar source logo.
 *
 * Usage (run once, or whenever the logo changes):
 *   node scripts/generate-icons.mjs
 *
 * Prerequisites (already installed):
 *   npm install sharp --save-dev
 *
 * Source : public/vitar-logo.png  (must be >= 512x512, transparent BG ideal)
 * Output : public/  (flat — matches manifest.json icon paths)
 *
 * Sizes generated:
 *   72, 96, 128, 144, 152, 180, 192, 384, 512  (standard PWA set)
 *   Additional: apple-touch-icon (180), maskable-icon (512)
 */

import sharp from 'sharp'
import { mkdir, copyFile } from 'fs/promises'
import path from 'path'
import { fileURLToPath } from 'url'

const __dirname = path.dirname(fileURLToPath(import.meta.url))
const ROOT = path.resolve(__dirname, '..')
const SOURCE = path.join(ROOT, 'public', 'vitar-logo.png')
const OUT_DIR = path.join(ROOT, 'public')

const SIZES = [72, 96, 128, 144, 152, 180, 192, 384, 512]

// Ensure output dir exists (it should already)
await mkdir(OUT_DIR, { recursive: true })

for (const size of SIZES) {
  const outPath = path.join(OUT_DIR, `icon-${size}x${size}.png`)
  await sharp(SOURCE)
    .resize(size, size, { fit: 'contain', background: { r: 255, g: 255, b: 255, alpha: 0 } })
    .png()
    .toFile(outPath)
  console.log(`✓ icon-${size}x${size}.png`)
}

// Apple touch icon (same as 180px)
await sharp(SOURCE)
  .resize(180, 180, { fit: 'contain', background: { r: 255, g: 255, b: 255, alpha: 1 } })
  .png()
  .toFile(path.join(OUT_DIR, 'apple-touch-icon.png'))
console.log('✓ apple-touch-icon.png')

// Maskable icon — fill the full square (no padding) for Android adaptive icons
await sharp(SOURCE)
  .resize(512, 512, { fit: 'cover', background: { r: 13, g: 148, b: 136, alpha: 1 } }) // teal-600
  .png()
  .toFile(path.join(OUT_DIR, 'maskable-icon-512x512.png'))
console.log('✓ maskable-icon-512x512.png')

console.log('\n✅ All PWA icons generated in public/')
console.log('   Update public/manifest.json if you changed the sizes list.')
