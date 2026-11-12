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
 *   2. Chrome/Chromium on PATH (searched manually through PATH:
 *      `chrome` / `google-chrome` / `chromium` / `chromium-browser` /
 *      `google-chrome-stable`, plus `.exe` spellings on Windows)
 *   3. Well-known Windows install paths
 *   4. /opt/meta-chromium/chrome (this Linux VM — known BROKEN, the
 *      probe will report it and exit loudly instead of rendering
 *      garbage)
 * Every candidate is LAUNCH-PROBED (dump-dom about:blank, exit 0)
 * before use — exactly like `ai_clip_studio/chrome_detect.py`.
 *
 * EXIT CODES: 0 = frames rendered. 2 = render BLOCKED with a clear
 * printed reason (no usable Chrome, missing build step, missing
 * dependency, bad spec/flags) — never a hang, never fake output.
 * 1 = an unexpected error during the render itself.
 *
 * The render page is served over a local HTTP server rooted at this
 * script's folder (127.0.0.1, ephemeral port): the page imports
 * `./World25D.js` and `./node_modules/three/...`, which only resolve
 * when served from the project folder. Loading the page from the
 * output folder as a file:// URL would 404 both imports and trip
 * Chrome's file-origin module restrictions.
 *
 * Usage (Windows, from this folder):
 *   npm install
 *   npm run build-world
 *   node render25d.mjs --spec example_spec.json --out frames --fps 24
 *
 * Requires: puppeteer-core, three (see package.json). No Motion Canvas
 * dependency for this script.
 */
import { spawnSync } from 'node:child_process';
import { existsSync, mkdirSync, readFileSync } from 'node:fs';
import { createServer } from 'node:http';
import { delimiter, dirname, join, resolve } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';

const SCRIPT_DIR = dirname(fileURLToPath(import.meta.url));
const WORLD_BUNDLE = join(SCRIPT_DIR, 'World25D.js');
const THREE_MODULE = join(
  SCRIPT_DIR, 'node_modules', 'three', 'build', 'three.module.js',
);

const KNOWN_WINDOWS_PATHS = [
  'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe',
  'C:\\Program Files (x86)\\Google\\Chrome\\Application\\chrome.exe',
  process.env.LOCALAPPDATA
    ? join(process.env.LOCALAPPDATA, 'Google\\Chrome\\Application\\chrome.exe')
    : '',
].filter(Boolean);

// Candidate executable names searched on PATH, in order. Mirrors
// chrome_detect.py's CANDIDATE_NAMES (plus the bare `chrome` name).
const PATH_CANDIDATE_NAMES = process.platform === 'win32'
  ? ['chrome.exe', 'chrome', 'google-chrome.exe', 'google-chrome',
     'chromium.exe', 'chromium']
  : ['chromium', 'chromium-browser', 'google-chrome',
     'google-chrome-stable', 'chrome'];

function findOnPath(names) {
  const found = [];
  const pathDirs = (process.env.PATH || '').split(delimiter);
  for (const name of names) {
    for (const dir of pathDirs) {
      if (!dir) continue;
      const candidate = join(dir, name);
      if (existsSync(candidate) && !found.includes(candidate)) {
        found.push(candidate);
      }
    }
  }
  return found;
}

function probeChrome(path) {
  const result = spawnSync(path, [
    '--headless=new', '--no-sandbox', '--disable-gpu',
    '--disable-dev-shm-usage', '--dump-dom', 'about:blank',
  ], { encoding: 'utf-8', timeout: 30000 });
  if (result.error) {
    return { ok: false, detail: `${path}: cannot launch (${result.error.message})` };
  }
  const ok = result.status === 0 && (result.stdout || '').includes('<html');
  const reason = ok
    ? 'launches OK'
    : ((result.stderr || '').split('\n')[0]
      || (result.status === null ? 'launch timed out' : `exit ${result.status}`));
  return { ok, detail: `${path}: ${ok ? 'launches OK' : `cannot launch (${reason})`}` };
}

export function detectChrome() {
  const candidates = [];
  const push = (path) => {
    if (path && !candidates.includes(path)) candidates.push(path);
  };
  // 1. Explicit override. A bare name (no separator) is also resolved
  // through PATH so CHROME_PATH=chrome works.
  if (process.env.CHROME_PATH) {
    push(process.env.CHROME_PATH);
    if (!/[/\\]/.test(process.env.CHROME_PATH)) {
      for (const found of findOnPath([process.env.CHROME_PATH])) push(found);
    }
  }
  // 2. Chrome/Chromium on PATH.
  for (const found of findOnPath(PATH_CANDIDATE_NAMES)) push(found);
  // 3. Well-known Windows install paths.
  for (const path of KNOWN_WINDOWS_PATHS) push(path);
  // 4. This Linux VM's browser (known broken; the probe reports it).
  push('/opt/meta-chromium/chrome');
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
    const flag = argv[i];
    if (flag !== '--spec' && flag !== '--out' && flag !== '--fps') {
      throw new Error(`unknown argument: ${flag}`);
    }
    const value = argv[++i];
    if (value === undefined) {
      throw new Error(`missing value for ${flag}`);
    }
    if (flag === '--spec') out.spec = value;
    if (flag === '--out') out.outDir = value;
    if (flag === '--fps') out.fps = Number(value);
  }
  if (!Number.isFinite(out.fps) || out.fps <= 0) {
    throw new Error(`--fps must be a positive number, got ${out.fps}`);
  }
  return out;
}

function blocked(message) {
  console.error(message);
  process.exit(2);
}

function renderPageHtml(specJson) {
  // The page is generated from the spec so the render is data-driven.
  // World25D.js is the esbuild bundle (npm run build-world); the
  // import map covers a non-bundled build that still imports 'three'.
  return `<!doctype html><html><body style="margin:0">
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
}

async function main() {
  let args;
  try {
    args = parseArgs(process.argv.slice(2));
  } catch (error) {
    blocked(
      'RENDER BLOCKED: ' + error.message + '\n'
      + 'Usage: node render25d.mjs --spec example_spec.json --out frames --fps 24',
    );
  }
  const { spec, outDir, fps } = args;
  let specJson;
  try {
    specJson = JSON.parse(readFileSync(resolve(spec), 'utf-8'));
  } catch (error) {
    blocked(`RENDER BLOCKED: cannot read spec ${spec}: ${error.message}`);
  }
  if (!specJson || typeof specJson.world !== 'object' || specJson.world === null) {
    blocked(`RENDER BLOCKED: spec ${spec} has no "world" object.`);
  }

  const { path: chromePath, detail } = detectChrome();
  if (!chromePath) {
    blocked(
      'RENDER BLOCKED: ' + detail + '\n'
      + 'Install Google Chrome and set CHROME_PATH, or run on the Windows PC.',
    );
  }
  console.log('Chrome: ' + detail);

  // Build preflights: fail with the exact fix instead of a 30 s page
  // timeout or a cryptic module error inside the browser.
  if (!existsSync(WORLD_BUNDLE)) {
    blocked(
      'RENDER BLOCKED: World25D.js is missing (run `npm run build-world` '
      + 'in this folder first).',
    );
  }
  if (!existsSync(THREE_MODULE)) {
    blocked(
      'RENDER BLOCKED: three is not installed (run `npm install` in '
      + 'this folder first).',
    );
  }
  // Puppeteer is imported LAZILY, after Chrome detection, so a
  // machine with no usable Chrome (or no node_modules yet) still
  // gets the clean exit-2 reason above instead of a module crash.
  let puppeteer;
  try {
    ({ default: puppeteer } = await import('puppeteer-core'));
  } catch {
    blocked(
      'RENDER BLOCKED: puppeteer-core is not installed '
      + '(run `npm install` in this folder first).',
    );
  }

  const duration = specJson.duration_seconds ?? 5;
  if (!Number.isFinite(duration) || duration <= 0) {
    blocked(`RENDER BLOCKED: spec duration_seconds must be positive, got ${duration}.`);
  }
  const totalFrames = Math.round(duration * fps);
  const outPath = resolve(outDir);
  mkdirSync(outPath, { recursive: true });

  const pageHtml = renderPageHtml(specJson);
  const serveFiles = new Map([
    ['/World25D.js', { file: WORLD_BUNDLE, type: 'text/javascript' }],
    ['/node_modules/three/build/three.module.js',
     { file: THREE_MODULE, type: 'text/javascript' }],
  ]);
  const server = createServer((req, res) => {
    const url = (req.url || '/').split('?')[0];
    if (url === '/_render_page.html' || url === '/') {
      res.writeHead(200, { 'Content-Type': 'text/html' });
      res.end(pageHtml);
      return;
    }
    const entry = serveFiles.get(url);
    if (entry) {
      res.writeHead(200, { 'Content-Type': entry.type });
      res.end(readFileSync(entry.file));
      return;
    }
    res.writeHead(404, { 'Content-Type': 'text/plain' });
    res.end('not found');
  });
  await new Promise((resolveListen) => {
    server.listen(0, '127.0.0.1', resolveListen);
  });
  const port = server.address().port;

  const browser = await puppeteer.launch({
    executablePath: chromePath,
    headless: 'new',
    args: ['--no-sandbox', '--disable-gpu', '--use-gl=swiftshader', '--enable-unsafe-swiftshader'],
  });
  try {
    const page = await browser.newPage();
    page.on('pageerror', (error) => {
      console.error('PAGE ERROR: ' + error.message);
    });
    await page.setViewport({ width: 1920, height: 1080 });
    await page.goto(`http://127.0.0.1:${port}/_render_page.html`, { waitUntil: 'networkidle0' });
    await page.waitForFunction(() => window.__renderAt, { timeout: 30000 });
    for (let f = 0; f < totalFrames; f++) {
      const t = f / fps;
      await page.evaluate((tt) => window.__renderAt(tt), t);
      await page.screenshot({ path: join(outPath, `frame_${String(f).padStart(4, '0')}.png`) });
    }
    console.log(`rendered ${totalFrames} frames @ ${fps}fps to ${outDir}`);
  } finally {
    await browser.close();
    await new Promise((resolveClose) => server.close(resolveClose));
  }
}

if (import.meta.url === pathToFileURL(resolve(process.argv[1])).href) {
  main().catch((e) => { console.error(e); process.exit(1); });
}
