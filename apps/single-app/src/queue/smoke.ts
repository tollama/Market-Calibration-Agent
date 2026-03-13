import 'dotenv/config';
import { randomUUID } from 'node:crypto';
import { enqueueExecutionStart } from './producer';

async function main() {
  const mode = (process.argv[2] ?? 'mock') as 'paper' | 'live' | 'mock';
  const enqueued = await enqueueExecutionStart({
    runId: randomUUID(),
    mode,
    requestedAt: new Date().toISOString(),
    dryRun: true,
    maxPosition: 1_000_000,
  });
  console.log(
    `[smoke] enqueued queue=${enqueued.queueName} jobId=${enqueued.jobId} runId=${enqueued.runId} mode=${mode}`
  );
}

main().catch((error) => {
  console.error('[smoke] failed:', error);
  process.exit(1);
});
