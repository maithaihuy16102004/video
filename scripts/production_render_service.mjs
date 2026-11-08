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
import { spawn } from 'node:child_process';
import puppeteer from 'puppeteer-core';

function getSha256(filePath) {
  const hash = crypto.createHash('sha256');
  const data = fs.readFileSync(filePath);
  hash.update(data);
  return hash.digest('hex');
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
  await page.setViewport({ width: 1920, height: 1080, deviceScaleFactor: 1 });

  // 2. Connect to Vite Dev Server running Motion Canvas + Three.js
  console.log('Connecting to Motion Canvas & Three.js runtime (http://localhost:9000/render_runner.html)...');
  await page.goto('http://localhost:9000/render_runner.html', { waitUntil: 'networkidle0' });

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
    '-af', 'alimiter=limit=0.64:level=false',
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
    await page.evaluate((idx, time) => window.renderFrame(idx, time), f, t);
    const frameBuf = await page.screenshot({ type: 'png' });
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

  await browser.close();

  const elapsed = ((Date.now() - startTime) / 1000).toFixed(1);
  const fileSizeMb = (fs.statSync(outputPath).size / (1024 * 1024)).toFixed(2);
  const fileHash = getSha256(outputPath);

  console.log(`Render completed successfully in ${elapsed}s!`);
  console.log(`Output: ${outputPath} (${fileSizeMb} MB, sha256: ${fileHash.substring(0, 16)}...)\n`);

  return {
    sceneType,
    durationSec,
    totalFrames,
    fps,
    outputPath,
    fileSizeMb,
    fileHash,
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
