import test from 'node:test';
import assert from 'node:assert/strict';

import {
  getAdvisoryDisclaimer,
  isExecutionApiEnabled,
  sanitizeAdvisoryText,
} from './advisory-policy';

test('advisory disclaimer 기본 필드 포함', () => {
  const disclaimer = getAdvisoryDisclaimer('/api/markets');

  assert.equal(disclaimer.advisoryOnly, true);
  assert.equal(disclaimer.notInvestmentAdvice, true);
  assert.equal(disclaimer.notLegalAdvice, true);
  assert.match(disclaimer.message, /정보 제공 전용/);
});

test('직접 거래 권유 문구를 서버측에서 치환', () => {
  const input = '지금 매수하고 buy now 하세요';
  const output = sanitizeAdvisoryText(input);

  assert.equal(output.includes('지금 매수'), false);
  assert.equal(output.toLowerCase().includes('buy now'), false);
  assert.match(output, /직접 거래 지시 문구/);
});

test('EXECUTION_API_ENABLED 환경변수 해석', () => {
  const previous = process.env.EXECUTION_API_ENABLED;
  process.env.EXECUTION_API_ENABLED = 'false';
  assert.equal(isExecutionApiEnabled(), false);

  process.env.EXECUTION_API_ENABLED = 'true';
  assert.equal(isExecutionApiEnabled(), true);

  if (previous === undefined) {
    delete process.env.EXECUTION_API_ENABLED;
  } else {
    process.env.EXECUTION_API_ENABLED = previous;
  }
});
