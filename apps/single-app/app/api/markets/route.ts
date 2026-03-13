import { NextResponse } from 'next/server';

import { fetchMarketsFromConfiguredSource } from '../../../src/lib/markets-source';
import { getAdvisoryDisclaimer, sanitizeAdvisoryText } from '../../../src/lib/advisory-policy';

export async function GET() {
  const result = await fetchMarketsFromConfiguredSource();

  const disclaimer = getAdvisoryDisclaimer('/api/markets');

  if (!result.ok) {
    return NextResponse.json({
      items: [],
      count: 0,
      source: result.source,
      error: {
        ...result.error,
        message: sanitizeAdvisoryText(result.error.message)
      },
      disclaimer
    });
  }

  return NextResponse.json({
    items: result.items,
    count: result.items.length,
    source: result.source,
    disclaimer
  });
}
