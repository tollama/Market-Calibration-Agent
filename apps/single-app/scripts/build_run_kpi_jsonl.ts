#!/usr/bin/env -S node --loader tsx
import { mkdirSync, readFileSync, writeFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';

type UnmatchedPolicy = 'skip' | 'warn' | 'error';

type RunKpiRow = {
  run_id: string;
  ended_at: string;
  brier: number;
  ece: number;
  realized_slippage_bps: number;
  execution_fail_rate: number;
};

type ExecutionRow = {
  run_id: string;
  ended_at: string;
  realized_slippage_bps: number;
  execution_fail_rate: number;
};

type MetricsRunRow = {
  run_id: string;
  ended_at?: string;
  brier: number;
  ece: number;
};

type ScoreboardRow = {
  as_of: string;
  brier: number;
  ece: number;
};

function parseArgs(argv: string[]) {
  const out: Record<string, string | boolean> = {
    'on-unmatched': 'warn',
    'time-tolerance-seconds': '300',
  };

  for (let i = 0; i < argv.length; i += 1) {
    const token = argv[i];
    if (!token.startsWith('--')) {
      throw new Error(`unexpected positional argument: ${token}`);
    }
    const key = token.slice(2);
    if (key === 'help') {
      out.help = true;
      continue;
    }
    const next = argv[i + 1];
    if (!next || next.startsWith('--')) {
      out[key] = true;
      continue;
    }
    out[key] = next;
    i += 1;
  }

  return out;
}

function usage() {
  console.log(`사용법:
  npx tsx scripts/build_run_kpi_jsonl.ts \
    --execution-source <path> \
    [--metrics-source <path>] \
    --output <path> \
    [--on-unmatched skip|warn|error] \
    [--time-tolerance-seconds 300]

설명:
  - execution source에서 run_id/ended_at/slippage/fail-rate를 읽고,
    metrics source(run-level 또는 scoreboard)에서 brier/ece를 결합해
    run-level KPI JSONL을 생성합니다.
  - run_id 매칭 우선, 실패 시 ended_at 근접 매칭(기본 300초)을 시도합니다.
`);
}

function toObjArray(payload: unknown): Record<string, unknown>[] {
  if (Array.isArray(payload)) {
    return payload.filter((item): item is Record<string, unknown> => !!item && typeof item === 'object');
  }
  if (payload && typeof payload === 'object') {
    const asObj = payload as Record<string, unknown>;
    const candidates = [asObj.runs, asObj.items, asObj.data, asObj.records];
    for (const c of candidates) {
      if (Array.isArray(c)) {
        return c.filter((item): item is Record<string, unknown> => !!item && typeof item === 'object');
      }
    }
  }
  return [];
}

function readAnyRows(path: string): Record<string, unknown>[] {
  const raw = readFileSync(path, 'utf-8').trim();
  if (!raw) return [];
  if (path.endsWith('.jsonl')) {
    return raw
      .split('\n')
      .map((line) => line.trim())
      .filter(Boolean)
      .map((line) => JSON.parse(line) as Record<string, unknown>);
  }
  return toObjArray(JSON.parse(raw));
}

function num(row: Record<string, unknown>, keys: string[]): number | null {
  for (const key of keys) {
    const v = row[key];
    if (v === undefined || v === null) continue;
    const parsed = Number(v);
    if (Number.isFinite(parsed)) return parsed;
  }
  return null;
}

function str(row: Record<string, unknown>, keys: string[]): string | null {
  for (const key of keys) {
    const v = row[key];
    if (typeof v === 'string' && v.trim()) return v.trim();
  }
  return null;
}

function normalizeRunId(v: string): string {
  return v.trim().toLowerCase();
}

function parseTs(v: string): number | null {
  const ms = Date.parse(v);
  return Number.isFinite(ms) ? ms : null;
}

function parseExecutionRows(inputRows: Record<string, unknown>[]): ExecutionRow[] {
  const out: ExecutionRow[] = [];
  for (const row of inputRows) {
    const runId = str(row, ['run_id', 'runId', 'id']);
    const endedAt = str(row, ['ended_at', 'endedAt', 'ts', 'timestamp', 'finished_at', 'finishedAt']);
    const slippage = num(row, ['realized_slippage_bps', 'slippage_bps', 'realized_slippage']);
    const failRate = num(row, ['execution_fail_rate', 'exec_fail_rate', 'failure_rate']);
    if (!runId || !endedAt || slippage === null || failRate === null) continue;
    out.push({
      run_id: runId,
      ended_at: endedAt,
      realized_slippage_bps: slippage,
      execution_fail_rate: failRate,
    });
  }
  return out;
}

function parseMetricsRows(
  inputRows: Record<string, unknown>[]
): { runLevel: MetricsRunRow[]; scoreboard: ScoreboardRow[] } {
  const runLevel: MetricsRunRow[] = [];
  const scoreboard: ScoreboardRow[] = [];

  for (const row of inputRows) {
    const brier = num(row, ['brier']);
    const ece = num(row, ['ece']);
    if (brier === null || ece === null) continue;

    const runId = str(row, ['run_id', 'runId', 'id']);
    const endedAt = str(row, ['ended_at', 'endedAt', 'ts', 'timestamp', 'finished_at', 'finishedAt']);
    const asOf = str(row, ['as_of', 'asOf', 'ts', 'timestamp']);

    if (runId) {
      runLevel.push({ run_id: runId, ended_at: endedAt ?? undefined, brier, ece });
      continue;
    }

    if (asOf) {
      scoreboard.push({ as_of: asOf, brier, ece });
    }
  }

  scoreboard.sort((a, b) => (parseTs(a.as_of) ?? 0) - (parseTs(b.as_of) ?? 0));
  return { runLevel, scoreboard };
}

function main() {
  const args = parseArgs(process.argv.slice(2));
  if (args.help) {
    usage();
    return;
  }

  const executionSource = args['execution-source'];
  const metricsSource = args['metrics-source'];
  const output = args.output;
  const onUnmatched = String(args['on-unmatched'] ?? 'warn') as UnmatchedPolicy;
  const toleranceSec = Number(args['time-tolerance-seconds'] ?? '300');

  if (!executionSource || typeof executionSource !== 'string') {
    throw new Error('--execution-source is required');
  }
  if (!output || typeof output !== 'string') {
    throw new Error('--output is required');
  }
  if (!['skip', 'warn', 'error'].includes(onUnmatched)) {
    throw new Error('--on-unmatched must be one of skip|warn|error');
  }

  const executionRows = parseExecutionRows(readAnyRows(resolve(executionSource)));
  if (executionRows.length === 0) {
    throw new Error(`no valid execution rows in ${executionSource}`);
  }

  let metricsRunRows: MetricsRunRow[] = [];
  let scoreboardRows: ScoreboardRow[] = [];
  if (metricsSource && typeof metricsSource === 'string') {
    const parsed = parseMetricsRows(readAnyRows(resolve(metricsSource)));
    metricsRunRows = parsed.runLevel;
    scoreboardRows = parsed.scoreboard;
  }

  const byRunId = new Map<string, MetricsRunRow[]>();
  for (const m of metricsRunRows) {
    const key = normalizeRunId(m.run_id);
    const list = byRunId.get(key) ?? [];
    list.push(m);
    byRunId.set(key, list);
  }

  const rows: RunKpiRow[] = [];
  const warnings: string[] = [];

  for (const ex of executionRows) {
    const exTs = parseTs(ex.ended_at);
    const candidates = byRunId.get(normalizeRunId(ex.run_id)) ?? [];

    let matched: MetricsRunRow | null = null;
    let matchPolicy = '';

    if (candidates.length > 0) {
      matched = candidates[0] ?? null;
      matchPolicy = 'run_id_exact';
      if (exTs !== null && candidates.length > 1) {
        matched = [...candidates]
          .filter((c) => c.ended_at)
          .sort((a, b) => {
            const da = Math.abs((parseTs(a.ended_at ?? '') ?? 0) - exTs);
            const db = Math.abs((parseTs(b.ended_at ?? '') ?? 0) - exTs);
            return da - db;
          })[0] ?? matched;
      }
    }

    if (!matched && exTs !== null && metricsRunRows.length > 0) {
      const nearest = [...metricsRunRows]
        .filter((m) => m.ended_at)
        .map((m) => ({ m, gap: Math.abs((parseTs(m.ended_at ?? '') ?? 0) - exTs) }))
        .sort((a, b) => a.gap - b.gap)[0];
      if (nearest && nearest.gap <= toleranceSec * 1000) {
        matched = nearest.m;
        matchPolicy = `ended_at_nearest<=${toleranceSec}s`;
      }
    }

    if (!matched && exTs !== null && scoreboardRows.length > 0) {
      const prev = [...scoreboardRows]
        .map((s) => ({ s, ts: parseTs(s.as_of) }))
        .filter((v): v is { s: ScoreboardRow; ts: number } => v.ts !== null)
        .filter((v) => v.ts <= exTs)
        .sort((a, b) => b.ts - a.ts)[0];
      if (prev) {
        matched = { run_id: ex.run_id, ended_at: ex.ended_at, brier: prev.s.brier, ece: prev.s.ece };
        matchPolicy = 'scoreboard_latest_as_of<=ended_at';
      }
    }

    if (!matched) {
      const msg = `[unmatched] run_id=${ex.run_id} ended_at=${ex.ended_at} -> metrics 매칭 실패`;
      if (onUnmatched === 'error') throw new Error(msg);
      if (onUnmatched === 'warn') warnings.push(msg);
      continue;
    }

    rows.push({
      run_id: ex.run_id,
      ended_at: ex.ended_at,
      brier: matched.brier,
      ece: matched.ece,
      realized_slippage_bps: ex.realized_slippage_bps,
      execution_fail_rate: ex.execution_fail_rate,
    });

    if (process.env.DEBUG_KPI_BUILD === '1') {
      console.log(`[match] run_id=${ex.run_id} policy=${matchPolicy}`);
    }
  }

  rows.sort((a, b) => (parseTs(a.ended_at) ?? 0) - (parseTs(b.ended_at) ?? 0));

  mkdirSync(dirname(resolve(output)), { recursive: true });
  const text = rows.map((row) => JSON.stringify(row)).join('\n');
  writeFileSync(resolve(output), text.length ? `${text}\n` : '', 'utf-8');

  console.log(`[done] wrote ${rows.length} rows -> ${output}`);
  console.log(
    `[stats] execution_rows=${executionRows.length} metrics_run_rows=${metricsRunRows.length} scoreboard_rows=${scoreboardRows.length}`
  );
  if (warnings.length > 0) {
    for (const w of warnings) console.warn(w);
    console.warn(`[warn] unmatched=${warnings.length} policy=${onUnmatched}`);
  }
}

main();
