export type ExecutionMode = 'paper' | 'live' | 'mock';

export interface ExecutionJobPayload {
  runId: string;
  mode: ExecutionMode;
  requestedAt: string;
  dryRun: boolean;
  maxPosition: number;
  notes?: string;
}

export interface ExecutionStartRequest {
  mode?: ExecutionMode;
  dryRun?: boolean;
  maxPosition?: number;
  notes?: string;
}
