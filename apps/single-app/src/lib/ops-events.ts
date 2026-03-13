export type OpsEventName =
  | 'execution_start_blocked'
  | 'worker_failed'
  | 'retry_exhausted'
  | 'kill_switch_on'
  | 'kill_switch_off'
  | 'execution_order_created'
  | 'order_status_transition_blocked'
  | 'order_status_transition_error';

export type OpsEventSeverity = 'info' | 'warning' | 'critical';

export interface OpsEventPayload {
  event: OpsEventName;
  severity: OpsEventSeverity;
  runId?: string;
  jobId?: string;
  reason?: string;
  details?: Record<string, unknown>;
}

interface OpsEventEnvelope extends OpsEventPayload {
  source: 'single-app';
  at: string;
}

function buildEnvelope(payload: OpsEventPayload): OpsEventEnvelope {
  return {
    source: 'single-app',
    at: new Date().toISOString(),
    ...payload,
  };
}

function logEvent(envelope: OpsEventEnvelope) {
  const line = JSON.stringify(envelope);
  if (envelope.severity === 'critical') {
    console.error(`[ops-event] ${line}`);
    return;
  }
  if (envelope.severity === 'warning') {
    console.warn(`[ops-event] ${line}`);
    return;
  }
  console.log(`[ops-event] ${line}`);
}

async function sendWebhook(envelope: OpsEventEnvelope) {
  const url = process.env.ALERT_WEBHOOK_URL?.trim();
  if (!url || envelope.severity !== 'critical') {
    return;
  }

  const body = {
    text: `[${envelope.event}] runId=${envelope.runId ?? '-'} jobId=${envelope.jobId ?? '-'} reason=${envelope.reason ?? '-'} at=${envelope.at}`,
    event: envelope,
  };

  const response = await fetch(url, {
    method: 'POST',
    headers: {
      'content-type': 'application/json',
    },
    body: JSON.stringify(body),
  });

  if (!response.ok) {
    throw new Error(`webhook returned ${response.status}`);
  }
}

export async function emitOpsEvent(payload: OpsEventPayload) {
  const envelope = buildEnvelope(payload);
  logEvent(envelope);

  try {
    await sendWebhook(envelope);
  } catch (error) {
    const reason = error instanceof Error ? error.message : String(error);
    console.error(`[ops-event] webhook delivery failed event=${envelope.event} reason=${reason}`);
  }
}
