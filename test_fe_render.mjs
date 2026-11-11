import puppeteer from 'puppeteer-core';

(async () => {
  try {
    const browser = await puppeteer.launch({
      executablePath: 'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe',
      headless: true
    });
    const page = await browser.newPage();
    await page.goto('http://127.0.0.1:5173', { waitUntil: 'networkidle2', timeout: 15000 });
    
    // Check Preflight panel in page
    const panelText = await page.evaluate(() => {
      const el = document.body;
      return el ? el.innerText : '';
    });
    console.log('CONTAINS_PREFLIGHT:', panelText.includes('STUDIO SCRIPT V1 PREFLIGHT GATE'));
    console.log('CONTAINS_REJECTED:', panelText.includes('REJECTED / BLOCKED'));
    console.log('CONTAINS_BLOCKED_BANNER:', panelText.includes('MASTER RENDERING IS CURRENTLY BLOCKED'));
    console.log('PREVIEW_SUBSTR:\n', panelText.substring(0, 600));

    // Take screenshot of the Preflight Panel
    await page.setViewport({ width: 1400, height: 900 });
    await page.screenshot({ path: 'frontend_preflight_panel_proof.png' });
    console.log('Screenshot saved to frontend_preflight_panel_proof.png');
    
    await browser.close();
  } catch (err) {
    console.error('ERROR:', err.message);
  }
})();
