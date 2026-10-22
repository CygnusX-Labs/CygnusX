const { chromium } = require('playwright');
const fs = require('fs');
const assert = require('assert/strict');
const input = JSON.parse(fs.readFileSync(0, 'utf8'));
const base = 'http://127.0.0.1:18023';
const records = [], network = [], errors = [];
function record(name, evidence) {
  records.push({ name, evidence });
  fs.writeFileSync('/output/results.json', JSON.stringify(records, null, 2));
}
(async () => {
  const browser = await chromium.launch({ headless: true, chromiumSandbox: true });
  const page = await browser.newPage({ viewport: { width: 1500, height: 1100 } });
  page.setDefaultTimeout(20000);
  page.on('pageerror', e => errors.push(e.message));
  page.on('response', r => {
    const url = new URL(r.url());
    if (url.pathname.startsWith('/api/')) network.push({ method: r.request().method(), path: url.pathname, query: url.search, status: r.status() });
  });
  try {
    await page.goto(base + '/login', { waitUntil: 'networkidle' });
    await page.fill('input[placeholder="请输入用户名"]', input.owner_username);
    await page.fill('input[placeholder="请输入密码"]', input.owner_password);
    await page.getByRole('button', { name: /登\s*录/ }).first().click();
    await page.waitForURL(base + '/');
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(1200);
    const benchmark = input.fixtures.benchmark_project_id;
    const response = page.waitForResponse(r => r.url().includes(`/api/v1/projects/${benchmark}/overview`));
    await page.goto(base + '/projects/' + benchmark, { waitUntil: 'networkidle' });
    const first = await (await response).json();
    assert.equal(first.run_offset, 0);
    assert.equal(first.run_limit, 10);
    assert.equal(first.runs_total, 100);
    assert.equal(first.runs.length, 10);
    const card = page.locator('.n-card').filter({ hasText: '历史运行与归档记录' }).last();
    await card.waitFor();
    const secondResponse = page.waitForResponse(r => {
      const url = new URL(r.url());
      return url.pathname === `/api/v1/projects/${benchmark}/overview` && url.searchParams.get('run_offset') === '10';
    });
    await card.getByText('2', { exact: true }).last().click();
    const second = await (await secondResponse).json();
    assert.equal(second.run_offset, 10);
    assert.equal(second.runs.length, 10);
    assert.ok(!second.runs.some(r => first.runs.some(old => old.id === r.id)));
    await page.getByText(second.runs[0].name, { exact: true }).first().waitFor();
    await card.screenshot({ path: '/output/indexed-pagination.png' });
    record('remote_pagination_by_real_overview_api', { first_ids: first.runs.map(r => r.id), second_ids: second.runs.map(r => r.id), total: 100 });
    const project = input.fixtures.project_id;
    await page.goto(base + '/projects/' + project, { waitUntil: 'networkidle' });
    const labels = page.locator('[data-test="historical-claim"]');
    await labels.first().waitFor();
    assert.equal(await labels.count(), 6);
    assert.ok((await labels.allTextContents()).every(text => text.includes('未观察计算执行，也未提交新任务')));
    const inventory = page.locator('.n-card').filter({ hasText: '项目科研成果与可追溯导出' }).last();
    assert.match(await inventory.innerText(), /分析任务：0 个/);
    assert.match(await inventory.innerText(), /项目导出功能尚未启用/);
    await inventory.screenshot({ path: '/output/historical-inventory.png' });
    const delivery = page.locator('.n-card').filter({ hasText: '科研执行与交付链' }).last();
    await delivery.screenshot({ path: '/output/historical-delivery.png' });
    const runs = page.locator('.n-card').filter({ hasText: '历史运行与归档记录' }).last();
    assert.match(await runs.innerText(), /历史认领（非计算完成）/);
    await runs.screenshot({ path: '/output/historical-run-status.png' });
    record('historical_claims_are_not_completed_computations', { labels: await labels.allTextContents(), task_count: 0, export_enabled: false });
    const writes = network.filter(r => r.method !== 'GET' && !r.path.endsWith('/auth/login'));
    assert.equal(writes.length, 0);
    record('overview_and_inventory_navigation_do_not_write', writes);
    record('pageerrors', errors);
    assert.equal(errors.length, 0);
    record('browser', { version: browser.version(), chromiumSandbox: true });
  } catch (e) {
    record('failure', e.message);
    await page.screenshot({ path: '/output/failure.png', fullPage: true });
    throw e;
  } finally {
    fs.writeFileSync('/output/network.json', JSON.stringify(network, null, 2));
    await browser.close();
  }
})().catch(e => { console.error(e.message); process.exitCode = 1; });
