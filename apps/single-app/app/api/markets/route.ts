import { NextResponse } from 'next/server';

import { fetchMarketsFromConfiguredSource } from '../../../src/lib/markets-source';

export async function GET() {
  const result = await fetchMarketsFromConfiguredSource();

  if (!result.ok) {
    return NextResponse.json({
      items: [],
      count: 0,
      source: result.source,
      error: result.error
    });
  }

  return NextResponse.json({
    items: result.items,
    count: result.items.length,
    source: result.source
  });
}
