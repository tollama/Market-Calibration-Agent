import { PrismaClient } from '@prisma/client';

const prisma = new PrismaClient();

async function main() {
  const now = new Date();

  await prisma.order.createMany({
    data: [
      {
        market: 'BTC-YES-2026Q1',
        side: 'BUY',
        quantity: '10.00000000',
        price: '0.62000000',
        status: 'FILLED',
        realizedPnl: '-120.50000000'
      },
      {
        market: 'ETH-NO-2026Q1',
        side: 'SELL',
        quantity: '5.50000000',
        price: '0.41000000',
        status: 'PENDING',
        realizedPnl: '80.00000000'
      }
    ]
  });

  await prisma.position.createMany({
    data: [
      {
        market: 'BTC-YES-2026Q1',
        size: '10.00000000',
        entryPrice: '0.62000000',
        pnl: '0.12000000'
      },
      {
        market: 'ETH-NO-2026Q1',
        size: '-5.50000000',
        entryPrice: '0.41000000',
        pnl: '-0.03000000'
      }
    ]
  });

  await prisma.calibrationRun.createMany({
    data: [
      {
        status: 'COMPLETED',
        startedAt: new Date(now.getTime() - 10 * 60 * 1000),
        finishedAt: new Date(now.getTime() - 8 * 60 * 1000),
        notes: 'initial seed run'
      },
      {
        status: 'STARTED',
        startedAt: new Date(now.getTime() - 2 * 60 * 1000),
        notes: 'ongoing calibration run sample'
      }
    ]
  });
}

main()
  .then(async () => {
    await prisma.$disconnect();
  })
  .catch(async (error) => {
    console.error(error);
    await prisma.$disconnect();
    process.exit(1);
  });
