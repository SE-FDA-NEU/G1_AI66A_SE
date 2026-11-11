import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';

const code = fs.readFileSync('src/web/static/login.js', 'utf8');
const status = { textContent: '' };
const form = { addEventListener() {} };
const button = { getBoundingClientRect: () => ({ width: 320 }) };
let googleCallback;
let insertedScript;
const elements = { 'login-form': form, 'login-error': {}, 'google-signin-status': status, 'google-signin-button': button };
const document = {
  getElementById: id => elements[id],
  createElement: () => ({}),
  head: { appendChild: script => { insertedScript = script; } },
};
const requests = [];
const fetch = async (url, options) => {
  requests.push({ url, options });
  return url.endsWith('/config')
    ? { ok: true, json: async () => ({ client_id: 'client.apps.googleusercontent.com' }) }
    : { ok: true, json: async () => ({ access_token: 'app-jwt', user: { role: 'buyer' } }) };
};
let saved, destination;
const context = {
  document, fetch, URLSearchParams,
  window: { location: { search: '?return_to=%2Fcart', assign: value => { destination = value; } } },
  localStorage: { setItem: (key, value) => { saved = [key, value]; } },
  google: { accounts: { id: {
    initialize: options => { googleCallback = options.callback; },
    renderButton: target => assert.equal(target, button),
  } } },
};
vm.runInNewContext(code, context);
await new Promise(resolve => setTimeout(resolve, 0));
assert.equal(insertedScript.src, 'https://accounts.google.com/gsi/client');
insertedScript.onload();
await googleCallback({ credential: 'google-token' });
assert.equal(requests[1].url, '/api/v1/auth/google');
assert.deepEqual(JSON.parse(requests[1].options.body), { credential: 'google-token' });
assert.deepEqual(saved, ['access_token', 'app-jwt']);
assert.equal(destination, '/cart');
console.log('Google sign-in UI checks passed');
