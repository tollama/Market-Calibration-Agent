export type MarketItem = {
  id: string;
  symbol: string;
  status: 'OPEN' | 'PAUSED' | 'CLOSED' | 'UNKNOWN';
  category: string | null;
  liquidityBucket: string | null;
  trustScore: number | null;
  asOf: string | null;
};

export type MarketsSourceSuccess = {
  ok: true;
  items: MarketItem[];
  source: string;
};

export type MarketsSourceFailure = {
  ok: false;
  items: [];
  source: 'fallback';
  error: {
    code: string;
    message: string;
  };
};

export type MarketsSourceResult = MarketsSourceSuccess | MarketsSourceFailure;

type UpstreamMarketsResponse = {
  items?: Array<Record<string, unknown>>;
  total?: number;
};

const DEFAULT_BASE_URL = 'http://127.0.0.1:8100';
const DEFAULT_PATH = '/markets';
const DEFAULT_TIMEOUT_MS = 5000;

function normalizeMarket(item: Record<string, unknown>): MarketItem {
  const id = String(item.market_id ?? item.id ?? 'unknown');

  return {
    id,
    symbol: String(item.symbol ?? item.ticker ?? item.market_id ?? item.id ?? 'unknown'),
    status: normalizeStatus(item.status),
    category: typeof item.category === 'string' ? item.category : null,
    liquidityBucket: typeof item.liquidity_bucket === 'string' ? item.liquidity_bucket : null,
    trustScore: typeof item.trust_score === 'number' ? item.trust_score : null,
    asOf: typeof item.as_of === 'string' ? item.as_of : null
  };
}

function normalizeStatus(status: unknown): MarketItem['status'] {
  if (typeof status !== 'string') return 'UNKNOWN';
  const upper = status.toUpperCase();
  if (upper === 'OPEN' || upper === 'PAUSED' || upper === 'CLOSED') return upper;
  return 'UNKNOWN';
}

function parseTimeoutMs(raw: string | undefined): number {
  const parsed = Number(raw);
  if (!Number.isFinite(parsed) || parsed <= 0) return DEFAULT_TIMEOUT_MS;
  return parsed;
}

export async function fetchMarketsFromConfiguredSource(): Promise<MarketsSourceResult> {
  const baseUrl = process.env.MARKETS_SOURCE_BASE_URL ?? DEFAULT_BASE_URL;
  const path = process.env.MARKETS_SOURCE_PATH ?? DEFAULT_PATH;
  const timeoutMs = parseTimeoutMs(process.env.MARKETS_SOURCE_TIMEOUT_MS);

  const url = new URL(path, baseUrl);

  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), timeoutMs);

  try {
    const response = await fetch(url, {
      method: 'GET',
      headers: {
        Accept: 'application/json'
      },
      cache: 'no-store',
      signal: controller.signal
    });

    if (!response.ok) {
      return {
        ok: false,
        source: 'fallback',
        items: [],
        error: {
          code: `UPSTREAM_HTTP_${response.status}`,
          message: `시장 데이터 조회 실패 (status=${response.status})`
        }
      };
    }

    const payload = (await response.json()) as UpstreamMarketsResponse;
    const rows = Array.isArray(payload?.items) ? payload.items : [];

    return {
      ok: true,
      source: url.toString(),
      items: rows.map((row) => normalizeMarket(row))
    };
  } catch (error) {
    if (error instanceof Error && error.name === 'AbortError') {
      return {
        ok: false,
        source: 'fallback',
        items: [],
        error: {
          code: 'UPSTREAM_TIMEOUT',
          message: `시장 데이터 조회 타임아웃 (${timeoutMs}ms)`
        }
      };
    }

    const message = error instanceof Error ? error.message : '알 수 없는 에러';
    return {
      ok: false,
      source: 'fallback',
      items: [],
      error: {
        code: 'UPSTREAM_FETCH_ERROR',
        message: `시장 데이터 조회 중 오류: ${message}`
      }
    };
  } finally {
    clearTimeout(timeout);
  }
}
