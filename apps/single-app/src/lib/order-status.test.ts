import test from 'node:test';
import assert from 'node:assert/strict';

import {
  ORDER_STATUS_TRANSITION_SPEC,
  ORDER_STATUSES,
  TERMINAL_ORDER_STATUSES,
  assertOrderStatusTransition,
  canTransitionOrderStatus,
  parseOrderStatus,
  type OrderStatus,
} from './order-status';

test('parseOrderStatus는 대소문자/공백을 정규화한다', () => {
  assert.equal(parseOrderStatus(' pending '), 'PENDING');
  assert.equal(parseOrderStatus('FILLED'), 'FILLED');
});

test('상태 전이 명세가 terminal 역전이를 차단한다', () => {
  for (const terminal of TERMINAL_ORDER_STATUSES) {
    for (const status of ORDER_STATUSES) {
      if (terminal === status) {
        assert.equal(canTransitionOrderStatus(terminal, status), true);
      } else {
        assert.equal(canTransitionOrderStatus(terminal, status), false);
      }
    }
  }
});

test('PENDING -> FILLED/CANCELED/FAILED 전이는 허용된다', () => {
  const allowed: OrderStatus[] = ['FILLED', 'CANCELED', 'FAILED'];

  for (const next of allowed) {
    assert.doesNotThrow(() => assertOrderStatusTransition('PENDING', next));
    assert.equal(canTransitionOrderStatus('PENDING', next), true);
  }
});

test('PENDING <- FILLED 역전이는 거부된다', () => {
  assert.throws(
    () => assertOrderStatusTransition('FILLED', 'PENDING'),
    /Invalid order status transition: FILLED -> PENDING/
  );
});

test('명세 테이블은 단일 경로 규칙과 일치한다', () => {
  assert.deepEqual(ORDER_STATUS_TRANSITION_SPEC, {
    PENDING: ['FILLED', 'CANCELED', 'FAILED'],
    FILLED: [],
    CANCELED: [],
    FAILED: [],
  });
});
