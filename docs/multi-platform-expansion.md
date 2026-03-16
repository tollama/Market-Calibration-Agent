# Multi-Platform Prediction Market Expansion

## 1) What It Is

The Multi-Platform Expansion extends the Market Calibration Agent from a single-platform system (Polymarket-only) to a multi-platform prediction market aggregation and calibration engine. It introduces a connector abstraction layer, platform-specific connectors for **Kalshi** and **Manifold Markets**, and a generalized ingestion pipeline — all while preserving full backward compatibility with existing Polymarket data flows.

### Scope of the expansion

| Component | Description |
|---|---|
| **Connector Abstraction** | Protocol-based interfaces (`MarketDataConnector`, `MetricsConnector`, `RealtimeConnector`) enabling uniform connector behavior across platforms |
| **Kalshi Connector** | Async REST client for Kalshi's Trading API with bearer-token auth, cursor pagination, and normalization |
| **Manifold Connector** | Async REST client for Manifold Markets' open API with before-cursor pagination and deduplication |
| **Platform Normalizers** | Field-mapping modules that translate platform-specific schemas into the canonical `MarketSnapshot` format |
| **Connector Factory** | Factory functions that instantiate the correct connector for any `Platform` enum value |
| **Generalized Ingestion** | `ingest_platform_raw` pipeline that works with any connector, plus `multi_platform_ingest` orchestrator |
| **Schema Extensions** | `Platform` enum and `platform` field on `MarketSnapshot` and `MarketRegistry` |
| **Config & API** | Platform enable/disable in `configs/default.yaml`, platform query filter on API endpoints |

### Supported platforms

| Platform | Market Type | Auth | Realtime | Status |
|---|---|---|---|---|
| **Polymarket** | Binary | None (public REST) | WebSocket | Production (existing) |
| **Kalshi** | Binary (regulated) | Bearer token (API key) | Not yet | Connector ready |
| **Manifold Markets** | Binary + Multi-outcome | None (open API) | Not yet | Connector ready |
| **Metaculus** | — | — | — | Enum reserved, connector TBD |

---

## 2) Why This Is Needed

### Single-platform dependency is a structural risk

Relying exclusively on Polymarket creates concentration risk across multiple dimensions:

- **Coverage gaps**: Polymarket focuses on politics, crypto, and pop culture. Kalshi covers regulated financial markets (Fed rates, economic indicators, weather). Manifold covers community-driven long-tail questions. No single platform covers the full prediction landscape.
- **Availability risk**: If Polymarket experiences downtime, API changes, or regulatory restrictions, the entire calibration pipeline stalls.
- **Selection bias**: Calibration metrics computed on a single platform's question set may not generalize. Accuracy measured on politically-focused questions does not tell you much about market reliability on economic or scientific questions.
- **Liquidity blindspots**: Some markets have thin liquidity on one platform but deep liquidity on another. Cross-platform comparison reveals which platform is more informative for a given question category.

### Regulatory landscape is evolving

The US prediction market landscape is under active regulatory development. Kalshi operates as a CFTC-regulated exchange. Polymarket operates offshore. Regulatory shifts could change platform availability — multi-platform support provides resilience against these changes.

### Cross-platform calibration unlocks new analytical capabilities

With data from multiple platforms on the same or similar questions:

- **Cross-platform arbitrage detection**: Divergent probabilities on the same question flag potential mispricings.
- **Platform-comparative trust scoring**: Compare calibration quality across platforms to identify which platform is most reliable for a given category.
- **Ensemble probability estimation**: Weight probabilities from multiple platforms based on their calibration history for more accurate composite signals.

---

## 3) What Benefits It Brings

### For quant/research teams

- **Broader question coverage**: Access markets spanning politics (Polymarket), regulated finance (Kalshi), and community-driven topics (Manifold) through a single pipeline.
- **Cross-platform comparison**: Run calibration metrics side-by-side to identify which platform's markets are best-calibrated for a given category.
- **Signal diversity**: Multiple independent probability estimates for the same underlying event reduce noise and improve inference quality.

### For ops/platform teams

- **Resilient pipeline**: If one platform's API is down, the pipeline continues ingesting from others.
- **Unified monitoring**: Scoreboard, alerts, and API endpoints work across all platforms with a single `?platform=` filter.
- **Gradual adoption**: New platforms are disabled by default in config (`enabled: false`) and can be turned on without code changes.

### For model teams

- **Richer training data**: More markets across more categories improve TSFM model generalization.
- **Platform-aware feature engineering**: The `platform` field on `MarketSnapshot` enables platform-specific feature buckets (e.g., different liquidity thresholds per platform).
- **Calibration drift detection per platform**: XAI trust score explanations now include platform provenance, enabling per-platform drift analysis.

---

## 4) What Value It Provides

### Quantitative value

| Metric | Single-platform | Multi-platform |
|---|---|---|
| Market coverage | ~1,000 active markets | ~5,000+ active markets across 3 platforms |
| Category breadth | Politics, crypto, culture | + CFTC-regulated events, economics, community-driven |
| Pipeline resilience | Single point of failure | Graceful per-platform error handling |
| Calibration signal quality | Single-source probabilities | Cross-platform ensemble opportunity |

### Architectural value

- **Extensibility**: Adding a new platform requires only a connector module and a normalizer — no changes to pipelines, schemas, or API.
- **Backward compatibility**: All existing Polymarket behavior is unchanged. The `platform` field defaults to `polymarket`. Existing tests pass without modification.
- **Clean separation of concerns**: Platform-specific logic is isolated in connector + normalizer modules. Shared behavior (retry, backoff, pagination, normalization to `MarketSnapshot`) is enforced through protocols.

---

## 5) Why This Is Reliable

### Production-proven patterns

Every new connector replicates the exact reliability patterns that the Polymarket Gamma connector has proven in production:

| Pattern | Implementation |
|---|---|
| **Exponential backoff with jitter** | Configurable `backoff_base`, `backoff_factor`, `backoff_max`, `backoff_jitter` per connector |
| **Retryable status codes** | `{408, 429, 500, 502, 503, 504}` — matching the Gamma connector exactly |
| **Rate limiting** | Optional `max_requests_per_second` with async lock-based throttling |
| **Timeout handling** | Per-request `httpx.Timeout` with `TimeoutException` catch and retry |
| **Connection ownership** | Connectors track whether they own their `httpx.AsyncClient` and only close it on `aclose()` if they created it |
| **Cursor dedup** | Pagination tracks seen cursors/IDs to prevent infinite loops on API bugs |

### Error hierarchy per platform

Each connector defines a structured exception hierarchy:

```
KalshiConnectorError (base)
├── KalshiRequestError    — request failed after all retries
├── KalshiHTTPError       — non-retryable HTTP error (with status, url, body)
└── KalshiResponseError   — unparseable or structurally invalid response

ManifoldConnectorError (base)
├── ManifoldRequestError
├── ManifoldHTTPError
└── ManifoldResponseError
```

This enables callers to catch platform-specific errors at the right granularity without losing error context.

### Graceful multi-platform orchestration

`multi_platform_ingest.py` handles per-platform failures gracefully:

- If one platform's connector creation fails, the error is logged and other platforms continue.
- If one platform's ingestion fails, the error is captured in the result dict (`{"error": "..."}`) and other platforms are unaffected.
- Connector cleanup (`aclose()`) is always called in a `finally` block, even on failure.

### Test coverage

- **12 unit tests** across `test_kalshi_connector.py` and `test_manifold_connector.py` covering:
  - Pagination behavior (cursor, before-cursor, partial-page stop)
  - Retry with exponential backoff (monkeypatched `asyncio.sleep` verification)
  - Timeout error propagation
  - snake_case normalization
  - Record deduplication
  - Event fetch behavior (Kalshi events, Manifold empty-list)
- Tests use `httpx.MockTransport` for deterministic, network-free test execution.
- All 463 existing tests continue to pass unchanged.

### Schema-level safety

- `MarketSnapshot.platform` defaults to `Platform.POLYMARKET` — all existing code that constructs snapshots without specifying a platform works identically.
- `MarketRegistry.platform` follows the same default pattern.
- Pydantic v2 `ConfigDict(extra="forbid")` ensures that platform-specific fields do not leak into the validated schema.

---

## 6) Technical Details

### 6.1 Platform enum and schema integration

```python
# schemas/enums.py
class Platform(StringEnum):
    POLYMARKET = "polymarket"
    KALSHI = "kalshi"
    MANIFOLD = "manifold"
    METACULUS = "metaculus"  # reserved for future
```

The `Platform` enum is orthogonal to the existing `DataSource` enum:
- **`DataSource`** = acquisition method (REST, GraphQL, WebSocket)
- **`Platform`** = prediction market platform (Polymarket, Kalshi, Manifold)

A single platform can have multiple data sources (Polymarket has Gamma REST + Subgraph + WebSocket). A single data source pattern (REST) is used across multiple platforms.

### 6.2 Connector protocol layer

Three `@runtime_checkable` protocols in `connectors/base.py`:

| Protocol | Methods | Required by |
|---|---|---|
| `MarketDataConnector` | `fetch_markets()`, `fetch_events()` | All platforms |
| `MetricsConnector` | `fetch_open_interest()`, `fetch_volume()`, `fetch_activity()` | Polymarket (Subgraph) only |
| `RealtimeConnector` | `stream_messages()` | Polymarket (WebSocket) only |

The factory returns `None` for capabilities a platform does not support, allowing callers to check capability at runtime:

```python
rt = create_realtime_connector(Platform.KALSHI)
if rt is not None:
    async for msg in rt.stream_messages(url):
        ...
```

### 6.3 Connector factory

`connectors/factory.py` provides three factory functions:

- `create_connector(platform, config=...)` → `MarketDataConnector`
- `create_metrics_connector(platform, config=...)` → `MetricsConnector | None`
- `create_realtime_connector(platform, config=...)` → `RealtimeConnector | None`

Lazy imports prevent circular dependency issues and keep unused platform code from being loaded.

### 6.4 Kalshi connector details

| Aspect | Detail |
|---|---|
| **Base URL** | `https://api.elections.kalshi.com/trade-api/v2` |
| **Auth** | Bearer token via `api_key_id` (set via `KALSHI_API_KEY_ID` env var) |
| **Pagination** | Cursor-based: response includes `cursor` field for next page |
| **Markets endpoint** | `GET /markets` → response: `{"markets": [...], "cursor": "..."}` |
| **Historical markets** | `GET /historical/markets` → same response shape; fetches archived/settled markets for training data augmentation. Supports `mve_filter=exclude` to skip multi-way venue events. |
| **Events endpoint** | `GET /events` → response: `{"events": [...], "cursor": "..."}` |
| **Record ID** | Primary key: `ticker` field (e.g., `AAPL-24MAR14-150`) |
| **Normalization** | Recursive camelCase → snake_case, platform-prefixed IDs (`kalshi:{ticker}`) |

**Kalshi normalizer field mapping** (`connectors/kalshi_normalizer.py`):

| Kalshi field | Canonical field | Transform |
|---|---|---|
| `ticker` | `market_id` | `"kalshi:{ticker}"` |
| `event_ticker` | `event_id` | `"kalshi:{event_ticker}"` |
| `yes_bid`, `yes_ask` | `p_yes` | Midpoint of bid/ask (cents → probability, ÷100) |
| — | `p_no` | `1.0 - p_yes` |
| `volume` | `volume_24h` | Direct mapping |
| `open_interest` | `open_interest` | Direct mapping |
| `close_time` | `tte_seconds` | `close_time - now` in seconds |
| `title` | `title` | Direct mapping |
| `category` | `category` | Direct mapping |

### 6.5 Manifold connector details

| Aspect | Detail |
|---|---|
| **Base URL** | `https://api.manifold.markets/v0` |
| **Auth** | None required (public API) |
| **Pagination** | Before-cursor: `?before={last_item_id}` to get next page |
| **Markets endpoint** | `GET /markets` → response: `[{...}, {...}, ...]` (JSON array) |
| **Events endpoint** | Returns `[]` — Manifold has no separate events concept |
| **Record ID** | `id` field (UUID-style) |
| **Dedup** | `seen_ids` set prevents duplicate records across pages |
| **Pagination stop** | When `len(response) < page_size` |

**Manifold normalizer field mapping** (`connectors/manifold_normalizer.py`):

| Manifold field | Canonical field | Transform |
|---|---|---|
| `id` | `market_id` | `"manifold:{id}"` |
| `group_slugs[0]` | `event_id` | `"manifold:{group_slug}"` (fallback: market_id) |
| `probability` | `p_yes` | Direct (binary markets) |
| — | `p_no` | `1.0 - p_yes` |
| `volume24Hours` | `volume_24h` | Direct mapping |
| `totalLiquidity` | `open_interest` | Proxy (Manifold has no traditional OI) |
| `uniqueBettorCount` | `num_traders_proxy` | Direct mapping |
| `closeTime` | `tte_seconds` | `closeTime/1000 - now` (ms → seconds) |
| `question` | `title` | Fallback to `title` |
| `outcomeType` | `outcome_type` | `BINARY`, `MULTIPLE_CHOICE`, etc. |

**Multi-outcome market handling**: For `MULTIPLE_CHOICE` markets, the normalizer flattens each answer into a separate record:
- `market_id = manifold:{id}:{answer_id}`
- `event_id = manifold:{id}` (shared parent)
- Volume and liquidity are divided equally across outcomes
- Each record independently satisfies `p_yes + p_no = 1.0`

### 6.6 Generalized ingestion pipeline

`pipelines/ingest_platform_raw.py` replaces platform-specific ingestion with a parameterized version:

```
ingest_platform_raw(connector, raw_writer, platform="kalshi", dt=...) →
  raw/kalshi/dt=2026-03-14/markets.jsonl
  raw/kalshi/dt=2026-03-14/events.jsonl
```

`pipelines/multi_platform_ingest.py` orchestrates across all enabled platforms:

1. Reads `platforms` section from config
2. Skips platforms with `enabled: false`
3. Creates connector via factory
4. Calls `ingest_platform_raw` per platform
5. Captures per-platform results or errors
6. Cleans up connectors in `finally` blocks

### 6.7 Storage layout

```
raw/
  gamma/                    # Polymarket (existing, untouched)
    dt=YYYY-MM-DD/
      markets.jsonl
      events.jsonl
  kalshi/                   # New
    dt=YYYY-MM-DD/
      markets.jsonl
      events.jsonl
  manifold/                 # New
    dt=YYYY-MM-DD/
      markets.jsonl
      events.jsonl
```

### 6.8 Configuration

```yaml
# configs/default.yaml — platforms section
platforms:
  polymarket:
    enabled: true
    connector: gamma
    base_url: "https://gamma-api.polymarket.com"
    max_retries: 3
    websocket:
      enabled: true
      url: "wss://ws-subscriptions-clob.polymarket.com/ws/market"
  kalshi:
    enabled: false          # opt-in
    connector: kalshi
    base_url: "https://api.elections.kalshi.com/trade-api/v2"
    api_key_id_env: "KALSHI_API_KEY_ID"
    api_key_secret_env: "KALSHI_API_KEY_SECRET"
    max_retries: 3
  manifold:
    enabled: false          # opt-in
    connector: manifold
    base_url: "https://api.manifold.markets/v0"
    max_retries: 3
```

### 6.9 API integration

API endpoints (`/markets`, `/scoreboard`) accept an optional `?platform=` query parameter:

- `GET /markets` → all markets across all platforms
- `GET /markets?platform=kalshi` → Kalshi markets only
- `GET /scoreboard?platform=manifold` → Manifold scoreboard

The XAI trust score explainer (`calibration/xai_integration.py`) reads platform from `market_data.get("platform", "polymarket")` for source attribution in evidence packages.

---

## 7) Files Reference

### New files (12)

| File | Purpose |
|---|---|
| `connectors/base.py` | Protocol definitions for connector capabilities |
| `connectors/normalizers.py` | `MarketNormalizer` protocol |
| `connectors/factory.py` | Platform-aware connector factory functions |
| `connectors/kalshi.py` | Kalshi async REST client |
| `connectors/kalshi_normalizer.py` | Kalshi → canonical field mapping |
| `connectors/manifold.py` | Manifold async REST client |
| `connectors/manifold_normalizer.py` | Manifold → canonical field mapping |
| `pipelines/ingest_platform_raw.py` | Generalized raw ingestion pipeline |
| `pipelines/multi_platform_ingest.py` | Multi-platform ingestion orchestrator |
| `tests/unit/test_kalshi_connector.py` | Kalshi connector unit tests (5 tests) |
| `tests/unit/test_manifold_connector.py` | Manifold connector unit tests (7 tests) |

### Modified files (9)

| File | Change |
|---|---|
| `schemas/enums.py` | Added `Platform` enum |
| `schemas/market_snapshot.py` | Added `platform` field (default: `POLYMARKET`) |
| `schemas/market_registry.py` | Added `platform` field (default: `POLYMARKET`) |
| `schemas/__init__.py` | Exported `Platform` |
| `connectors/__init__.py` | Expanded exports with protocols and factory |
| `configs/default.yaml` | Added `platforms` configuration section |
| `calibration/xai_integration.py` | Platform-aware source attribution |
| `api/app.py` | Added `?platform=` query filter |
| `storage/layout.md` | Documented multi-platform storage paths |

---

## 8) How to Enable a New Platform

### Enabling Kalshi

1. Set environment variables:
   ```bash
   export KALSHI_API_KEY_ID="your-api-key-id"
   export KALSHI_API_KEY_SECRET="your-api-key-secret"
   ```

2. Update `configs/default.yaml`:
   ```yaml
   platforms:
     kalshi:
       enabled: true
   ```

3. Run ingestion:
   ```python
   from pipelines.multi_platform_ingest import run_multi_platform_ingest_sync
   from storage.raw_writer import RawWriter

   config = yaml.safe_load(open("configs/default.yaml"))
   writer = RawWriter(root="data")
   results = run_multi_platform_ingest_sync(config=config, raw_writer=writer)
   print(results["kalshi"])
   ```

### Enabling Manifold

1. Update `configs/default.yaml`:
   ```yaml
   platforms:
     manifold:
       enabled: true
   ```
   No API keys required — Manifold's API is fully public.

2. Run ingestion — same as above, results will include `results["manifold"]`.

### Adding a new platform (developer guide)

1. Create `connectors/{platform}.py` — async client satisfying `MarketDataConnector` protocol.
2. Create `connectors/{platform}_normalizer.py` — field mapping to canonical schema.
3. Add the platform to `Platform` enum in `schemas/enums.py`.
4. Register in `connectors/factory.py` → `create_connector()`.
5. Add config block in `configs/default.yaml` under `platforms`.
6. Write tests in `tests/unit/test_{platform}_connector.py` using `httpx.MockTransport`.

No changes to pipelines, schemas, API, or storage layer are needed — the abstraction handles everything.

---

## 9) Cross-Platform Market Normalization

`features/prediction_market_normalization.py` provides deterministic normalization that standardizes data across platforms:

### Canonical category inference

Platform-specific categories are mapped to a fixed canonical set: `politics`, `crypto`, `macro`, `sports`, `science_health`, `technology`, `culture`, `business`, `weather`, `lifestyle`, `other`. Mapping uses:
1. Exact match table (e.g., `pop_culture` → `culture`, `us_current_affairs` → `politics`).
2. Token matching on title/slug/platform (e.g., title containing "inflation" → `macro`).
3. Fallback to `other`.

### Market structure classification

Detects non-standard contract types, particularly on Kalshi:
- `combo_multi_leg`: Multi-clause combos (parlay, crosscategory, SGP tickers, multiple yes/no clauses).
- `player_prop`: Sports player prop patterns.
- `standard_binary`: Default.

Non-standard structures are excluded from training by default to focus on well-behaved binary contracts.

### Integration

`augment_prediction_market_context(frame)` adds `canonical_category`, `market_structure`, `platform_category`, and `is_standard_market` in one call. Used by:
- `scripts/bootstrap_prediction_market_resolved_dataset.py` (data bootstrap)
- `scripts/generate_real_data_forecasting_pack.py` (training data generation)
- `pipelines/train_resolved_model.py` (segment routing features)

---

## 10) Kalshi Historical Markets

`KalshiConnector.fetch_historical_markets()` fetches archived/settled markets from Kalshi's `/historical/markets` endpoint with cursor pagination (same pattern as live markets).

Purpose: Increases training data volume by incorporating historical resolved markets, improving model calibration with more historical patterns.

Integration in the bootstrap script:
- Fetches historical markets with `mve_filter=exclude` (excludes multi-way venue events).
- Combines with live market records and deduplicates by ticker.
- Tracks `historical_market_count` in platform summaries.
