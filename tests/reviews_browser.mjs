// Run: node tests/reviews_browser.mjs (uses installed Chrome/Edge, no npm packages).
// Native DOM/layout checks use deterministic API fixtures; persistence is tested in Python.
import assert from 'node:assert/strict';
import {spawn} from 'node:child_process';
import {createServer} from 'node:http';
import {existsSync} from 'node:fs';
import {readFile, mkdir, mkdtemp, writeFile} from 'node:fs/promises';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
const root = new URL('../', import.meta.url);
const executable = process.env.BROWSER_PATH || [
  'C:/Program Files/Google/Chrome/Application/chrome.exe',
  'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe',
].find(existsSync);
assert.ok(executable, 'Set BROWSER_PATH to an installed Chromium browser');
const profile = await mkdtemp(join(tmpdir(), 'reviews131-browser-'));
const output = new URL('../docs/images/us15/', import.meta.url);
await mkdir(output, {recursive: true});
let base, reviewed = false, reviewFailure = false, listFailures = 0;
const writes = [];
const reviews = [{id: 1, rating: 5, comment: 'Comfortable fabric. Arrived as described.',
  created_at: '2026-10-20T10:00:00Z', seller_reply: 'Thank you for sharing your experience!',
  seller_replied_at: '2026-10-21T09:30:00Z'},
  {id: 2, rating: 4, comment: 'Good fit and packaging.', created_at: '2026-10-22T10:00:00Z',
    seller_reply: null, seller_replied_at: null}];
const server = createServer(async (request, response) => {
  try {
    const path = new URL(request.url, 'http://localhost').pathname;
    const json = (value, status = 200) => {
      response.writeHead(status, {'Content-Type': 'application/json'}).end(JSON.stringify(value));
    };
    if (path.startsWith('/api/')) {
      if (path === '/api/v1/auth/me') {
        const token = request.headers.authorization?.split(' ')[1];
        const seller = JSON.parse(Buffer.from(token.split('.')[1], 'base64url')).role === 'seller';
        json({id: seller ? 7 : 3, role: seller ? 'seller' : 'buyer'}); return;
      }
      if (path.endsWith('/reviewable-items')) {
        json({data: reviewed ? [] : [{order_item_id: 42, quantity: 1}]}); return;
      }
      if (path === '/api/v1/products/REVIEW-131') {
        json({id: 10, seller_id: 7, name: 'Everyday cotton shirt', price: 180000,
          description: 'Soft cotton with a relaxed fit. Verified customer feedback below.',
          stock_quantity: 8, review_count: reviews.length, rating: 4.5,
          image_url: `${base}/static/product-placeholder.svg`}); return;
      }
      if (path.endsWith('/reviews') && request.method !== 'POST') {
        if (listFailures > 0) { listFailures--; json({error: {message: 'Reviews unavailable. Try again.'}}, 503); return; }
        json({data: reviews.map((review, index) => ({...review, media_urls: review.media_urls ??
          (index ? [] : [`${base}/static/product-placeholder.svg`, `${base}/sample.webm`])})),
          rating: reviews.reduce((sum, row) => sum + row.rating, 0) / reviews.length,
          review_count: reviews.length}); return;
      }
      if (path.includes('/variants')) { json({data: []}); return; }
      let body = '';
      for await (const chunk of request) body += chunk;
      const payload = JSON.parse(body);
      writes.push({path, payload});
      if (reviewFailure) { json({error: {message: 'Please check your review.'}}, 422); return; }
      if (path.endsWith('/reply')) {
        reviews[0].seller_reply = payload.reply;
        reviews[0].seller_replied_at = '2026-10-29T02:30:00Z';
        json({data: reviews[0]}); return;
      }
      reviewed = true;
      reviews.push({id: 3, rating: payload.rating, comment: payload.comment,
        media_urls: payload.media_urls, created_at: '2026-10-29T02:00:00Z'});
      json({data: reviews.at(-1)}, 201); return;
    }
    const file = path === '/products/REVIEW-131' ? 'src/web/pages/product-detail.html'
      : /^\/static\/[\w.-]+$/.test(path) ? `src/web${path}` : null;
    if (!file) { response.writeHead(404).end(); return; }
    response.setHeader('Content-Type', file.endsWith('.js') ? 'text/javascript'
      : file.endsWith('.css') ? 'text/css' : file.endsWith('.svg') ? 'image/svg+xml' : 'text/html');
    response.end(await readFile(new URL(file, root)));
  } catch (error) { response.writeHead(500).end(String(error)); }
});
await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
base = `http://127.0.0.1:${server.address().port}`;
const browser = spawn(executable, ['--headless=new', '--disable-gpu', '--no-first-run',
  '--remote-debugging-port=0', `--user-data-dir=${profile}`], {windowsHide: true, stdio: ['ignore', 'ignore', 'pipe']});
let browserError = '';
browser.stderr.on('data', chunk => { browserError += chunk.toString(); });
let ws;
try {
  let port;
  for (let i = 0; i < 100; i++) {
    try { port = (await readFile(join(profile, 'DevToolsActivePort'), 'utf8')).split('\n')[0]; break; }
    catch { await new Promise(resolve => setTimeout(resolve, 100)); }
  }
  assert.ok(port, `Browser starts: ${browserError.slice(-1500)}`);
  const targets = await (await fetch(`http://127.0.0.1:${port}/json/list`)).json();
  ws = new WebSocket(targets.find(target => target.type === 'page').webSocketDebuggerUrl);
  await new Promise((resolve, reject) => { ws.onopen = resolve; ws.onerror = reject; });
  let id = 0, authScript;
  const pending = new Map();
  ws.onmessage = event => {
    const message = JSON.parse(event.data), task = pending.get(message.id);
    if (!task) return;
    pending.delete(message.id); clearTimeout(task.timer);
    message.error ? task.reject(new Error(message.error.message)) : task.resolve(message.result);
  };
  const send = (method, params = {}) => new Promise((resolve, reject) => {
    const next = ++id;
    const timer = setTimeout(() => { pending.delete(next); reject(new Error(method)); }, 10000);
    pending.set(next, {resolve, reject, timer}); ws.send(JSON.stringify({id: next, method, params}));
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
    assert.fail(expression);
  };
  const viewport = width => send('Emulation.setDeviceMetricsOverride', {
    width, height: 1000, deviceScaleFactor: 1, mobile: false,
  });
  const screenshot = async name => {
    const result = await send('Page.captureScreenshot', {format: 'png', captureBeyondViewport: true});
    await writeFile(new URL(name, output), Buffer.from(result.data, 'base64'));
  };
  const navigate = async role => {
    if (authScript) await send('Page.removeScriptToEvaluateOnNewDocument', {identifier: authScript});
    const token = `fixture.${Buffer.from(JSON.stringify({sub: role === 'seller' ? '7' : '3', role})).toString('base64url')}.fixture`;
    authScript = (await send('Page.addScriptToEvaluateOnNewDocument', {
      source: `localStorage.setItem('access_token', ${JSON.stringify(token)});`,
    })).identifier;
    await send('Page.navigate', {url: `${base}/products/REVIEW-131`});
    await waitFor('document.querySelectorAll(".review-card").length > 0');
  };
  await send('Page.enable');
  for (const width of [390, 768, 1280]) {
    await viewport(width); await navigate('buyer');
    await waitFor('document.getElementById("review-form").hidden === false');
    assert.equal(await evaluate('document.documentElement.scrollWidth <= document.documentElement.clientWidth'), true, `Overflow ${width}`);
    assert.equal(await evaluate('document.querySelectorAll(".review-media__image").length'), 1);
    assert.equal(await evaluate('document.querySelector(".review-media__video").controls'), true);
    assert.equal(await evaluate('document.querySelector(".review-card__reply time").dateTime'), '2026-10-21T09:30:00.000Z');
    await screenshot(`reviews-${width}.png`);
  }
  await viewport(390);
  await evaluate('document.getElementById("review-media-url").value = "javascript:bad"; document.getElementById("review-form").requestSubmit()');
  await waitFor('document.activeElement.id === "review-media-url"');
  assert.equal(writes.length, 0);
  await screenshot('review-validation-390.png');
  reviewFailure = true;
  await evaluate(`document.getElementById('review-media-url').value = ${JSON.stringify(`${base}/static/product-placeholder.svg`)};
    document.getElementById('review-comment').value = 'Keep this draft'; document.getElementById('review-form').requestSubmit()`);
  await waitFor('document.getElementById("review-form-status").textContent === "Please check your review."');
  assert.equal(await evaluate('document.getElementById("review-comment").value'), 'Keep this draft');
  reviewFailure = false;
  await evaluate('document.getElementById("review-form").requestSubmit()');
  await waitFor('document.getElementById("review-form").hidden && document.getElementById("review-form-status").textContent.includes("was submitted")');
  assert.equal(writes.at(-1).payload.media_urls.length, 1);
  await viewport(1280); await navigate('seller');
  await waitFor('document.querySelectorAll(".seller-reply-form").length > 0');
  assert.equal(await evaluate('document.querySelector("label[for=seller-reply-1]") !== null'), true);
  await evaluate('document.getElementById("seller-reply-1").value = "Thanks for the photo!"; document.querySelector(".seller-reply-form").requestSubmit()');
  await waitFor('document.getElementById("reviews-feedback").textContent === "Seller reply saved." && document.querySelector(".review-card__reply p").textContent === "Thanks for the photo!"');
  await screenshot('seller-reply-1280.png');
  listFailures = 1;
  await send('Page.reload');
  await waitFor('document.getElementById("reviews-retry").hidden === false');
  await evaluate('document.getElementById("reviews-retry").click()');
  await waitFor('document.getElementById("reviews-error").hidden && document.getElementById("reviews-list").hidden === false');
  console.log('Native review checks passed: 390/768/1280px, media/fallback, UTC reply time, validation focus, draft recovery, submit, seller reply and retry.');
} finally {
  ws?.close(); browser.kill(); server.close();
}
