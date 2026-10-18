// Browser launch probe only, never business E2E acceptance.
const { chromium } = require('playwright');
(async () => {
 const browser = await chromium.launch({headless: true, chromiumSandbox: true});
 console.log(JSON.stringify({chromium: browser.version(), playwright: require('playwright/package.json').version}));
 for (const width of [1920, 768, 390]) {
  const page = await browser.newPage({viewport: {width, height: 1080}});
  const response = await page.goto('http://frontend:8080/');
  if (!response || !response.ok()) throw new Error('Frontend unavailable');
  console.log(JSON.stringify({width, status: response.status(), scope: 'launch probe only'}));
  await page.close();
 }
 await browser.close();
})().catch(e => {console.error(e.message); process.exitCode = 1;});
