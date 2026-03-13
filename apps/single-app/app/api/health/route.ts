import { NextResponse } from 'next/server';

import { withAdvisory } from '../../../src/lib/advisory-policy';
import { prisma } from '../../../src/lib/prisma';

export async function GET() {
  try {
    await prisma.$queryRaw`SELECT 1`;

    return NextResponse.json({
      ok: true,
      service: 'single-app',
      now: new Date().toISOString(),
      db: {
        ok: true
      }
    });
  } catch (error) {
    console.error('[health] database check failed', error);

    return NextResponse.json(
      withAdvisory('/api/health', {
        ok: false,
        service: 'single-app',
        now: new Date().toISOString(),
        db: {
          ok: false,
          error: 'DB connection failed'
        }
      }),
      { status: 503 }
    );
  }
}
