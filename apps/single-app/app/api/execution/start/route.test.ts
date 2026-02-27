import test from 'node:test';
import assert from 'node:assert/strict';
import { NextRequest } from 'next/server';

import { POST } from './route';

test('인증 실패(401) 응답에도 disclaimer/advisory 메타 포함', async () => {
  const prevToken = process.env.ADMIN_API_TOKEN;
  const prevEnabled = process.env.EXECUTION_API_ENABLED;

  process.env.ADMIN_API_TOKEN = 'test-token';
  process.env.EXECUTION_API_ENABLED = 'false';

  const req = new NextRequest('http://localhost:3000/api/execution/start', {
    method: 'POST',
    headers: {
      'content-type': 'application/json',
    },
    body: JSON.stringify({ mode: 'paper', dryRun: true }),
  });

  const response = await POST(req);
  const body = await response.json();

  assert.equal(response.status, 401);
  assert.equal(body.disclaimer?.advisoryOnly, true);
  assert.equal(body.advisory?.scope, '/api/execution/start');
  assert.equal(body.advisory?.executionEnabled, false);

  if (prevToken === undefined) {
    delete process.env.ADMIN_API_TOKEN;
  } else {
    process.env.ADMIN_API_TOKEN = prevToken;
  }

  if (prevEnabled === undefined) {
    delete process.env.EXECUTION_API_ENABLED;
  } else {
    process.env.EXECUTION_API_ENABLED = prevEnabled;
  }
});

test('EXECUTION_API_ENABLED=false 이면 execution/start 차단', async () => {
  const prevToken = process.env.ADMIN_API_TOKEN;
  const prevEnabled = process.env.EXECUTION_API_ENABLED;

  process.env.ADMIN_API_TOKEN = 'test-token';
  process.env.EXECUTION_API_ENABLED = 'false';

  const req = new NextRequest('http://localhost:3000/api/execution/start', {
    method: 'POST',
    headers: {
      authorization: 'Bearer test-token',
      'content-type': 'application/json',
    },
    body: JSON.stringify({ mode: 'paper', dryRun: true }),
  });

  const response = await POST(req);
  const body = await response.json();

  assert.equal(response.status, 403);
  assert.equal(body.code, 'EXECUTION_DISABLED');
  assert.equal(body.disclaimer?.advisoryOnly, true);
  assert.equal(body.advisory?.scope, '/api/execution/start');
  assert.equal(body.advisory?.executionEnabled, false);

  if (prevToken === undefined) {
    delete process.env.ADMIN_API_TOKEN;
  } else {
    process.env.ADMIN_API_TOKEN = prevToken;
  }

  if (prevEnabled === undefined) {
    delete process.env.EXECUTION_API_ENABLED;
  } else {
    process.env.EXECUTION_API_ENABLED = prevEnabled;
  }
});
