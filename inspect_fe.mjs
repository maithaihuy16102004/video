import puppeteer from 'puppeteer-core';

(async () => {
  try {
    const browser = await puppeteer.launch({
      executablePath: 'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe',
      headless: true
    });
    const page = await browser.newPage();
    await page.goto('http://127.0.0.1:5173', { waitUntil: 'networkidle2', timeout: 10000 });
    const textareaVal = await page.evaluate(() => {
      const ta = document.querySelector('textarea');
      return ta ? ta.value : null;
    });
    console.log('TEXTAREA_VALUE_LENGTH:', textareaVal ? textareaVal.length : 0);
    console.log('IS_STUDIO_SCRIPT_V1:', textareaVal ? textareaVal.includes('STUDIO SCRIPT V1') : false);
    if (textareaVal) {
      console.log('TEXTAREA_PREVIEW:\n' + textareaVal.substring(0, 300));
    }
    await browser.close();
  } catch (err) {
    console.error('PUPPETEER_ERROR:', err.message);
  }
})();
