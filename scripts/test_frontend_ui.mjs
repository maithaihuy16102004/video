import fs from 'node:fs';
import puppeteer from 'puppeteer-core';

async function main() {
  const browser = await puppeteer.launch({
    executablePath: 'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe',
    headless: true,
    args: ['--no-sandbox', '--disable-setuid-sandbox', '--window-size=1920,1080'],
  });

  const page = await browser.newPage();
  await page.setViewport({ width: 1920, height: 1080 });

  console.log('Navigating to http://127.0.0.1:4173/...');
  await page.goto('http://127.0.0.1:4173/', { waitUntil: 'networkidle0' });

  // Read Edo script
  const reqData = JSON.parse(fs.readFileSync('output/studio-jobs/ec69382649/request.json', 'utf-8'));
  const scriptText = reqData.script;

  // Set script into textarea
  await page.evaluate((text) => {
    const textarea = document.querySelector('textarea');
    if (textarea) {
      // Native setter to trigger React onChange
      const nativeSetter = Object.getOwnPropertyDescriptor(window.HTMLTextAreaElement.prototype, 'value').set;
      nativeSetter.call(textarea, text);
      textarea.dispatchEvent(new Event('input', { bubbles: true }));
      textarea.dispatchEvent(new Event('change', { bubbles: true }));
    }
  }, scriptText);

  await new Promise(r => setTimeout(r, 600));

  // Click 'Phân tích & Tạo Storyboard'
  console.log('Clicking Phân tích & Tạo Storyboard...');
  const clicked = await page.evaluate(() => {
    const buttons = Array.from(document.querySelectorAll('button'));
    const btn = buttons.find(b => b.textContent.includes('Phân tích') || b.textContent.includes('Storyboard'));
    if (btn) {
      btn.click();
      return true;
    }
    return false;
  });
  console.log('Button clicked:', clicked);

  // Wait for network response and UI update
  console.log('Waiting for storyboard update...');
  await new Promise(r => setTimeout(r, 4000));

  const screenshotPath = 'output/v51_drafts/frontend_edo_storyboard_verified.png';
  fs.mkdirSync('output/v51_drafts', { recursive: true });
  await page.screenshot({ path: screenshotPath, fullPage: true });
  console.log('Screenshot saved to:', screenshotPath);

  await browser.close();
}

main().catch(err => {
  console.error(err);
  process.exit(1);
});
