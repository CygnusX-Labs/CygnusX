const { chromium } = require('playwright');
const fs = require('fs');
const assert = require('assert/strict');
const input = JSON.parse(fs.readFileSync(0, 'utf8'));
const base = 'http://127.0.0.1:18013';
const records = [], network = [], errors = [];
function record(name, evidence) {
  records.push({ name, evidence });
  fs.writeFileSync('/output/results.json', JSON.stringify(records, null, 2));
}
(async () => {
  const browser = await chromium.launch({ headless: true, chromiumSandbox: true });
  const page = await browser.newPage({ viewport: { width: 1440, height: 1080 } });
  page.setDefaultTimeout(15000);
  page.on('pageerror', e => errors.push(e.message));
  page.on('response', r => {
    const url = new URL(r.url());
    if (url.pathname.startsWith('/api/')) network.push({ method: r.request().method(), path: url.pathname, status: r.status() });
  });
  try {
    await page.goto(base + '/login', { waitUntil: 'networkidle' });
    await page.fill('input[placeholder="请输入用户名"]', input.owner_username);
    await page.fill('input[placeholder="请输入密码"]', input.owner_password);
    await page.getByRole('button', { name: /登\s*录/ }).first().click();
    await page.waitForURL(base + '/');
    await page.waitForLoadState('networkidle');
    await page.waitForTimeout(1200);
    await page.goto(base + '/projects/' + input.project_id, { waitUntil: 'networkidle' });
    await page.getByText('暂无科研计划，可在项目 AI 助手或寻宝鼠中准备计划。', { exact: true }).waitFor();
    await page.getByText('尚无 Dataset 交付记录', { exact: true }).waitFor();
    await page.getByText('没有可信关联的分析任务；仍可预览空范围及缺口', { exact: true }).waitFor();
    await page.getByText('项目导出功能尚未启用；可查看已有关联与证据。', { exact: true }).waitFor();
    for (const [name, title] of [['plan','科研计划与审阅'], ['delivery','科研执行与交付链'], ['inventory','项目科研成果与可追溯导出']]) {
      const card = page.locator('.n-card').filter({ hasText: title }).last();
      await card.screenshot({ path: '/output/' + name + '-empty.png' });
      record(name + '_empty_card', await card.innerText());
    }
    assert.equal(await page.getByText('确认生成 ZIP', { exact: true }).count(), 0);
    const research = network.filter(r => /\/(research-plans|research-delivery|delivery-inventory)$/.test(r.path));
    assert.equal(research.length, 3);
    assert.ok(research.every(r => r.method === 'GET' && r.status === 200));
    record('read_only_research_requests', research);
    record('no_automatic_plan_write', network.filter(r => r.method === 'POST' && r.path.includes('research-plan')));
    assert.equal(network.filter(r => r.method === 'POST' && r.path.includes('research-plan')).length, 0);
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
