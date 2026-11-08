import fs from 'node:fs';
import path from 'node:path';
import puppeteer from 'puppeteer-core';

async function run() {
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

  await page.goto('http://localhost:9000/render_runner.html', { waitUntil: 'networkidle0' });

  const threeVer = await page.evaluate(() => {
    return window.THREE ? window.THREE.REVISION : null;
  });

  console.log('Successfully connected to Vite and loaded THREE.js revision:', threeVer);
  await browser.close();
}

run().catch(err => {
  console.error(err);
  process.exit(1);
});
