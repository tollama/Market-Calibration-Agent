import { Queue, JobsOptions } from 'bullmq';
import { getRedisConnection } from './config';
import type { ExecutionJobPayload } from './types';

export const EXECUTION_QUEUE_NAME = 'execution_start';

export const executionJobDefaults: JobsOptions = {
  attempts: 3,
  backoff: {
    type: 'exponential',
    delay: 1000
  },
  removeOnComplete: 100,
  removeOnFail: 100
};

export function createExecutionQueue() {
  return new Queue<ExecutionJobPayload>(EXECUTION_QUEUE_NAME, {
    connection: getRedisConnection(),
    defaultJobOptions: executionJobDefaults
  });
}
