import puppeteer from 'puppeteer-core';

(async () => {
  try {
    const browser = await puppeteer.launch({
      executablePath: 'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe',
      headless: true
    });
    const page = await browser.newPage();
    await page.goto('http://127.0.0.1:5173', { waitUntil: 'networkidle2', timeout: 15000 });
    
    // Find button "⚡ Nạp STUDIO SCRIPT V1 Episode 01 Chuẩn"
    const buttons = await page.$$('button');
    let loadBtn = null;
    for (const b of buttons) {
      const text = await page.evaluate(el => el.innerText, b);
      if (text && text.includes('Episode 01 Chuẩn')) {
        loadBtn = b;
        break;
      }
    }
    
    if (loadBtn) {
      console.log('Found Load Compliant Script Button. Clicking...');
      await loadBtn.click();
      await new Promise(r => setTimeout(r, 800)); // wait for audit
      
      const panelText = await page.evaluate(() => document.body.innerText);
      console.log('CONTAINS_PASSED:', panelText.includes('PASSED (10/10)'));
      console.log('CONTAINS_ALLOW_DRAFT:', panelText.includes('Tạo 1 Bản Audiovisual Draft'));
      
      await page.setViewport({ width: 1400, height: 900 });
      await page.screenshot({ path: 'frontend_preflight_passed_proof.png' });
      console.log('Screenshot saved to frontend_preflight_passed_proof.png');
    } else {
      console.log('Button not found');
    }
    
    await browser.close();
  } catch (err) {
    console.error('ERROR:', err.message);
  }
})();
