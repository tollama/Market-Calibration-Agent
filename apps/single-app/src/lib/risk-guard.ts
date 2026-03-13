import { prisma } from './prisma';

export type RiskGuardCode = 'RISK_LIMIT_EXCEEDED' | 'ORDER_RATE_LIMIT_EXCEEDED';

export class RiskGuardError extends Error {
  readonly code: RiskGuardCode;
  readonly status: number;
  readonly details: Record<string, unknown>;

  constructor(params: {
    code: RiskGuardCode;
    message: string;
    status?: number;
    details?: Record<string, unknown>;
  }) {
    super(params.message);
    this.name = 'RiskGuardError';
    this.code = params.code;
    this.status = params.status ?? 409;
    this.details = params.details ?? {};
  }
}

function toFinitePositiveInt(value: string | undefined, fallback: number): number {
  const parsed = Number(value);
  if (!Number.isFinite(parsed) || parsed <= 0) {
    return fallback;
  }
  return Math.floor(parsed);
}

function toFinitePositiveNumber(value: string | undefined, fallback: number): number {
  const parsed = Number(value);
  if (!Number.isFinite(parsed) || parsed <= 0) {
    return fallback;
  }
  return parsed;
}

function toNumber(value: unknown): number {
  if (typeof value === 'number') {
    return value;
  }
  if (typeof value === 'string') {
    return Number(value);
  }
  if (value && typeof value === 'object' && 'toNumber' in value) {
    return Number((value as { toNumber: () => number }).toNumber());
  }
  return Number.NaN;
}

function getTodayRange(now = new Date()) {
  const start = new Date(now);
  start.setHours(0, 0, 0, 0);
  const end = new Date(start);
  end.setDate(end.getDate() + 1);
  return { start, end };
}

export interface RiskGuardSnapshot {
  dailyLoss: {
    currentLossAbs: number;
    maxDailyLoss: number;
  };
  orderRate: {
    ordersLastMinute: number;
    limitPerMinute: number;
  };
}

export async function evaluateRiskGuards(): Promise<RiskGuardSnapshot> {
  const maxDailyLoss = toFinitePositiveNumber(process.env.RISK_MAX_DAILY_LOSS, 500000);
  const limitPerMinute = toFinitePositiveInt(process.env.ORDER_RATE_LIMIT_PER_MIN, 30);
  const { start, end } = getTodayRange();

  const [negativePnlAgg, ordersLastMinute] = await Promise.all([
    prisma.order.aggregate({
      _sum: { realizedPnl: true },
      where: {
        createdAt: {
          gte: start,
          lt: end,
        },
        realizedPnl: {
          lt: 0,
        },
      },
    }),
    prisma.order.count({
      where: {
        createdAt: {
          gte: new Date(Date.now() - 60_000),
        },
      },
    }),
  ]);

  const negativePnl = toNumber(negativePnlAgg._sum.realizedPnl);
  const currentLossAbs = Number.isFinite(negativePnl) ? Math.abs(negativePnl) : 0;

  return {
    dailyLoss: {
      currentLossAbs,
      maxDailyLoss,
    },
    orderRate: {
      ordersLastMinute,
      limitPerMinute,
    },
  };
}

export async function assertRiskGuardsOrThrow(context: 'producer' | 'worker') {
  const snapshot = await evaluateRiskGuards();

  if (snapshot.dailyLoss.currentLossAbs >= snapshot.dailyLoss.maxDailyLoss) {
    throw new RiskGuardError({
      code: 'RISK_LIMIT_EXCEEDED',
      message: `[${context}] blocked: daily loss limit exceeded`,
      details: {
        currentLossAbs: snapshot.dailyLoss.currentLossAbs,
        maxDailyLoss: snapshot.dailyLoss.maxDailyLoss,
      },
    });
  }

  if (snapshot.orderRate.ordersLastMinute >= snapshot.orderRate.limitPerMinute) {
    throw new RiskGuardError({
      code: 'ORDER_RATE_LIMIT_EXCEEDED',
      message: `[${context}] blocked: order rate limit exceeded`,
      details: {
        ordersLastMinute: snapshot.orderRate.ordersLastMinute,
        limitPerMinute: snapshot.orderRate.limitPerMinute,
      },
    });
  }

  return snapshot;
}
