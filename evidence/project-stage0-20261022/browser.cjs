const { chromium } = require('playwright');
const fs = require('fs');
const assert = require('assert/strict');
const input = JSON.parse(fs.readFileSync(0, 'utf8'));
const records = [], network = [], errors = [];
const base = 'http://127.0.0.1:18003';
function record(name, evidence) {
  records.push({ name, evidence });
  fs.writeFileSync('/output/results.json', JSON.stringify(records, null, 2));
}
(async () => {
  const browser = await chromium.launch({ headless: true, chromiumSandbox: true });
  const page = await browser.newPage({ viewport: { width: 1440, height: 1080 } });
  page.setDefaultTimeout(15000);
  record('browser_launched', browser.version());
  page.on('pageerror', e => errors.push(e.message));
  page.on('request', r => {
    const url = new URL(r.url());
    if (url.pathname.startsWith('/api/')) network.push({ method: r.method(), path: url.pathname });
  });
  try {
    await page.goto(base + '/login', { waitUntil: 'networkidle' });
    await page.fill('input[placeholder="请输入用户名"]', input.owner_username);
    await page.fill('input[placeholder="请输入密码"]', input.owner_password);
    await page.getByRole('button', { name: /登\s*录/ }).first().click();
    await page.waitForURL(base + '/');
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(1200);
    record('real_ui_login', { browser: browser.version(), chromiumSandbox: true });
    const first = '/projects/' + input.projects['browser-enabled'];
    await page.goto(base + first, { waitUntil: 'networkidle' });
    const toggle = page.locator('[data-test="project-research-default"]');
    await toggle.waitFor();
    assert.equal(await toggle.getAttribute('aria-checked'), 'true');
    assert.equal(await page.getByText(/服务未启用：/).count(), 3);
    for (const [name, title] of [['plan', '科研计划与审阅'], ['delivery', '科研执行与交付链'], ['export', '项目科研成果与可追溯导出']]) {
      await page.locator('.n-card').filter({ hasText: `服务未启用：${title}尚未开放。` }).last()
        .screenshot({ path: `/output/${name}-service-disabled.png` });
    }
    record('saved_true_is_visible', true);
    await page.reload({ waitUntil: 'networkidle' });
    assert.equal(await toggle.getAttribute('aria-checked'), 'true');
    record('saved_true_survives_refresh', true);
    await page.screenshot({ path: '/output/research-mode-true-gates-closed.png', fullPage: true });
    // Use router navigation, keeping the same Vue view instance alive.
    await page.evaluate(id => {
      const app = document.querySelector('#app').__vue_app__;
      return app.config.globalProperties.$router.push('/projects/' + id);
    }, input.projects['browser-disabled']);
    await page.waitForURL('**/projects/' + input.projects['browser-disabled']);
    await page.waitForFunction(() => document.querySelector('[data-test="project-research-default"]')?.getAttribute('aria-checked') === 'false');
    assert.equal(await toggle.getAttribute('aria-checked'), 'false');
    record('same_view_project_switch_resets_saved_false', true);
    const unwanted = network.filter(r => /\/(research-plans|research-delivery|delivery-inventory)(\?|$)/.test(r.path));
    assert.equal(unwanted.length, 0);
    record('disabled_surfaces_make_zero_research_requests', { unwanted, capabilityRequests: network.filter(r => r.path.endsWith('/capability-status')).length });
    await page.screenshot({ path: '/output/research-mode-false-gates-closed.png', fullPage: true });
    await toggle.click();
    await page.waitForTimeout(500);
    await page.reload({ waitUntil: 'networkidle' });
    assert.equal(await toggle.getAttribute('aria-checked'), 'true');
    record('ui_toggle_persisted_by_real_patch', true);
    record('pageerrors', errors);
    assert.equal(errors.length, 0);
  } catch (e) {
    record('failure', e.message);
    try { await page.screenshot({ path: '/output/failure.png', fullPage: true, timeout: 5000 }); } catch {}
    throw e;
  } finally {
    fs.writeFileSync('/output/network.json', JSON.stringify(network, null, 2));
    await browser.close();
  }
})().catch(e => { console.error(e.message); process.exitCode = 1; });
