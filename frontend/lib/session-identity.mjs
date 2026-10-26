export const ACTIVE_SESSION_KEY = "paytrace_active_session_v2";
export const TAB_ID_KEY = "paytrace_browser_tab_id_v2";
const TAB_LEASE_PREFIX = "paytrace_tab_lease_v2:";
const LOCK_KEY = "paytrace_session_identity_lock_v2";

export function generateSecureId(cryptoApi = globalThis.crypto) {
  if (cryptoApi?.randomUUID) return cryptoApi.randomUUID();
  if (!cryptoApi?.getRandomValues) throw new Error("Secure browser randomness is unavailable.");
  const bytes = cryptoApi.getRandomValues(new Uint8Array(16));
  bytes[6] = (bytes[6] & 0x0f) | 0x40;
  bytes[8] = (bytes[8] & 0x3f) | 0x80;
  return [...bytes].map((byte, index) => `${[4, 6, 8, 10].includes(index) ? "-" : ""}${byte.toString(16).padStart(2, "0")}`).join("");
}

export function sessionIdleTimeout(configured) {
  const value = Number(configured);
  return Number.isFinite(value) ? Math.min(86_400_000, Math.max(60_000, value)) : 1_800_000;
}

function parseRecord(raw) {
  if (!raw) return null;
  try {
    const value = JSON.parse(raw);
    if (typeof value.id === "string" && Number.isFinite(value.created_at) && Number.isFinite(value.last_activity_at)) return value;
  } catch { /* Ignore malformed or stale browser storage. */ }
  return null;
}

export function getOrCreateSessionRecord(storage, { now = Date.now(), idleTimeout = 1_800_000, idFactory = generateSecureId } = {}) {
  const previous = parseRecord(storage.getItem(ACTIVE_SESSION_KEY));
  const expiredSessionId = previous && now - previous.last_activity_at >= idleTimeout ? previous.id : null;
  const record = previous && !expiredSessionId
    ? { ...previous, last_activity_at: now }
    : { id: idFactory(), created_at: now, last_activity_at: now };
  storage.setItem(ACTIVE_SESSION_KEY, JSON.stringify(record));
  return { record, expiredSessionId };
}

export function touchSessionRecord(storage, sessionId, now = Date.now()) {
  const record = parseRecord(storage.getItem(ACTIVE_SESSION_KEY));
  if (!record || record.id !== sessionId) return false;
  storage.setItem(ACTIVE_SESSION_KEY, JSON.stringify({ ...record, last_activity_at: now }));
  return true;
}

export function claimTabId(tabStorage, sharedStorage, { now = Date.now(), owner = generateSecureId(), idFactory = generateSecureId, leaseMs = 30_000 } = {}) {
  let tabId = tabStorage.getItem(TAB_ID_KEY);
  if (tabId) {
    const rawLease = sharedStorage.getItem(`${TAB_LEASE_PREFIX}${tabId}`);
    if (rawLease) {
      try {
        const lease = JSON.parse(rawLease);
        if (lease.expires_at > now && lease.owner !== owner) tabId = null;
      } catch { tabId = null; }
    }
  }
  if (!tabId) tabId = idFactory();
  tabStorage.setItem(TAB_ID_KEY, tabId);
  sharedStorage.setItem(`${TAB_LEASE_PREFIX}${tabId}`, JSON.stringify({ owner, expires_at: now + leaseMs }));
  return { tabId, owner, leaseMs };
}

export function renewTabLease(sharedStorage, claim, now = Date.now()) {
  const key = `${TAB_LEASE_PREFIX}${claim.tabId}`;
  try {
    const lease = JSON.parse(sharedStorage.getItem(key) || "null");
    if (lease?.owner !== claim.owner) return false;
    sharedStorage.setItem(key, JSON.stringify({ owner: claim.owner, expires_at: now + claim.leaseMs }));
    return true;
  } catch { return false; }
}

export function releaseTabLease(sharedStorage, claim) {
  const key = `${TAB_LEASE_PREFIX}${claim.tabId}`;
  try {
    const lease = JSON.parse(sharedStorage.getItem(key) || "null");
    if (lease?.owner === claim.owner) sharedStorage.removeItem(key);
  } catch { /* Expiring the lease is the safe fallback. */ }
}

export function activeTabLeaseCount(sharedStorage, now = Date.now()) {
  let count = 0;
  try {
    const keys = Array.from({ length: sharedStorage.length }, (_, index) => sharedStorage.key(index)).filter((key) => key?.startsWith(TAB_LEASE_PREFIX));
    for (const key of keys) {
      try { if (JSON.parse(sharedStorage.getItem(key) || "null")?.expires_at > now) count += 1; } catch { /* Ignore a corrupt lease. */ }
    }
  } catch { return 0; }
  return count;
}

export async function withSessionIdentityLock(work, { lockManager = globalThis.navigator?.locks, storage = globalThis.localStorage, sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms)) } = {}) {
  if (lockManager?.request) return lockManager.request("paytrace-session-identity", { mode: "exclusive" }, work);
  const owner = generateSecureId();
  for (let attempt = 0; attempt < 40; attempt += 1) {
    const now = Date.now();
    let lease = null;
    try { lease = JSON.parse(storage.getItem(LOCK_KEY) || "null"); } catch { /* Replace malformed lock. */ }
    if (!lease || lease.expires_at <= now) {
      storage.setItem(LOCK_KEY, JSON.stringify({ owner, expires_at: now + 5000 }));
      try { lease = JSON.parse(storage.getItem(LOCK_KEY) || "null"); } catch { lease = null; }
      if (lease?.owner === owner) {
        try { return await work(); }
        finally {
          try {
            const current = JSON.parse(storage.getItem(LOCK_KEY) || "null");
            if (current?.owner === owner) storage.removeItem(LOCK_KEY);
          } catch { /* Lock expires automatically. */ }
        }
      }
    }
    await sleep(15 + Math.floor(Math.random() * 25));
  }
  throw new Error("Could not coordinate this browser session across tabs.");
}
