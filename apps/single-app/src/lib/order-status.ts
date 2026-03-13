import { prisma } from './prisma';

export const ORDER_STATUSES = ['PENDING', 'FILLED', 'CANCELED', 'FAILED'] as const;
export type OrderStatus = (typeof ORDER_STATUSES)[number];

export const TERMINAL_ORDER_STATUSES: ReadonlySet<OrderStatus> = new Set([
  'FILLED',
  'CANCELED',
  'FAILED',
]);

const ALLOWED_TRANSITIONS: Readonly<Record<OrderStatus, readonly OrderStatus[]>> = {
  PENDING: ['FILLED', 'CANCELED', 'FAILED'],
  FILLED: [],
  CANCELED: [],
  FAILED: [],
};

export class OrderStatusTransitionError extends Error {
  readonly code:
    | 'UNKNOWN_ORDER_STATUS'
    | 'INVALID_ORDER_STATUS_TRANSITION'
    | 'ORDER_NOT_FOUND'
    | 'ORDER_STATE_CONFLICT';
  readonly details: Record<string, unknown>;

  constructor(
    code: OrderStatusTransitionError['code'],
    message: string,
    details: Record<string, unknown> = {}
  ) {
    super(message);
    this.name = 'OrderStatusTransitionError';
    this.code = code;
    this.details = details;
  }
}

export function parseOrderStatus(raw: string): OrderStatus {
  const normalized = raw.trim().toUpperCase();
  if ((ORDER_STATUSES as readonly string[]).includes(normalized)) {
    return normalized as OrderStatus;
  }

  throw new OrderStatusTransitionError('UNKNOWN_ORDER_STATUS', `Unknown order status: ${raw}`, {
    raw,
    normalized,
    allowed: ORDER_STATUSES,
  });
}

export function getAllowedNextStatuses(from: OrderStatus): readonly OrderStatus[] {
  return ALLOWED_TRANSITIONS[from];
}

export function canTransitionOrderStatus(from: OrderStatus, to: OrderStatus): boolean {
  if (from === to) return true;
  return ALLOWED_TRANSITIONS[from].includes(to);
}

export function assertOrderStatusTransition(from: OrderStatus, to: OrderStatus): void {
  if (!canTransitionOrderStatus(from, to)) {
    throw new OrderStatusTransitionError(
      'INVALID_ORDER_STATUS_TRANSITION',
      `Invalid order status transition: ${from} -> ${to}`,
      {
        from,
        to,
        terminal: TERMINAL_ORDER_STATUSES.has(from),
        allowedNext: ALLOWED_TRANSITIONS[from],
      }
    );
  }
}

export async function transitionOrderStatus(params: {
  orderId: string;
  to: string;
}): Promise<OrderStatus> {
  const next = parseOrderStatus(params.to);

  const currentOrder = await prisma.order.findUnique({
    where: { id: params.orderId },
    select: { id: true, status: true },
  });

  if (!currentOrder) {
    throw new OrderStatusTransitionError('ORDER_NOT_FOUND', `Order not found: ${params.orderId}`, {
      orderId: params.orderId,
    });
  }

  const current = parseOrderStatus(currentOrder.status);
  assertOrderStatusTransition(current, next);

  if (current === next) {
    return current;
  }

  const updated = await prisma.order.updateMany({
    where: {
      id: params.orderId,
      status: current,
    },
    data: {
      status: next,
    },
  });

  if (updated.count !== 1) {
    throw new OrderStatusTransitionError(
      'ORDER_STATE_CONFLICT',
      `Order status changed concurrently for order=${params.orderId}`,
      {
        orderId: params.orderId,
        expectedFrom: current,
        to: next,
      }
    );
  }

  return next;
}

export const ORDER_STATUS_TRANSITION_SPEC = ALLOWED_TRANSITIONS;
