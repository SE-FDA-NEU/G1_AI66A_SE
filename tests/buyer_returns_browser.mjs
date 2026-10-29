// Native browser/layout checks for #139. API fixtures; production HTML/CSS/scripts.
import assert from 'node:assert/strict';
import {spawn} from 'node:child_process';
import {createServer} from 'node:http';
import {existsSync} from 'node:fs';
import {readFile, writeFile, mkdir, mkdtemp} from 'node:fs/promises';
import {tmpdir} from 'node:os';
import {join} from 'node:path';

const root = new URL('../', import.meta.url);
const executable = process.env.BROWSER_PATH || [
  'C:/Program Files/Google/Chrome/Application/chrome.exe',
  'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe',
].find(existsSync);
assert.ok(executable, 'Set BROWSER_PATH to installed Chrome/Edge');
const output = new URL('../docs/images/us17/', import.meta.url);
await mkdir(output, {recursive: true});
const initial = {id: 10, status: 'PROCESSING', total_amount: 300000,
  recipient_name: 'Demo Buyer', delivery_address: '123 Demo Street', phone_number: '0912345678',
  created_at: '2026-10-20T10:00:00Z', payment_status: 'PAID', escrow_status: 'HELD',
  sub_orders: [21, 22, 23].map((id, i) => ({id, seller_id: 7 + i,
    status: i === 2 ? 'SHIPPED' : 'DELIVERED', payment_status: 'PAID', escrow_status: 'HELD'})),
  items: [21, 22, 23].map(id => ({seller_order_id: id, product_code: `DEMO-${id}`,
    product_name: `Cotton shirt from shop ${id}`, quantity: 1, unit_price: 100000,
    line_total: 100000, product_image_snapshot: '/static/product-placeholder.svg'}))};
let order = structuredClone(initial), rows = [], validationFailure = false, uncertain = false;
const writes = [];
const server = createServer(async (request, response) => {
  const path = new URL(request.url, 'http://localhost').pathname;
  const json = (value, status = 200) => response.writeHead(status, {'Content-Type': 'application/json'}).end(JSON.stringify(value));
  try {
    if (path.startsWith('/api/')) {
      const token = request.headers.authorization?.split(' ')[1];
      const buyer = token && JSON.parse(Buffer.from(token.split('.')[1], 'base64url')).sub === '2';
      if (path === '/api/v1/auth/me') { json({id: buyer ? 2 : 3, role: 'buyer', status: 'ACTIVE'}); return; }
      if (!buyer) { json({error: {message: 'Order not found.'}}, 404); return; }
      if (path === '/api/v1/orders') { json([{data: order}]); return; }
      if (path === '/api/v1/orders/10') { json({data: order}); return; }
      if (path === '/api/v1/orders/10/returns') {
        if (request.method !== 'POST') { json({data: rows}); return; }
        let body = ''; for await (const chunk of request) body += chunk;
        const payload = JSON.parse(body); writes.push(payload);
        if (validationFailure) {
          json({error: {code: 'ERR_VALIDATION', message: 'Check evidence.', fields: {evidence: ['Provide clearer evidence.']}}}, 422); return;
        }
        order.status = 'RETURN_REQUESTED'; order.escrow_status = 'PAUSED';
        order.sub_orders.find(row => row.id === payload.seller_order_id).status = 'RETURN_REQUESTED';
        const saved = {id: 31, order_id: 10, seller_order_id: payload.seller_order_id,
          reason: payload.reason, evidence: payload.evidence, status: 'PENDING',
          created_at: '2026-10-29T10:00:00Z', payment_status: 'PAID', escrow_status: 'PAUSED', seller_order_status: 'RETURN_REQUESTED'};
        rows = [saved];
        json(uncertain ? {error: {message: 'Response unavailable.'}} : {data: saved}, uncertain ? 503 : 201); return;
      }
      json({error: {message: 'Not found.'}}, 404); return;
    }
    const file = path === '/orders/10' ? 'src/web/pages/order.html'
      : /^\/static\/[\w.-]+$/.test(path) ? `src/web${path}` : null;
    if (!file) { response.writeHead(404).end(); return; }
    response.setHeader('Content-Type', file.endsWith('.js') ? 'text/javascript'
      : file.endsWith('.css') ? 'text/css' : file.endsWith('.svg') ? 'image/svg+xml' : 'text/html');
    response.end(await readFile(new URL(file, root)));
  } catch (error) { response.writeHead(500).end(String(error)); }
});
await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
const base = `http://127.0.0.1:${server.address().port}`;
const profile = await mkdtemp(join(tmpdir(), 'returns139-browser-'));
const browser = spawn(executable, ['--headless=new', '--disable-gpu', '--no-first-run',
  '--remote-debugging-port=0', `--user-data-dir=${profile}`], {windowsHide: true, stdio: 'ignore'});
let ws;
try {
  let port;
  for (let i = 0; i < 100; i++) {
    try { port = (await readFile(join(profile, 'DevToolsActivePort'), 'utf8')).split('\n')[0]; break; }
    catch { await new Promise(resolve => setTimeout(resolve, 100)); }
  }
  assert.ok(port, 'Isolated browser starts');
  const targets = await (await fetch(`http://127.0.0.1:${port}/json/list`)).json();
  ws = new WebSocket(targets.find(row => row.type === 'page').webSocketDebuggerUrl);
  await new Promise((resolve, reject) => { ws.onopen = resolve; ws.onerror = reject; });
  let next = 0; const pending = new Map(), errors = [];
  ws.onmessage = event => {
    const message = JSON.parse(event.data), task = pending.get(message.id);
    if (message.method === 'Runtime.exceptionThrown') errors.push(message.params.exceptionDetails);
    if (!task) return;
    pending.delete(message.id); clearTimeout(task.timer);
    message.error ? task.reject(new Error(message.error.message)) : task.resolve(message.result);
  };
  const send = (method, params = {}) => new Promise((resolve, reject) => {
    const id = ++next, timer = setTimeout(() => reject(new Error(method)), 10000);
    pending.set(id, {resolve, reject, timer}); ws.send(JSON.stringify({id, method, params}));
  });
  const evaluate = async expression => {
    const result = await send('Runtime.evaluate', {expression, returnByValue: true});
    assert.ok(!result.exceptionDetails, JSON.stringify(result.exceptionDetails));
    return result.result.value;
  };
  const waitFor = async expression => {
    for (let i = 0; i < 100; i++) {
      if (await evaluate(expression)) return;
      await new Promise(resolve => setTimeout(resolve, 50));
    }
    assert.fail(`${expression}\n${JSON.stringify(errors)}`);
  };
  const screenshot = async (name, history = false) => {
    const width = await evaluate('innerWidth');
    const height = await evaluate('document.documentElement.scrollHeight + 100');
    await send('Emulation.setDeviceMetricsOverride', {width, height, deviceScaleFactor: 1, mobile: false});
    await evaluate('window.scrollTo(0, 0)');
    const clip = await evaluate(`(() => {
      const panel = document.getElementById('buyer-return-form-card').getBoundingClientRect();
      const top = ${history} ? document.getElementById('return-status-card').getBoundingClientRect().top : panel.top;
      return {x: Math.max(0, panel.left - 4), y: top + scrollY - 4, width: panel.width + 8, height: panel.bottom - top + 8, scale: 1};
    })()`);
    const captured = await send('Page.captureScreenshot', {format: 'png', captureBeyondViewport: true, clip});
    await writeFile(new URL(name, output), Buffer.from(captured.data, 'base64'));
    await send('Emulation.setDeviceMetricsOverride', {width, height: 1000, deviceScaleFactor: 1, mobile: false});
  };
  const token = sub => `fixture.${Buffer.from(JSON.stringify({sub, role: 'buyer'})).toString('base64url')}.fixture`;
  await send('Page.enable'); await send('Runtime.enable'); await send('Network.enable');
  // The task does not use the tracker's external map; exercise its existing offline fallback.
  await send('Network.setBlockedURLs', {urls: ['https://unpkg.com/*']});
  await send('Page.addScriptToEvaluateOnNewDocument', {source: `localStorage.setItem('access_token', ${JSON.stringify(token('2'))});`});
  for (const width of [390, 768, 1280]) {
    await send('Emulation.setDeviceMetricsOverride', {width, height: 1000, deviceScaleFactor: 1, mobile: false});
    await send('Page.navigate', {url: `${base}/orders/10`});
    await waitFor('!document.getElementById("return-request-action").hidden');
    await evaluate('document.getElementById("return-request-action").click()');
    assert.equal(await evaluate('document.getElementById("return-seller-order-select").options.length'), 2);
    assert.equal(await evaluate('document.getElementById("return-seller-order-select").value'), '21');
    await screenshot(`return-form-${width}.png`);
    const overflow = await evaluate('document.documentElement.scrollWidth <= document.documentElement.clientWidth');
    if (!overflow) console.log(await evaluate('JSON.stringify([...document.querySelectorAll("body *")].filter(el => el.getBoundingClientRect().right > innerWidth + 1).slice(0, 15).map(el => ({id:el.id, tag:el.tagName, class:el.className, right:el.getBoundingClientRect().right, width:el.getBoundingClientRect().width})))'));
    assert.equal(overflow, true, `Overflow ${width}`);
  }
  await send('Emulation.setDeviceMetricsOverride', {width: 390, height: 1000, deviceScaleFactor: 1, mobile: false});
  await evaluate('document.getElementById("buyer-return-form").requestSubmit()');
  await waitFor('document.activeElement.id === "return-reason-input"');
  assert.equal(writes.length, 0);
  await screenshot('return-validation-390.png');
  validationFailure = true;
  const fill = `document.getElementById('return-reason-input').value = 'Damaged parcel';
    document.getElementById('return-evidence-input').value = 'Photo: https://example.com/damaged-parcel.jpg';`;
  await evaluate(`${fill} document.getElementById('buyer-return-form').requestSubmit()`);
  await waitFor('document.activeElement.id === "return-evidence-input" && !document.getElementById("return-form-error").hidden');
  assert.equal(await evaluate('document.getElementById("return-reason-input").value'), 'Damaged parcel');
  validationFailure = false;
  await evaluate('document.getElementById("buyer-return-form").requestSubmit()');
  await waitFor('document.getElementById("return-feedback").textContent.includes("#31 submitted") && document.querySelectorAll(".buyer-return-request").length === 1');
  assert.equal(writes.at(-1).seller_order_id, 21);
  assert.equal(await evaluate('document.querySelectorAll("#return-requests-list img, #return-requests-list a").length'), 0);
  await screenshot('return-submitted-390.png', true);
  order = structuredClone(initial); rows = []; uncertain = true;
  await send('Page.reload');
  await waitFor('!document.getElementById("return-request-action").hidden');
  await evaluate(`document.getElementById('return-request-action').click(); ${fill}
    document.getElementById('return-evidence-input').value = '<img onerror=alert(1)> Photo reference';
    document.getElementById('buyer-return-form').requestSubmit()`);
  await waitFor('!document.getElementById("return-retry").hidden');
  const postsBeforeRetry = writes.length;
  await evaluate('document.getElementById("return-retry").click()');
  await waitFor('document.getElementById("return-feedback").textContent.includes("#31 is recorded")');
  assert.equal(writes.length, postsBeforeRetry, 'Retry reads existing state without repeating POST');
  assert.equal(await evaluate('document.querySelectorAll("#return-requests-list img, #return-requests-list a").length'), 0);
  await evaluate(`localStorage.setItem('access_token', ${JSON.stringify(token('3'))}); window.dispatchEvent(new StorageEvent('storage', {key: 'access_token'}))`);
  await waitFor('document.getElementById("buyer-return-form-card").hidden && !document.getElementById("error-message").hidden');
  assert.equal(await evaluate('document.getElementById("return-requests-list").children.length'), 0);
  assert.equal(errors.length, 0, JSON.stringify(errors));
  console.log('Native buyer-return checks passed: 390/768/1280px, focus, draft recovery, submit, reconciliation and account change.');
} finally {
  ws?.close(); browser.kill();
  await new Promise(resolve => server.close(resolve));
  server.closeAllConnections();
}
