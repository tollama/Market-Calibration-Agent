import { PrismaClient } from '@prisma/client';
import { assertRiskGuardsOrThrow } from '../src/lib/risk-guard';

const prisma = new PrismaClient();

async function main() {
  await prisma.order.create({
    data: {
      market: 'SMOKE-RATE',
      side: 'BUY',
      quantity: '1',
      price: '0.5',
      status: 'FILLED',
      realizedPnl: '0',
    },
  });

  process.env.ORDER_RATE_LIMIT_PER_MIN = '1';

  try {
    await assertRiskGuardsOrThrow('producer');
    console.log('[risk-smoke] unexpected-pass');
    process.exit(1);
  } catch (e) {
    console.log('[risk-smoke] blocked', (e as { code?: string }).code ?? 'UNKNOWN');
  }
}

main()
  .catch((e) => {
    console.error('[risk-smoke] failed', e);
    process.exit(1);
  })
  .finally(async () => {
    await prisma.$disconnect();
  });
