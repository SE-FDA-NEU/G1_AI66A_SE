import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';

const code = fs.readFileSync('src/web/static/backend-runtime.js', 'utf8');
for (const origin of ['', 'https://demo.trycloudflare.com']) {
  const calls = [];
  const window = { MARKETPLACE_API_ORIGIN: origin, fetch: (...args) => calls.push(args) };
  vm.runInNewContext(code, { window, URL });
  const headers = { Authorization: 'Bearer demo', 'Idempotency-Key': 'key' };
  window.fetch('/api/v1/orders?limit=2', { method: 'POST', headers });
  assert.equal(calls[0][0], origin + '/api/v1/orders?limit=2');
  assert.equal(calls[0][1].headers, headers);
  window.fetch('/static/base.css');
  assert.equal(calls[1][0], '/static/base.css');
  assert.equal(window.marketplaceImageUrl('/api/v1/products/P/image'), origin + '/api/v1/products/P/image');
  assert.equal(window.marketplaceImageUrl('/static/product-placeholder.svg'), '/static/product-placeholder.svg');
  assert.equal(window.marketplaceImageUrl('https://images.example/p.png'), 'https://images.example/p.png');
}
console.log('Backend runtime checks passed');
