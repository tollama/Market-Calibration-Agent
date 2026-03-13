import test from 'node:test';
import assert from 'node:assert/strict';

import { GET } from './route';

test('markets 응답에 advisory disclaimer 포함', async () => {
  const originalFetch = global.fetch;

  global.fetch = async () =>
    new Response(
      JSON.stringify({
        items: [{ id: 'm1', symbol: 'BTC', status: 'OPEN' }],
      }),
      {
        status: 200,
        headers: { 'content-type': 'application/json' },
      }
    );

  const response = await GET();
  const body = await response.json();

  assert.equal(response.status, 200);
  assert.equal(Array.isArray(body.items), true);
  assert.equal(body.disclaimer?.advisoryOnly, true);

  global.fetch = originalFetch;
});
