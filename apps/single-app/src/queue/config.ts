export function getRedisConnection() {
  const redisUrl = process.env.REDIS_URL;

  if (!redisUrl) {
    throw new Error('REDIS_URL is required to use queue/worker');
  }

  return {
    url: redisUrl
  };
}
