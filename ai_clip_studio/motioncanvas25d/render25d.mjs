/**
 * render25d.mjs — render the World25D Three.js scene to PNG frames with
 * headless Chrome (puppeteer-core), WITHOUT Motion Canvas.
 *
 * Why two render paths? The Motion Canvas editor render (`scene25d.tsx`
 * via `motion-canvas render`) is the primary path on Mai's Windows PC.
 * This script is the independent fallback: it loads a plain HTML page
 * that builds the same `World25D` spec, steps the camera timeline at
 * 24 fps and screenshots every frame. It proves the 3D world renders
 * correctly even if the Motion Canvas toolchain has a problem — and it
 * is the script used for the first smoke test on Windows.
 *
 * CHROME PATH: NEVER hardcoded. Resolution order:
 *   1. $CHROME_PATH (explicit override)
 *   2. Chrome on PATH (Windows: `where chrome`; `google-chrome`)
 *   3. Well-known Windows install paths
 *   4. /opt/meta-chromium/chrome (this Linux VM — known BROKEN, the
 *      probe will report it and exit loudly instead of rendering
 *      garbage)
 * Every candidate is LAUNCH-PROBED (dump-dom about:blank, exit 0)
 * before use — exactly like `ai_clip_studio/chrome_detect.py`.
 *
 * Usage (Windows, from this folder):
 *   npm install
 *   node render25d.mjs --spec example_spec.json --out frames --fps 24
 *
 * Requires: puppeteer-core, three (see package.json). No Motion Canvas
 * dependency for this script.
 */
import { spawnSync } from 'node:child_process';
import { existsSync, mkdirSync, readFileSync, writeFileSync } from 'node:fs';
import { join, resolve } from 'node:path';
import puppeteer from 'puppeteer-core';

const KNOWN_WINDOWS_PATHS = [
  'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe',
  'C:\\Program Files (x86)\\Google\\Chrome\\Application\\chrome.exe',
  process.env.LOCALAPPDATA
    ? join(process.env.LOCALAPPDATA, 'Google\\Chrome\\Application\\chrome.exe')
    : '',
].filter(Boolean);

function probeChrome(path) {
  const r = spawnSync(path, [
    '--headless=new', '--no-sandbox', '--disable-gpu',
    '--disable-dev-shm-usage', '--dump-dom', 'about:blank',
  ], { encoding: 'utf-8', timeout: 30000 });
  const ok = r.status === 0 && (r.stdout || '').includes('<html');
  const reason = ok ? 'launches OK' : ((r.stderr || '').split('\n')[0] || `exit ${r.status}`);
  return { ok, detail: `${path}: ${ok ? 'launches OK' : `cannot launch (${reason})`}` };
}

export function detectChrome() {
  const candidates = [];
  if (process.env.CHROME_PATH) candidates.push(process.env.CHROME_PATH);
  for (const p of KNOWN_WINDOWS_PATHS) {
    if (!candidates.includes(p)) candidates.push(p);
  }
  if (!candidates.includes('/opt/meta-chromium/chrome')) {
    candidates.push('/opt/meta-chromium/chrome');
  }
  const tried = [];
  for (const path of candidates) {
    if (!existsSync(path)) {
      tried.push(`${path}: not present`);
      continue;
    }
    const { ok, detail } = probeChrome(path);
    tried.push(detail);
    if (ok) return { path, detail: tried.join('; ') };
  }
  return { path: null, detail: 'no usable Chrome: ' + tried.join('; ') };
}

function parseArgs(argv) {
  const out = { spec: 'example_spec.json', outDir: 'frames', fps: 24 };
  for (let i = 0; i < argv.length; i++) {
    if (argv[i] === '--spec') out.spec = argv[++i];
    if (argv[i] === '--out') out.outDir = argv[++i];
    if (argv[i] === '--fps') out.fps = Number(argv[++i]);
  }
  return out;
}

async function main() {
  const { spec, outDir, fps } = parseArgs(process.argv.slice(2));
  const specJson = JSON.parse(readFileSync(resolve(spec), 'utf-8'));
  const { path: chromePath, detail } = detectChrome();
  if (!chromePath) {
    console.error('RENDER BLOCKED: ' + detail);
    console.error('Install Google Chrome and set CHROME_PATH, or run on the Windows PC.');
    process.exit(2);
  }
  console.log('Chrome: ' + detail);

  const duration = specJson.duration_seconds ?? 5;
  const totalFrames = Math.round(duration * fps);
  mkdirSync(outDir, { recursive: true });

  // The page is generated from the spec so the render is data-driven:
  // World25D is bundled by esbuild in the real project; for the smoke
  // test we import three + World25D from the local node_modules via an
  // import map. See README_WINDOWS.md for the build step.
  const html = `<!doctype html><html><body style="margin:0">
<canvas id="c" width="1920" height="1080"></canvas>
<script type="importmap">{"imports":{"three":"./node_modules/three/build/three.module.js"}}</script>
<script type="module">
import { World25D } from './World25D.js';
const spec = ${JSON.stringify(specJson.world)};
const world = new World25D(spec, 1920, 1080);
window.__world = world;
window.__renderAt = (t) => {
  world.updateCamera(t);
  world.render(document.getElementById('c'));
  return world.characterScreenBoxes();
};
</script></body></html>`;
  writeFileSync(join(outDir, '_render_page.html'), html);

  const browser = await puppeteer.launch({
    executablePath: chromePath,
    headless: 'new',
    args: ['--no-sandbox', '--disable-gpu', '--use-gl=swiftshader', '--enable-unsafe-swiftshader'],
  });
  try {
    const page = await browser.newPage();
    await page.setViewport({ width: 1920, height: 1080 });
    await page.goto('file://' + resolve(join(outDir, '_render_page.html')), { waitUntil: 'networkidle0' });
    await page.waitForFunction(() => window.__renderAt, { timeout: 30000 });
    for (let f = 0; f < totalFrames; f++) {
      const t = f / fps;
      await page.evaluate((tt) => window.__renderAt(tt), t);
      await page.screenshot({ path: join(outDir, `frame_${String(f).padStart(4, '0')}.png`) });
    }
    console.log(`rendered ${totalFrames} frames @ ${fps}fps to ${outDir}`);
  } finally {
    await browser.close();
  }
}

if (import.meta.url === `file://${process.argv[1]}`) {
  main().catch((e) => { console.error(e); process.exit(1); });
}
