/**
 * Automated Proof Capture for Priority 6: Frontend Script Parser.
 * Uses puppeteer-core to visit http://127.0.0.1:4173, paste the Edo script,
 * trigger Storyboard Analysis, and capture an authoritative high-res screenshot
 * proving:
 * 1. 5 scenes parsed (not 1 scene 10s fallback)
 * 2. 3 characters identified: Haru (young_courier), Ông chủ trạm thư (tech_founder), Aiko (noblewoman)
 * 3. Exact Vietnamese dialogue, shots, emotions, and SFX cues displayed.
 */
import fs from 'node:fs';
import path from 'node:path';
import puppeteer from 'puppeteer-core';

async function main() {
  console.log('Launching Chrome for Frontend Proof Capture...');
  const browser = await puppeteer.launch({
    executablePath: 'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe',
    headless: true,
    args: ['--no-sandbox', '--disable-setuid-sandbox', '--window-size=1920,1080'],
  });

  const page = await browser.newPage();
  await page.setViewport({ width: 1920, height: 1080 });

  console.log('Navigating to http://127.0.0.1:4173...');
  await page.goto('http://127.0.0.1:4173/', { waitUntil: 'networkidle0' });

  // Read Edo script
  const edoScript = fs.readFileSync('edo_script_raw.txt', 'utf-8');

  console.log('Pasting Edo script into textarea...');
  await page.evaluate((text) => {
    const textarea = document.querySelector('textarea');
    if (textarea) {
      textarea.value = text;
      textarea.dispatchEvent(new Event('input', { bubbles: true }));
      textarea.dispatchEvent(new Event('change', { bubbles: true }));
    }
  }, edoScript);

  // Wait 500ms
  await new Promise((r) => setTimeout(r, 500));

  console.log('Clicking "Phân tích & Tạo Storyboard" button...');
  await page.evaluate(() => {
    const buttons = Array.from(document.querySelectorAll('button'));
    const analyzeBtn = buttons.find((b) => b.textContent && b.textContent.includes('Phân tích & Tạo Storyboard'));
    if (analyzeBtn) {
      analyzeBtn.click();
    }
  });

  // Wait for /api/plan network response and UI update
  console.log('Waiting for Storyboard cards to render in UI...');
  await page.waitForFunction(
    () => {
      const text = document.body.innerText;
      return text.includes('Ông chủ trạm thư') && text.includes('Aiko') && text.includes('5 cảnh');
    },
    { timeout: 15000 }
  );

  // Take screenshot
  const outDir = path.resolve('output/v51_drafts');
  fs.mkdirSync(outDir, { recursive: true });
  const outPath = path.join(outDir, 'frontend_edo_script_parsed_proof.png');

  await page.screenshot({ path: outPath, fullPage: false });
  console.log(`Frontend proof screenshot captured successfully: ${outPath}`);

  await browser.close();
}

main().catch((err) => {
  console.error('Error capturing frontend proof:', err);
  process.exit(1);
});
