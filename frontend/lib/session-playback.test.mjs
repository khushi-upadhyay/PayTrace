import test from "node:test";
import assert from "node:assert/strict";
import { createReplayConfig, normalizeOccurrenceTime, PLAYBACK_SPEEDS, seekPreservingPlayback } from "./session-playback.mjs";

test("seek preserves whether playback was active", () => {
  const calls = [];
  const player = { play: (value) => calls.push(["play", value]), pause: (value) => calls.push(["pause", value]) };
  assert.equal(seekPreservingPlayback(player, 3200, true), true);
  assert.equal(seekPreservingPlayback(player, 800, false), true);
  assert.deepEqual(calls, [["play", 3200], ["pause", 800]]);
  assert.equal(seekPreservingPlayback(player, Number.NaN, true), false);
});

test("playback options use supported speeds and bounded inactivity threshold", () => {
  assert.deepEqual(PLAYBACK_SPEEDS, [0.5, 1, 1.5, 2, 4]);
  assert.deepEqual(createReplayConfig({ speed: 4, skipInactive: false, inactiveThreshold: 100 }), { speed: 4, skipInactive: false, inactivePeriodThreshold: 1000 });
  assert.equal(createReplayConfig({ speed: 3 }).speed, 1);
});

test("occurrence timestamps parse in UTC and missing timestamps stay unknown", () => {
  assert.equal(normalizeOccurrenceTime("2026-10-26T10:00:00.000Z"), Date.UTC(2026, 9, 26, 10));
  assert.equal(normalizeOccurrenceTime(undefined), null);
  assert.equal(normalizeOccurrenceTime("invalid"), null);
});
