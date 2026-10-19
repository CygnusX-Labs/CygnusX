// Probe: create and capture ALL responses to /exports endpoints.
const { chromium } = require('playwright');
const UI = process.env.UI_BASE;
(async () => {
  const b = await chromium.launch({ headless: true, chromiumSandbox: true });
  const p = await (await b.newContext()).newPage();
  await p.goto(UI + '/login', { waitUntil: 'networkidle' });
  await p.fill('input[placeholder="请输入用户名"]', process.env.RI095_USER);
  await p.fill('input[placeholder="请输入密码"]', process.env.RI095_PASS);
  await p.getByRole('button', { name: /登\s*录/ }).first().click();
  await p.waitForURL((u) => !u.pathname.includes('/login'), { timeout: 45000 });

  p.on('response', async (r) => {
    if (r.url().includes('/exports')) {
      let body = '';
      try { body = (await r.text()).slice(0, 400); } catch (e) {}
      console.log('RESP', r.request().method(), r.status(), r.url().split('/api/v1/')[1], body);
    }
  });

  await p.goto(UI + '/projects/' + process.env.RI095_PROJECT, { waitUntil: 'networkidle' });
  await p.waitForTimeout(2500);
  await p.getByRole('button', { name: /刷新科研成果/ }).first().click();
  await p.waitForTimeout(2500);
  await p.getByRole('button', { name: /导出科研成果/ }).first().click();
  await p.waitForTimeout(3000);
  await p.getByRole('button', { name: /确认范围并后台生成/ }).first().click();
  await p.waitForTimeout(10000);
  await b.close();
})().catch((e) => console.log('FAIL', e.message.split('\n')[0]));
