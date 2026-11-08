import puppeteer from 'puppeteer-core';
import fs from 'node:fs';
import path from 'node:path';

async function main() {
  console.log('Testing Canonical Rig & Analytical Kinematics in Headless Chrome...');
  
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
  await page.setViewport({ width: 1920, height: 1080 });

  page.on('console', msg => console.log('BROWSER LOG:', msg.text()));
  page.on('pageerror', err => console.error('BROWSER ERROR:', err));

  await page.goto('http://localhost:9000/render_runner.html', { waitUntil: 'networkidle0' });

  // Test 1: Initialize a production package with Canonical Rig
  console.log('>>> [1/3] Testing setupProductionPackage with Canonical Rig...');
  const testPkg = {
    project_id: 'test_canonical_rig',
    scene_world: {
      location_id: 'RAIL_STATION',
      canonical_name: 'Shanghai Rail Station 1930',
      architecture_style: 'RAIL_STATION',
      weather: 'RAIN'
    },
    actors: [
      {
        actor_id: 'char_arthur',
        role: 'LEAD',
        dna: {
          characterId: 'char_scholar_arthur',
          canonicalName: 'Arthur',
          archetypeId: 'detective_scholar',
          proportions: {
            headRatio: 0.142,
            standingHeightPx: 325,
            shoulderWidthPx: 60,
            limbThicknessPx: 11,
            torsoLengthPx: 108,
            legLengthPx: 168
          },
          face: { headContour: 'oval_gaunt', skinTone: '#EFE0D3', eyeType: 'intense_focused', eyeColor: '#2B2D42', eyebrowStyle: 'straight_sharp', facialHair: 'none' },
          hair: { style: 'side_sweep_1914', color: '#4A3B32', accessory: 'glasses_round' },
          costume: { archetype: 'victorian_frock_coat', primaryColor: '#2B2D42', secondaryColor: '#8D99AE', accentColor: '#D90429', pantsColor: '#1F2022', beltType: 'leather_belt', footwear: 'leather_shoes', footwearColor: '#1A1110' },
          heldProps: { rightHand: 'walking_cane' }
        },
        staging: {
          initial_world_pos: [-0.8, 0.45, -0.6],
          facing: 'RIGHT',
          posture: 'walk'
        },
        performance_cues: [
          { time: 0.0, pos: [-0.8, 0.45, -0.6], action: 'walk', emotion: 'focused', facing: 1 },
          { time: 3.0, pos: [0.2, 0.45, -0.6], action: 'hold', emotion: 'focused', facing: 1 }
        ]
      }
    ]
  };

  const setupRes = await page.evaluate(pkg => window.setupProductionPackage(pkg), testPkg);
  console.log('Setup result:', setupRes);

  // Test 2: Render Frames
  console.log('>>> [2/3] Rendering Frames 0 to 5...');
  for (let f = 0; f < 5; f++) {
    const t = f / 24.0;
    const ok = await page.evaluate((frame, time) => window.renderFrame(frame, time), f, t);
    if (!ok) throw new Error(`Render frame ${f} failed`);
  }
  console.log('Frames rendered successfully.');

  // Test 3: Enable Debug Skeleton & Take Screenshot
  console.log('>>> [3/3] Capturing Skeleton Debug Frame...');
  await page.evaluate(() => { window.__debugSkeleton = true; window.renderFrame(0, 0.0); });
  
  const outDir = path.resolve('output', 'rig_debug');
  fs.mkdirSync(outDir, { recursive: true });
  const debugPngPath = path.join(outDir, 'canonical_rig_debug_shanghai.png');

  const compCanvas = await page.$('#composite-canvas');
  // Need to make composite canvas visible or draw to screenshot
  const screenshotBuf = await page.screenshot({ clip: { x: 0, y: 0, width: 1920, height: 1080 } });
  fs.writeFileSync(debugPngPath, screenshotBuf);
  console.log('Saved debug screenshot to:', debugPngPath);

  await browser.close();
  console.log('Canonical Rig Headless Test: ALL PASS!');
}

main().catch(err => {
  console.error('Test failed:', err);
  process.exit(1);
});
