import test from "node:test";
import assert from "node:assert/strict";
import { MEMORY_BUFFER_LIMIT, MEMORY_FLUSH_SIZE, PACKET_PACING_MS, groupEventsBySession, retryDelay, restoreUnsentBatch, shouldPersistBuffer, UPLOAD_BATCH_SIZE, UPLOAD_INTERVAL_MS } from "./session-buffer-policy.mjs";

test("in-memory telemetry persists after 500 events or 500ms and uploads in paced bounded batches", () => {
  assert.equal(MEMORY_FLUSH_SIZE, 500);
  assert.equal(shouldPersistBuffer(499), false);
  assert.equal(shouldPersistBuffer(500), true);
  assert.equal(UPLOAD_INTERVAL_MS, 4000);
  assert.equal(UPLOAD_BATCH_SIZE, 100);
  assert.equal(PACKET_PACING_MS, 500);
});

test("failed storage writes restore unsent events and respect the memory bound", () => {
  const restored = restoreUnsentBatch(["new-1", "new-2"], ["old-1", "old-2"], 3);
  assert.deepEqual(restored, { events: ["old-1", "old-2", "new-1"], dropped: 1 });
  assert.equal(MEMORY_BUFFER_LIMIT, 1000);
});

test("upload retry delay grows exponentially and caps at 30 seconds", () => {
  assert.deepEqual([0, 1, 2, 3, 4, 5, 6].map(retryDelay), [1000, 2000, 4000, 8000, 16000, 30000, 30000]);
});

test("events queued before session recovery remain scoped to their original session", () => {
  const oldEvent = { id: "old", session_id: "expired-session", occurred_at: "2026-10-30T10:00:00Z" };
  const newEvent = { id: "new", session_id: "active-session", occurred_at: "2026-10-30T10:01:00Z" };
  const groups = groupEventsBySession([oldEvent, newEvent, { id: "unstamped" }], "active-session");
  assert.deepEqual(groups.get("expired-session"), [oldEvent]);
  assert.deepEqual(groups.get("active-session"), [newEvent, { id: "unstamped" }]);
});
