import test from 'node:test';
import assert from 'node:assert/strict';

import { GET } from './route';
import { prisma } from '../../../src/lib/prisma';

test('health 공통 에러 응답에도 disclaimer/advisory 메타 포함', async () => {
  const originalQueryRaw = prisma.$queryRaw;

  (prisma.$queryRaw as unknown as () => Promise<unknown>) = async () => {
    throw new Error('forced health db error');
  };

  try {
    const response = await GET();
    const body = await response.json();

    assert.equal(response.status, 503);
    assert.equal(body.ok, false);
    assert.equal(body.disclaimer?.advisoryOnly, true);
    assert.equal(body.advisory?.scope, '/api/health');
    assert.equal(typeof body.advisory?.executionEnabled, 'boolean');
  } finally {
    prisma.$queryRaw = originalQueryRaw;
  }
});
