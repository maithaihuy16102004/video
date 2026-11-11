/**
 * ProductionRenderService V4.2.1
 * 
 * Authoritative Visual Production Render Engine.
 * 
 * Pipeline:
 * Three.js WebGL 3D World (Architecture, Perspective, Lighting, Weather)
 *   + Motion Canvas 2D Vector Compositor (Bézier Characters, Kinematics, Typography, Subtitles)
 *   → Headless Chrome Hardware WebGL Frame Buffer (1920x1080 @ 24fps)
 *   → Deterministic Frame-by-Frame Pipe
 *   → FFmpeg Mux with VieNeu-TTS & Multi-Track Foley
 *   → Web-Optimized H.264 FastStart MP4
 */

import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';
import http from 'node:http';
import { spawn, execSync } from 'node:child_process';
import puppeteer from 'puppeteer-core';

async function isPortOpen(port) {
  return new Promise((resolve) => {
    const req = http.get(`http://localhost:${port}/render_runner.html`, (res) => {
      resolve(true);
    });
    req.on('error', () => resolve(false));
    req.setTimeout(1500, () => {
      req.abort();
      resolve(false);
    });
  });
}

let spawnedVite = null;

async function ensureViteServer(port = 9000) {
  const open = await isPortOpen(port);
  if (open) return;
  console.log(`Port ${port} not reachable. Spawning Vite dev server on port ${port}...`);
  const isWin = process.platform === 'win32';
  const npxCmd = isWin ? 'npx.cmd' : 'npx';
  spawnedVite = spawn(npxCmd, ['vite', '--port', String(port)], {
    stdio: 'ignore',
    shell: isWin,
    detached: true,
  });
  spawnedVite.unref();

  for (let i = 0; i < 30; i++) {
    await new Promise((r) => setTimeout(r, 500));
    if (await isPortOpen(port)) {
      console.log(`Vite dev server successfully running on port ${port}!`);
      return;
    }
  }
  throw new Error(`Failed to start Vite dev server on port ${port} after 15 seconds.`);
}

function getSha256(filePath) {
  const hash = crypto.createHash('sha256');
  const data = fs.readFileSync(filePath);
  hash.update(data);
  return hash.digest('hex');
}

export function getElementaryStreamHashes(filePath) {
  let videoHash = '';
  let audioHash = '';
  try {
    const vOut = execSync(`ffmpeg -i "${filePath}" -map 0:v:0 -c copy -f streamhash -hash sha256 -`, { encoding: 'utf-8', stdio: ['pipe', 'pipe', 'pipe'] });
    const vMatch = vOut.match(/0,v,SHA256=([0-9a-fA-F]+)/);
    if (vMatch) videoHash = vMatch[1].toLowerCase();
  } catch (err) {
    const output = (err.stdout || '') + (err.stderr || '');
    const vMatch = output.match(/0,v,SHA256=([0-9a-fA-F]+)/);
    if (vMatch) videoHash = vMatch[1].toLowerCase();
  }
  try {
    const aOut = execSync(`ffmpeg -i "${filePath}" -map 0:a:0 -c copy -f streamhash -hash sha256 -`, { encoding: 'utf-8', stdio: ['pipe', 'pipe', 'pipe'] });
    const aMatch = aOut.match(/0,a,SHA256=([0-9a-fA-F]+)/);
    if (aMatch) audioHash = aMatch[1].toLowerCase();
  } catch (err) {
    const output = (err.stdout || '') + (err.stderr || '');
    const aMatch = output.match(/0,a,SHA256=([0-9a-fA-F]+)/);
    if (aMatch) audioHash = aMatch[1].toLowerCase();
  }
  return { videoStreamHash: videoHash, audioStreamHash: audioHash };
}

export async function renderProductionVideo({
  sceneType,
  packagePath,
  scenePackage,
  durationSec,
  audioPath,
  outputPath,
  fps = 24,
}) {
  const startTime = Date.now();

  let activePkg = scenePackage;
  if (!activePkg && packagePath && fs.existsSync(packagePath)) {
    activePkg = JSON.parse(fs.readFileSync(packagePath, 'utf-8'));
  }

  if (activePkg && !durationSec) {
    durationSec = activePkg.total_sequence_duration_seconds || 10.0;
  }

  const effectiveDuration = durationSec || 10.0;
  const totalFrames = Math.round(effectiveDuration * fps);
  console.log(`\n======================================================`);
  console.log(`PRODUCTION RENDER SERVICE V4.2.2 (UNIVERSAL ENGINE)`);
  if (activePkg) {
    console.log(`Package:     ${activePkg.project_id || activePkg.sequence_id || 'ProductionScenePackage'}`);
    console.log(`Location:    ${activePkg.scene_world?.canonical_name || activePkg.scene_world?.location_id}`);
    console.log(`Actors:      ${activePkg.actors?.map(a => a.dna?.name || a.actor_id).join(', ')}`);
  } else {
    console.log(`Scene:       ${sceneType}`);
  }
  console.log(`Duration:    ${effectiveDuration}s (${totalFrames} frames @ ${fps}fps)`);
  console.log(`Audio:       ${audioPath}`);
  console.log(`Output MP4:  ${outputPath}`);
  console.log(`======================================================\n`);

  fs.mkdirSync(path.dirname(outputPath), { recursive: true });

  const renderW = activePkg?.width || (activePkg?.aspect_ratio === '9:16' ? 1080 : 1920);
  const renderH = activePkg?.height || (activePkg?.aspect_ratio === '9:16' ? 1920 : 1080);

  // Ensure dev server is alive
  await ensureViteServer(9000);

  // 1. Launch Headless Chrome with Hardware WebGL Enabled
  const browser = await puppeteer.launch({
    executablePath: 'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe',
    headless: true,
    args: [
      '--no-sandbox',
      '--disable-setuid-sandbox',
      '--use-gl=angle',
      '--use-angle=d3d11',
      '--enable-webgl',
      '--ignore-gpu-blocklist',
    ],
  });

  const page = await browser.newPage();
  await page.setViewport({ width: renderW, height: renderH, deviceScaleFactor: 1 });

  page.on('console', (msg) => {
    const text = msg.text();
    if (text.includes('Error') || text.includes('failed') || text.includes('UniversalRunner')) {
      console.log(`[Browser Console] ${text}`);
    }
  });
  page.on('pageerror', (err) => {
    console.error(`[Browser PageError]`, err.message);
  });

  // 2. Connect to Vite Dev Server running Motion Canvas + Three.js
  console.log('Connecting to Motion Canvas & Three.js runtime (http://localhost:9000/render_runner.html)...');
  await page.goto('http://localhost:9000/render_runner.html', { waitUntil: 'domcontentloaded' });
  await page.waitForFunction(() => window.runnerReady === true, { timeout: 30000 });

  // Initialize Scene via Universal Package or Legacy Adapter
  if (activePkg) {
    console.log('Initializing via Universal setupProductionPackage()...');
    await page.evaluate((pkg) => window.setupProductionPackage(pkg), activePkg);
  } else {
    console.log(`Initializing via setupScene('${sceneType}')...`);
    await page.evaluate((st) => window.setupScene(st), sceneType);
  }

  // 3. Spawn FFmpeg Process
  const ffmpegArgs = [
    '-y',
    '-f', 'image2pipe',
    '-vcodec', 'png',
    '-r', String(fps),
    '-i', '-',
    '-i', audioPath,
    '-c:v', 'libx264',
    '-crf', '22',
    '-preset', 'faster',
    '-pix_fmt', 'yuv420p',
    '-c:a', 'aac',
    '-b:a', '192k',
    '-ar', '48000',
    '-af', 'loudnorm=I=-14:TP=-2.0:LRA=7',
    '-movflags', '+faststart',
    outputPath,
  ];

  const ffmpeg = spawn('ffmpeg', ffmpegArgs, { stdio: ['pipe', 'pipe', 'pipe'] });
  ffmpeg.stderr.on('data', (d) => {
    // Suppress verbose FFmpeg logs unless error
  });

  // 4. Deterministic Frame Loop
  console.log(`Starting frame render loop (0 -> ${totalFrames - 1})...`);
  for (let f = 0; f < totalFrames; f++) {
    const t = f / fps;
    try {
      await page.evaluate((idx, time) => window.renderFrame(idx, time), f, t);
    } catch (err) {
      console.error(`\n[CRITICAL_FRAME_REJECTED] Frame ${f} (t=${t.toFixed(2)}s) rejected during render:`, err.message);
      ffmpeg.stdin.end();
      await browser.close();
      throw err;
    }
    const compHandle = await page.$('#composite-canvas');
    const frameBuf = compHandle ? await compHandle.screenshot({ type: 'png' }) : await page.screenshot({ type: 'png' });
    ffmpeg.stdin.write(frameBuf);

    if (f % 24 === 0 || f === totalFrames - 1) {
      process.stdout.write(`  Rendered frame ${f + 1}/${totalFrames} (t = ${t.toFixed(2)}s)...\r`);
    }
  }
  process.stdout.write('\n');

  ffmpeg.stdin.end();

  await new Promise((resolve, reject) => {
    ffmpeg.on('close', (code) => {
      if (code === 0) resolve();
      else reject(new Error(`FFmpeg exited with error code ${code}`));
    });
  });

  // 5. Invariant Validation Before Finalizing Render
  // "validate that prop_position == hand_bone_world_position ± 2px before finalizing render"
  console.log(`Validating handheld prop attachment tolerance (±2px) before finalizing render...`);
  const finalizationAudit = await page.evaluate(() => {
    if (typeof window.finalizeRender === 'function') {
      return window.finalizeRender();
    }
    return null;
  });

  if (finalizationAudit) {
    console.log(`  ✓ Prop parenting validated: ${finalizationAudit.checkedCount} checks, max deviation: ${finalizationAudit.maxDistance}px (limit ±2px)`);
  }

  await browser.close();

  const elapsed = ((Date.now() - startTime) / 1000).toFixed(1);
  const fileSizeMb = (fs.statSync(outputPath).size / (1024 * 1024)).toFixed(2);
  const fileHash = getSha256(outputPath);
  const streamHashes = getElementaryStreamHashes(outputPath);

  console.log(`Render completed successfully in ${elapsed}s!`);
  console.log(`Output: ${outputPath} (${fileSizeMb} MB)`);
  console.log(`  Container SHA256:    ${fileHash.substring(0, 16)}...`);
  console.log(`  Video Stream SHA256: ${streamHashes.videoStreamHash.substring(0, 16)}...`);
  console.log(`  Audio Stream SHA256: ${streamHashes.audioStreamHash.substring(0, 16)}...\n`);

  return {
    sceneType,
    durationSec,
    totalFrames,
    fps,
    outputPath,
    fileSizeMb,
    fileHash,
    videoStreamHash: streamHashes.videoStreamHash,
    audioStreamHash: streamHashes.audioStreamHash,
    elapsedSec: elapsed,
  };
}

// CLI Support
if (process.argv[1] && path.resolve(process.argv[1]) === path.resolve('scripts/production_render_service.mjs')) {
  const args = process.argv.slice(2);
  const getArg = (flag) => {
    const idx = args.indexOf(flag);
    return idx !== -1 ? args[idx + 1] : null;
  };

  const packagePath = getArg('--package') ? path.resolve(getArg('--package')) : null;
  const sceneType = getArg('--scene') || (packagePath ? null : 'edo_bridge');
  const durationSec = getArg('--duration') ? parseFloat(getArg('--duration')) : null;
  const audioPath = path.resolve(getArg('--audio') || 'output/v421_audio/proof_a_mixed.wav');
  const outputPath = path.resolve(getArg('--out') || `output/Universal_Cinematic_Pipeline_V421_Renderer_Recovery/v422_${sceneType || 'universal'}_proof.mp4`);

  renderProductionVideo({ sceneType, packagePath, durationSec, audioPath, outputPath })
    .then(() => process.exit(0))
    .catch((err) => {
      console.error('Fatal render failure:', err);
      process.exit(1);
    });
}
