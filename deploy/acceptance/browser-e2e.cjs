/**
 * RI09.5 business E2E over the real isolated UI (nginx -> api -> PG/Redis/Worker).
 *
 * NOT a launch probe. Drives the actual Vue app with Chromium's real sandbox
 * (chromiumSandbox: true; never --no-sandbox) at 1920/768/390, capturing
 * screenshots, console, network, downloads and SHA-256.
 *
 * Run inside the browser container: node /acceptance/browser-e2e.cjs
 * Env: UI_BASE, OUT, RI095_USER, RI095_PASS
 */
const { chromium } = require('playwright');
const fs = require('fs');
const path = require('path');
const crypto = require('crypto');

const UI = process.env.UI_BASE || 'http://frontend:8080';
const OUT = process.env.OUT || '/tmp/e2e-browser';
const USER = process.env.RI095_USER;
const PASS = process.env.RI095_PASS;
const PROJECT_ID = process.env.RI095_PROJECT;
const WIDTHS = [1920, 768, 390];

fs.mkdirSync(OUT, { recursive: true });
const results = [];
const rec = (step, ok, extra) => {
  const row = Object.assign({ step, ok }, extra || {});
  results.push(row);
  console.log(JSON.stringify(row));
  return row;
};
const sha = (b) => crypto.createHash('sha256').update(b).digest('hex');
const shoot = (page, name) => page.screenshot({ path: path.join(OUT, name), fullPage: true });

async function main() {
  const browser = await chromium.launch({ headless: true, chromiumSandbox: true });
  rec('browser.launch_sandboxed', true, { version: browser.version() });

  for (const width of WIDTHS) {
    const ctx = await browser.newContext({ viewport: { width, height: 1080 }, acceptDownloads: true });
    const page = await ctx.newPage();
    const console_msgs = [];
    const net = [];
    page.on('console', (m) => console_msgs.push(`${m.type()}: ${m.text().slice(0, 160)}`));
    page.on('request', (r) => net.push({ method: r.method(), url: r.url().slice(0, 180) }));
    page.on('response', (r) => {
      if (r.status() >= 400) net.push({ status: r.status(), url: r.url().slice(0, 180) });
    });

    const tag = `w${width}`;

    // ---- 1. login ----
    try {
      await page.goto(`${UI}/login`, { waitUntil: 'networkidle', timeout: 45000 });
      await shoot(page, `${tag}-01-login.png`);
      await page.fill('input[placeholder="请输入用户名"]', USER);
      await page.fill('input[placeholder="请输入密码"]', PASS);
      await page.getByRole('button', { name: /登\s*录/ }).first().click();
      await page.waitForURL((u) => !u.pathname.includes('/login'), { timeout: 45000 });
      rec(`${tag}.login`, true, { url: page.url() });
      await shoot(page, `${tag}-02-after-login.png`);
    } catch (e) {
      rec(`${tag}.login`, false, { error: e.message.slice(0, 200) });
      await shoot(page, `${tag}-02-login-FAILED.png`).catch(() => {});
      await ctx.close();
      continue;
    }

    // ---- 2. project list -> detail ----
    try {
      await page.goto(`${UI}/projects`, { waitUntil: 'networkidle', timeout: 45000 });
      await shoot(page, `${tag}-03-projects.png`);
      const detailBtns = page.getByRole('button', { name: '查看详情' });
      const cardCount = await detailBtns.count();
      rec(`${tag}.project_list`, cardCount > 0, { rows: cardCount });
      if (PROJECT_ID) {
        await page.goto(`${UI}/projects/${PROJECT_ID}`, { waitUntil: 'networkidle', timeout: 45000 });
      } else {
        await detailBtns.first().click();
      }
      await page.waitForURL(/\/projects\/[0-9a-f-]{8,}/, { timeout: 30000 });
      await page.waitForLoadState('networkidle', { timeout: 30000 });
      rec(`${tag}.project_detail`, true, { url: page.url() });
      await shoot(page, `${tag}-04-project-detail.png`);
    } catch (e) {
      rec(`${tag}.project_detail`, false, { error: e.message.slice(0, 200) });
      await shoot(page, `${tag}-04-detail-FAILED.png`).catch(() => {});
      await ctx.close();
      continue;
    }

    // ---- 3. research delivery panel ----
    try {
      const refresh = page.getByRole('button', { name: /刷新科研成果/ });
      const hasPanel = (await refresh.count()) > 0;
      rec(`${tag}.delivery_panel_present`, hasPanel);
      if (hasPanel) {
        await refresh.first().click();
        await page.waitForTimeout(2500);
        await shoot(page, `${tag}-05-inventory.png`);

        const previewBtn = page.getByRole('button', { name: /导出科研成果/ });
        const previewVisible = (await previewBtn.count()) > 0;
        rec(`${tag}.export_preview_available`, previewVisible);
        if (previewVisible) {
          await previewBtn.first().click();
          await page.waitForTimeout(3000);
          await shoot(page, `${tag}-06-preview.png`);
          const details = await page.locator('details summary').count();
          rec(`${tag}.preview_shows_details`, details > 0, { detail_sections: details });

          const createBtn = page.getByRole('button', { name: /确认范围并后台生成/ });
          if ((await createBtn.count()) > 0 && (await createBtn.first().isEnabled())) {
            await createBtn.first().click();
            // The create is idempotent: an existing ready job returns immediately;
            // a fresh one reaches ready through the real worker. Wait for either
            // the ready-download button or the job status line.
            const ready = page.getByRole('button', { name: /核验 SHA-256 并下载 ZIP/ });
            const statusLine = page.locator('p[role="status"]');
            let readyVisible = false;
            for (let i = 0; i < 45; i++) {
              if ((await ready.count()) > 0) { readyVisible = true; break; }
              const statuses = await statusLine.allTextContents();
              if (statuses.some((t) => t.includes('ready') || t.includes('ready'.replace('ready', '已完成')))) {
                readyVisible = true; break;
              }
              await page.waitForTimeout(2000);
            }
            rec(`${tag}.export_ready`, readyVisible, {
              buttons: (await page.locator('button').allTextContents()).filter((t) => t.trim()).slice(0, 12),
            });
            await shoot(page, `${tag}-07-export-ready.png`);
            if (readyVisible) {
              const [download] = await Promise.all([
                page.waitForEvent('download', { timeout: 30000 }),
                ready.first().click(),
              ]);
              const p = path.join(OUT, `${tag}-project-delivery.zip`);
              await download.saveAs(p);
              const blob = fs.readFileSync(p);
              rec(`${tag}.zip_download`, true, {
                bytes: blob.length,
                sha256: sha(blob),
                filename: download.suggestedFilename(),
              });
            }
          }
        }
      }
    } catch (e) {
      rec(`${tag}.delivery_flow`, false, { error: e.message.slice(0, 250) });
      await shoot(page, `${tag}-07-delivery-FAILED.png`).catch(() => {});
    }

    // ---- 4. refresh persistence / keyboard / overflow ----
    try {
      await page.reload({ waitUntil: 'networkidle', timeout: 45000 });
      const stillOnDetail = /\/projects\/[0-9a-f-]{8,}/.test(page.url());
      rec(`${tag}.refresh_persists`, stillOnDetail, { url: page.url() });
      await page.keyboard.press('Tab');
      await page.keyboard.press('Tab');
      const focused = await page.evaluate(() => document.activeElement && document.activeElement.tagName);
      rec(`${tag}.keyboard_focus`, !!focused, { focused_tag: focused });
      const overflow = await page.evaluate(
        () => document.documentElement.scrollWidth - document.documentElement.clientWidth
      );
      rec(`${tag}.no_horizontal_overflow`, overflow <= 2, { overflow_px: overflow });
      await shoot(page, `${tag}-08-after-refresh.png`);
    } catch (e) {
      rec(`${tag}.post_checks`, false, { error: e.message.slice(0, 200) });
    }

    fs.writeFileSync(path.join(OUT, `${tag}-console.json`), JSON.stringify(console_msgs, null, 2));
    fs.writeFileSync(path.join(OUT, `${tag}-network.json`), JSON.stringify(net, null, 2));
    // The acceptance nginx has no WebSocket proxy for /api/v1/cookies/ws; that
    // connection error is an environment artifact, not a business-page error.
    const real = console_msgs.filter(
      (m) => m.startsWith('error:') && !m.includes('WebSocket connection')
    );
    rec(`${tag}.console_clean`, real.length === 0, { errors: real.length });
    await ctx.close();
  }

  await browser.close();
  fs.writeFileSync(path.join(OUT, 'browser-results.json'), JSON.stringify(results, null, 2));
  const failed = results.filter((r) => !r.ok);
  console.log(JSON.stringify({ summary: { steps: results.length, failed: failed.length } }));
  process.exitCode = 0; // status is conveyed by results; exit code alone never claims success
}

main().catch((e) => {
  console.error(e.stack || e.message);
  process.exitCode = 1;
});
