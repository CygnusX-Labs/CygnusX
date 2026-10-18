/** Offline browser evidence runner. Does not need a listening server or credentials.
 * TREASURE_POC_PLAYWRIGHT_PATH=/path/to/playwright-core/index.js
 * TREASURE_POC_CHROMIUM=/path/to/chrome node scripts/poc/treasure-island-browser.mjs
 */
import { readFile, mkdir, writeFile } from 'node:fs/promises';
import { resolve, extname, sep } from 'node:path';
import { pathToFileURL } from 'node:url';
import assert from 'node:assert/strict';
const evidence = resolve('evidence/treasure-native/p1a-browser');
await mkdir(evidence, { recursive: true });
const report = { status: 'BLOCKED', screenshots: [], errors: [], checks: [] };
let browser;
try {
  const playwright = await import(process.env.TREASURE_POC_PLAYWRIGHT_PATH
    ? pathToFileURL(process.env.TREASURE_POC_PLAYWRIGHT_PATH).href : 'playwright-core');
  const { chromium } = playwright.default || playwright;
  browser = await chromium.launch({ headless: true,
    ...(process.env.TREASURE_POC_CHROMIUM ? { executablePath: process.env.TREASURE_POC_CHROMIUM } : {}),
    args: ['--no-sandbox'],
  });
  const page = await browser.newPage();
  const consoleErrors = [];
  page.on('pageerror', error => consoleErrors.push(error.message));
  await page.route('**/*', async route => {
    const url = new URL(route.request().url());
    if (url.origin !== 'http://treasure-poc.test') return route.abort();
    const reference = url.pathname.startsWith('/reference/');
    const root = reference ? '/tmp/treasure-reference-poc-dist' : '/tmp/treasure-vue-poc-dist';
    const relative = reference ? url.pathname.slice('/reference/'.length) : url.pathname.slice(1);
    const file = resolve(root, relative || 'index.html');
    if (!file.startsWith(root + sep)) return route.abort();
    const types = { '.js': 'text/javascript', '.css': 'text/css', '.html': 'text/html', '.woff2': 'font/woff2', '.webp': 'image/webp' };
    try { await route.fulfill({ body: await readFile(file), contentType: types[extname(file)] || 'application/octet-stream' }); }
    catch { await route.abort(); }
  });
  for (const [width, height] of [[1920, 1080], [1366, 768], [768, 1024], [390, 844]]) {
    await page.setViewportSize({ width, height });
    for (const lang of ['zh', 'en']) for (const theme of ['light', 'dark']) {
      for (const mode of ['reference', 'island']) {
        const path = mode === 'reference' ? '/reference/island-reference.html' : '/';
        await page.goto(`http://treasure-poc.test${path}?lang=${lang}&theme=${theme}`);
        await page.locator('h1').waitFor();
        await page.evaluate(async () => {
          await document.fonts.load('14px "Noto Sans SC Variable"', '科研寻宝鼠');
          await document.fonts.ready;
          const root = document.querySelector('#treasure-island-host')?.shadowRoot || document;
          await Promise.all([...root.querySelectorAll('img')].map(image => image.decode()));
        });
        assert.equal(await page.locator('section').count(), 4);
        if (mode === 'island') {
          const isolated = await page.evaluate(() => {
            const host = document.querySelector('#treasure-island-host');
            const root = host.shadowRoot;
            const heading = root.querySelector('h1');
            return {
              headingColor: getComputedStyle(heading).color,
              foreground: getComputedStyle(root.querySelector('.treasure-island-root')).color,
              noHorizontalOverflow: document.documentElement.scrollWidth <= innerWidth,
              imagesLoaded: [...root.querySelectorAll('img')].every(image => image.naturalWidth > 0),
            };
          });
          assert.equal(isolated.headingColor, isolated.foreground, 'Platform h1 color leaked into island');
          assert.ok(isolated.noHorizontalOverflow, 'Viewport overflows horizontally');
          assert.ok(isolated.imagesLoaded, 'Original local image failed to load');
        }
        const name = `${mode}-${width}-${lang}-${theme}.png`;
        await page.screenshot({ path: resolve(evidence, name), fullPage: true });
        report.screenshots.push(name);
      }
    }
  }
  await page.goto('http://treasure-poc.test/');
  for (let i = 0; i < 2; i++) {
    await page.locator('#treasure-island-host h1').waitFor();
    await page.locator('#route-toggle').click();
    assert.equal(await page.locator('#treasure-island-host').count(), 0);
    assert.equal(await page.locator('style[data-treasure-island-fonts]').count(), 0);
    await page.locator('#route-toggle').click();
  }
  report.checks.push('Vue enter/leave twice; owned font rules released');
  const examples = page.locator('#treasure-island-host section button');
  for (const index of [0, 2, 4, 6]) {
    await examples.nth(index).click();
    assert.ok((await page.locator('#treasure-island-host textarea').inputValue()).length > 0);
  }
  report.checks.push('Four scenes update the Vue-owned draft');
  const before = await page.evaluate(() => ({ body: document.body.getAttribute('style'), title: document.title, lang: document.documentElement.lang }));
  await page.locator('#treasure-island-host button').first().click({ clickCount: 3 });
  await page.locator('#treasure-island-host [role=dialog]').waitFor();
  assert.equal(await page.locator('#treasure-island-host [data-treasure-dialog-backdrop]').count(), 1);
  assert.equal(await page.locator('body > [role=dialog]').count(), 0);
  const dialogButtons = page.locator('#treasure-island-host [role=dialog] button');
  await dialogButtons.last().focus();
  await page.keyboard.press('Tab');
  assert.ok(await dialogButtons.first().evaluate(element => element.getRootNode().activeElement === element));
  await page.keyboard.press('Shift+Tab');
  assert.ok(await dialogButtons.last().evaluate(element => element.getRootNode().activeElement === element));
  await page.screenshot({ path: resolve(evidence, 'island-dialog.png'), fullPage: true });
  await page.keyboard.press('Escape');
  await page.locator('#treasure-island-host [role=dialog]').waitFor({ state: 'detached' });
  assert.ok(await page.locator('#treasure-island-host button').first().evaluate(element => element.getRootNode().activeElement === element));
  assert.deepEqual(await page.evaluate(() => ({ body: document.body.getAttribute('style'), title: document.title, lang: document.documentElement.lang })), before);
  report.checks.push('Scoped backdrop, Tab/Shift+Tab wrap, Escape and focus restoration; platform metadata untouched');
  assert.deepEqual(consoleErrors, []);
  report.status = 'AUTOMATED_CHECKS_PASSED_VISUAL_REVIEW_PENDING';
} catch (error) {
  report.errors.push(String(error));
  process.exitCode = 1;
} finally {
  await browser?.close();
  await writeFile(resolve(evidence, 'result.json'), JSON.stringify(report, null, 2) + '\n');
  console.log(JSON.stringify({ status: report.status, screenshots: report.screenshots.length, errors: report.errors }, null, 2));
}
