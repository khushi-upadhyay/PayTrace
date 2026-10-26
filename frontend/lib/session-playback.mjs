export const PLAYBACK_SPEEDS = Object.freeze([0.5, 1, 1.5, 2, 4]);

export function seekPreservingPlayback(player, offset, wasPlaying) {
  if (!player || !Number.isFinite(offset) || offset < 0) return false;
  if (wasPlaying) player.play(offset);
  else player.pause(offset);
  return true;
}

export function createReplayConfig({ speed = 1, skipInactive = true, inactiveThreshold = 5000 } = {}) {
  return {
    speed: PLAYBACK_SPEEDS.includes(speed) ? speed : 1,
    skipInactive: Boolean(skipInactive),
    inactivePeriodThreshold: Math.max(1000, Math.min(60_000, Number(inactiveThreshold) || 5000)),
  };
}

export function normalizeOccurrenceTime(value) {
  if (typeof value !== "string") return null;
  const timestamp = Date.parse(value);
  return Number.isFinite(timestamp) ? timestamp : null;
}
