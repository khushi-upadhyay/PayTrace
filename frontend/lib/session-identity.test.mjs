import test from "node:test";
import assert from "node:assert/strict";
import { ACTIVE_SESSION_KEY, TAB_ID_KEY, activeTabLeaseCount, claimTabId, createWithExpiredSessionRecovery, generateSecureId, getOrCreateSessionRecord, isSessionExpiredDetail, releaseTabLease, replaceExpiredSessionRecord, sessionIdleTimeout } from "./session-identity.mjs";

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

test("tabs share the active session and an expired server identity is rotated once", () => {
  const shared = new MemoryStorage();
  const firstTab = getOrCreateSessionRecord(shared, { now: 1000, idFactory: () => "session-1" });
  const secondTab = getOrCreateSessionRecord(shared, { now: 1100, idFactory: () => "session-2" });
  assert.equal(firstTab.record.id, secondTab.record.id);
  const replacement = replaceExpiredSessionRecord(shared, "session-1", { now: 1200, idFactory: () => "session-3" });
  assert.equal(replacement.id, "session-3");
  assert.equal(getOrCreateSessionRecord(shared, { now: 1300, idFactory: () => "session-4" }).record.id, "session-3");
});

test("server expiry during recovery rotates again once and succeeds", async () => {
  const attempted = [];
  const result = await createWithExpiredSessionRecovery({
    expiredSessionId: "session-old",
    rotateSession: async (staleId) => ({ id: `${staleId}-new` }),
    createSession: async ({ id }) => {
      attempted.push(id);
      if (id === "session-old-new") throw { code: "session_expired" };
      return { id };
    },
    isExpired: (error) => error?.code === "session_expired",
  });
  assert.deepEqual(attempted, ["session-old-new", "session-old-new-new"]);
  assert.equal(result.session.id, "session-old-new-new");
});

test("server expiry recovery is bounded", async () => {
  let attempts = 0;
  await assert.rejects(createWithExpiredSessionRecovery({
    expiredSessionId: "session-old",
    rotateSession: async (staleId) => ({ id: `${staleId}-new` }),
    createSession: async () => { attempts += 1; throw { code: "session_expired" }; },
    isExpired: (error) => error?.code === "session_expired",
    maxAttempts: 2,
  }), (error) => error?.code === "session_expired");
  assert.equal(attempts, 2);
});

test("detects FastAPI's nested session_expired response detail", () => {
  const response = { detail: { code: "session_expired", message: "Session expired; start a new session" } };
  assert.equal(isSessionExpiredDetail(response), true);
  assert.equal(isSessionExpiredDetail(response.detail), true);
  assert.equal(isSessionExpiredDetail({ detail: { code: "validation_error" } }), false);
});

test("replaces the exact expired ID from a FastAPI 409 before retrying session creation", async () => {
  const storage = new MemoryStorage();
  storage.setItem(ACTIVE_SESSION_KEY, JSON.stringify({ id: "d3070ac2-44ca-46fd-9060-c27db291ccd9", created_at: 1, last_activity_at: 2 }));
  const postedIds = [];
  const result = await createWithExpiredSessionRecovery({
    expiredSessionId: "d3070ac2-44ca-46fd-9060-c27db291ccd9",
    rotateSession: (staleId) => replaceExpiredSessionRecord(storage, staleId, { now: 3, idFactory: () => "fresh-session-id" }),
    createSession: async ({ id }) => { postedIds.push(id); return { id }; },
    isExpired: isSessionExpiredDetail,
  });
  assert.deepEqual(postedIds, ["fresh-session-id"]);
  assert.equal(result.session.id, "fresh-session-id");
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
