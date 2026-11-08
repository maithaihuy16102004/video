import fs from 'node:fs';
import path from 'node:path';
import puppeteer from 'puppeteer-core';

async function run() {
  const outDir = path.resolve('output/Universal_Cinematic_Pipeline_V421_Renderer_Recovery');
  fs.mkdirSync(outDir, { recursive: true });

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

  console.log('Loading runner from http://localhost:9000/render_runner.html...');
  await page.goto('http://localhost:9000/render_runner.html', { waitUntil: 'networkidle0' });

  // Test 1: Edo Bridge Frame
  console.log('Rendering Proof A sample frame (Edo Bridge)...');
  await page.evaluate(() => {
    window.setupScene('edo_bridge');
    window.renderFrame(120, 5.0);
  });
  const bufA = await page.screenshot({ type: 'png' });
  fs.writeFileSync(path.join(outDir, 'sample_frame_edo_bridge.png'), bufA);

  // Test 2: Edo House Frame
  console.log('Rendering Proof B sample frame (Edo Lantern House)...');
  await page.evaluate(() => {
    window.setupScene('edo_house');
    window.renderFrame(144, 6.0);
  });
  const bufB = await page.screenshot({ type: 'png' });
  fs.writeFileSync(path.join(outDir, 'sample_frame_edo_house.png'), bufB);

  // Test 3: Modern Lab Frame
  console.log('Rendering Proof C sample frame (Modern AI Robotics Lab)...');
  await page.evaluate(() => {
    window.setupScene('modern_lab');
    window.renderFrame(72, 3.0);
  });
  const bufC = await page.screenshot({ type: 'png' });
  fs.writeFileSync(path.join(outDir, 'sample_frame_modern_lab.png'), bufC);

  console.log('All 3 sample frames rendered successfully!');
  await browser.close();
}

run().catch(err => {
  console.error('Frame render failed:', err);
  process.exit(1);
});
