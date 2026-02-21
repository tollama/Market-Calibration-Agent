#!/usr/bin/env python3.11
from __future__ import annotations

import argparse
import hashlib
import json
import re
import time
from pathlib import Path
from typing import Any

import httpx

GAMMA_BASE = "https://gamma-api.polymarket.com"
CLOB_BASE = "https://clob.polymarket.com"
_HEX2_RE = re.compile(r"[0-9a-f]{2}$", re.IGNORECASE)
_WS_RE = re.compile(r"\s+")
_NON_ALNUM_RE = re.compile(r"[^a-z0-9\s]+")


def _request_json(client: httpx.Client, url: str, *, params: dict[str, Any], retries: int = 3) -> Any:
    last_error: Exception | None = None
    for attempt in range(retries + 1):
        try:
            res = client.get(url, params=params)
            if res.status_code in {408, 429, 500, 502, 503, 504} and attempt < retries:
                time.sleep(min(2**attempt, 4))
                continue
            res.raise_for_status()
            return res.json()
        except Exception as exc:  # noqa: BLE001 - concise script for demo-data prep
            last_error = exc
            if attempt < retries:
                time.sleep(min(2**attempt, 4))
                continue
            raise
    raise RuntimeError("request failed") from last_error


def _parse_json_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, list) else []
        except json.JSONDecodeError:
            return []
    return []


def _to_float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _pick_rank_signal(market: dict[str, Any]) -> float:
    v24 = _to_float(market.get("volume24hr"))
    if v24 > 0:
        return v24
    vol = _to_float(market.get("volume"))
    if vol > 0:
        return vol
    return _to_float(market.get("liquidity"))


def _normalize_prefix(text: str, *, token_limit: int = 12) -> str:
    lowered = text.lower().strip()
    lowered = _NON_ALNUM_RE.sub(" ", lowered)
    lowered = _WS_RE.sub(" ", lowered).strip()
    if not lowered:
        return ""
    return " ".join(lowered.split(" ")[:token_limit])


def _stable_group_key(market: dict[str, Any], title: str) -> str:
    qid_raw = market.get("questionID") or market.get("questionId") or market.get("question_id")
    if qid_raw not in (None, ""):
        qid = str(qid_raw).strip().lower()
        if len(qid) > 2 and _HEX2_RE.search(qid):
            qid = qid[:-2]
        if qid:
            return f"qid:{qid}"

    prefix = _normalize_prefix(str(market.get("question") or market.get("title") or title))
    if prefix:
        return f"txt:{prefix}"

    # last-resort stable fallback to avoid dropping all orphaned records
    return "fallback:" + hashlib.sha1(str(market.get("id", "")).encode("utf-8")).hexdigest()[:12]


def _pick_yes_token(market: dict[str, Any]) -> str | None:
    outcomes = _parse_json_list(market.get("outcomes"))
    token_ids = _parse_json_list(market.get("clobTokenIds"))
    if not token_ids:
        return None
    yes_idx = next((i for i, o in enumerate(outcomes) if str(o).strip().lower() == "yes"), 0)
    if yes_idx >= len(token_ids):
        yes_idx = 0
    token = token_ids[yes_idx]
    return str(token) if token not in (None, "") else None


def _fetch_markets(client: httpx.Client, max_fetch: int) -> list[dict[str, Any]]:
    payload = _request_json(
        client,
        f"{GAMMA_BASE}/markets",
        params={"limit": max(20, max_fetch), "active": True, "closed": False},
    )
    if not isinstance(payload, list):
        return []
    return [m for m in payload if isinstance(m, dict)]


def _fetch_series(client: httpx.Client, token_id: str, points: int) -> list[float]:
    payload = _request_json(
        client,
        f"{CLOB_BASE}/prices-history",
        params={"market": token_id, "interval": "max", "fidelity": 60},
    )
    history = payload.get("history", []) if isinstance(payload, dict) else []
    prices: list[float] = []
    for row in history:
        if not isinstance(row, dict):
            continue
        try:
            p = float(row.get("p"))
        except (TypeError, ValueError):
            continue
        if 0.0 <= p <= 1.0:
            prices.append(round(p, 6))
    return prices[-points:]


def build_sample(*, market_count: int, points: int, independent_only: bool = True, max_fetch: int = 200) -> dict[str, Any]:
    items: list[dict[str, Any]] = []
    seen_groups: set[str] = set()

    with httpx.Client(timeout=20.0, headers={"Accept": "application/json"}) as client:
        markets = _fetch_markets(client, max_fetch=max(max_fetch, market_count))
        markets.sort(key=_pick_rank_signal, reverse=True)

        for market in markets:
            if len(items) >= market_count:
                break
            market_id = str(market.get("id") or "").strip()
            title = str(market.get("question") or market.get("title") or "").strip()
            if not market_id or not title:
                continue

            group_key = _stable_group_key(market, title)
            if independent_only and group_key in seen_groups:
                continue

            token_id = _pick_yes_token(market)
            if not token_id:
                continue
            try:
                y = _fetch_series(client, token_id, points)
            except Exception:
                continue
            if len(y) < min(10, points):
                continue

            items.append(
                {
                    "market_id": market_id,
                    "title": title,
                    "question": title,
                    "y": y,
                    "as_of_ts": int(time.time()),
                }
            )
            seen_groups.add(group_key)

    return {
        "generated_at": int(time.time()),
        "source": {"gamma": GAMMA_BASE, "clob": CLOB_BASE},
        "items": items,
    }


def _write_md(payload: dict[str, Any], path: Path) -> None:
    lines = [
        "# Live Demo Sample Data",
        "",
        f"- generated_at: `{payload.get('generated_at')}`",
        f"- item_count: `{len(payload.get('items', []))}`",
        "",
    ]
    for idx, item in enumerate(payload.get("items", []), start=1):
        y = item.get("y", [])
        preview = ", ".join(str(v) for v in y[:5])
        lines.extend(
            [
                f"## {idx}. {item.get('title', '')}",
                f"- market_id: `{item.get('market_id', '')}`",
                f"- as_of_ts: `{item.get('as_of_ts', '')}`",
                f"- y_len: `{len(y)}`",
                f"- y_preview: `{preview}`",
                "",
            ]
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Prepare live Polymarket sample y-series for TSFM demo.")
    parser.add_argument("--market-count", type=int, default=4, help="Number of markets to include.")
    parser.add_argument("--points", type=int, default=64, help="Recent y points per market.")
    parser.add_argument(
        "--independent-only",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Keep at most one market per correlated question/bucket family (default: true).",
    )
    parser.add_argument(
        "--max-fetch",
        type=int,
        default=200,
        help="Max active markets to fetch before ranking/dedup (default: 200).",
    )
    parser.add_argument(
        "--json-out",
        default="artifacts/demo/live_demo_sample_data.json",
        help="Output JSON path.",
    )
    parser.add_argument(
        "--md-out",
        default="artifacts/demo/live_demo_sample_data.md",
        help="Output Markdown path.",
    )
    args = parser.parse_args()

    payload = build_sample(
        market_count=max(1, args.market_count),
        points=max(10, args.points),
        independent_only=bool(args.independent_only),
        max_fetch=max(20, args.max_fetch),
    )

    json_path = Path(args.json_out)
    json_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    _write_md(payload, Path(args.md_out))

    print(f"wrote {json_path} and {args.md_out} (items={len(payload.get('items', []))})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
