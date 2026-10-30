export const MEMORY_BUFFER_LIMIT = 1000;
export const MEMORY_FLUSH_SIZE = 500;
export const MEMORY_FLUSH_DELAY_MS = 500;
export const UPLOAD_BATCH_SIZE = 100;
export const UPLOAD_INTERVAL_MS = 4000;
export const PACKET_PACING_MS = 500;
export const MAX_PACKETS_PER_UPLOAD = 3;

export function shouldPersistBuffer(length) {
  return Number.isFinite(length) && length >= MEMORY_FLUSH_SIZE;
}

export function restoreUnsentBatch(pending, batch, limit = MEMORY_BUFFER_LIMIT) {
  const combined = [...batch, ...pending];
  const dropped = Math.max(0, combined.length - limit);
  return { events: combined.slice(0, limit), dropped };
}

export function groupEventsBySession(events, defaultSessionId) {
  const groups = new Map();
  for (const event of events) {
    const sessionId = event.session_id || defaultSessionId;
    const group = groups.get(sessionId) ?? [];
    group.push(event);
    groups.set(sessionId, group);
  }
  return groups;
}

export function retryDelay(attempt) {
  const exponent = Math.min(5, Math.max(0, Math.floor(Number(attempt) || 0)));
  return Math.min(30_000, 1000 * 2 ** exponent);
}
