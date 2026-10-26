import test from "node:test";
import assert from "node:assert/strict";
import { ACTIVE_SESSION_KEY, TAB_ID_KEY, activeTabLeaseCount, claimTabId, generateSecureId, getOrCreateSessionRecord, releaseTabLease, sessionIdleTimeout } from "./session-identity.mjs";

class MemoryStorage {
  values = new Map();
  getItem(key) { return this.values.get(key) ?? null; }
  setItem(key, value) { this.values.set(key, String(value)); }
  removeItem(key) { this.values.delete(key); }
  get length() { return this.values.size; }
  key(index) { return [...this.values.keys()][index] ?? null; }
}

test("session ID survives refresh and starts a new session after idle expiry", () => {
  const shared = new MemoryStorage();
  const first = getOrCreateSessionRecord(shared, { now: 1000, idleTimeout: 500, idFactory: () => "session-1" });
  const refresh = getOrCreateSessionRecord(shared, { now: 1200, idleTimeout: 500, idFactory: () => "session-2" });
  const expired = getOrCreateSessionRecord(shared, { now: 1800, idleTimeout: 500, idFactory: () => "session-3" });
  assert.equal(first.record.id, refresh.record.id);
  assert.equal(expired.expiredSessionId, "session-1");
  assert.equal(expired.record.id, "session-3");
  assert.ok(shared.getItem(ACTIVE_SESSION_KEY));
});

test("tab ID survives same-tab reload but copied tab storage gets a distinct ID", () => {
  const shared = new MemoryStorage();
  const firstStorage = new MemoryStorage();
  const first = claimTabId(firstStorage, shared, { now: 1000, owner: "owner-a", idFactory: () => "tab-a" });
  const refreshed = claimTabId(firstStorage, shared, { now: 1100, owner: "owner-a", idFactory: () => "tab-b" });
  assert.equal(refreshed.tabId, first.tabId);
  const duplicateStorage = new MemoryStorage();
  duplicateStorage.setItem(TAB_ID_KEY, first.tabId);
  const duplicate = claimTabId(duplicateStorage, shared, { now: 1200, owner: "owner-b", idFactory: () => "tab-b" });
  assert.equal(duplicate.tabId, "tab-b");
  assert.equal(activeTabLeaseCount(shared, 1200), 2);
  releaseTabLease(shared, first);
  assert.equal(activeTabLeaseCount(shared, 1200), 1);
});

test("session timeout is bounded and IDs use secure randomness only", () => {
  assert.equal(sessionIdleTimeout(1), 60_000);
  assert.equal(sessionIdleTimeout(999_999_999), 86_400_000);
  const cryptoApi = { getRandomValues: (bytes) => { bytes.fill(1); return bytes; } };
  assert.match(generateSecureId(cryptoApi), /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i);
});
