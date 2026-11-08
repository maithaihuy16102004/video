import puppeteer from 'puppeteer-core';

async function test() {
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

  await page.setContent(`
    <!DOCTYPE html>
    <html>
      <head>
        <title>WebGL Test</title>
      </head>
      <body>
        <canvas id="c" width="1920" height="1080"></canvas>
        <script>
          const canvas = document.getElementById('c');
          const gl = canvas.getContext('webgl2') || canvas.getContext('webgl');
          window.webglSupported = !!gl;
          if (gl) {
            window.glRenderer = gl.getParameter(gl.RENDERER);
            window.glVendor = gl.getParameter(gl.VENDOR);
          }
        </script>
      </body>
    </html>
  `);

  const info = await page.evaluate(() => ({
    supported: window.webglSupported,
    renderer: window.glRenderer,
    vendor: window.glVendor,
  }));

  console.log('WebGL Test Result:', JSON.stringify(info, null, 2));
  await browser.close();
}

test().catch(err => {
  console.error('Test failed:', err);
  process.exit(1);
});
