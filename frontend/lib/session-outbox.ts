import type { BrowserSessionEvent } from "@/lib/api";

const DATABASE = "paytrace-session-outbox";
const STORE = "events";
const MAX_STORED_EVENTS = 1000;

function openDatabase(): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    if (typeof indexedDB === "undefined") {
      reject(new Error("Browser event storage is unavailable."));
      return;
    }
    const request = indexedDB.open(DATABASE, 1);
    request.onupgradeneeded = () => {
      if (!request.result.objectStoreNames.contains(STORE)) {
        request.result.createObjectStore(STORE, { keyPath: "key" });
      }
    };
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error ?? new Error("Could not open browser event storage."));
  });
}

type StoredEvent = { key: string; sessionId: string; event: BrowserSessionEvent };
function transaction<T>(mode: IDBTransactionMode, run: (store: IDBObjectStore) => IDBRequest<T>): Promise<T> {
  return openDatabase().then((db) => new Promise<T>((resolve, reject) => {
    const tx = db.transaction(STORE, mode);
    const request = run(tx.objectStore(STORE));
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error ?? new Error("Browser event storage failed."));
    tx.oncomplete = () => db.close();
    tx.onerror = () => { db.close(); reject(tx.error ?? new Error("Browser event storage failed.")); };
    tx.onabort = () => { db.close(); reject(tx.error ?? new Error("Browser event storage was interrupted.")); };
  }));
}

export async function persistSessionEvents(sessionId: string, events: BrowserSessionEvent[]) {
  if (events.length === 0) return 0;
  const db = await openDatabase();
  return await new Promise<number>((resolve, reject) => {
    const tx = db.transaction(STORE, "readwrite");
    const store = tx.objectStore(STORE);
    for (const event of events) {
      if (event.id) store.put({ key: `${sessionId}:${event.id}`, sessionId, event } satisfies StoredEvent);
    }
    const all = store.getAll() as IDBRequest<StoredEvent[]>;
    let evicted = 0;
    all.onsuccess = () => {
      const rows = all.result;
      const excess = Math.max(0, rows.length - MAX_STORED_EVENTS);
      const evictionOrder = [...rows].sort((a, b) => {
        const aReplay = a.event.category === "replay" || a.event.event_type === "rrweb" ? 0 : 1;
        const bReplay = b.event.category === "replay" || b.event.event_type === "rrweb" ? 0 : 1;
        return aReplay - bReplay || (a.event.occurred_at ?? "").localeCompare(b.event.occurred_at ?? "");
      });
      for (const row of evictionOrder.slice(0, excess)) { store.delete(row.key); evicted += 1; }
    };
    tx.oncomplete = () => { db.close(); resolve(evicted); };
    tx.onerror = () => { db.close(); reject(tx.error ?? new Error("Could not save session events locally.")); };
    tx.onabort = () => { db.close(); reject(tx.error ?? new Error("Could not save session events locally.")); };
  });
}


export async function readSessionEvents(sessionId: string, limit = 20): Promise<BrowserSessionEvent[]> {
  const rows = await transaction("readonly", (store) => store.getAll()) as StoredEvent[];
  return rows.filter((row) => row.sessionId === sessionId)
    .sort((a, b) => (a.event.occurred_at ?? "").localeCompare(b.event.occurred_at ?? ""))
    .slice(0, limit)
    .map((row) => row.event);
}

export async function removeSessionEvents(sessionId: string, events: BrowserSessionEvent[]) {
  if (events.length === 0) return;
  const db = await openDatabase();
  await new Promise<void>((resolve, reject) => {
    const tx = db.transaction(STORE, "readwrite");
    const store = tx.objectStore(STORE);
    for (const event of events) if (event.id) store.delete(`${sessionId}:${event.id}`);
    tx.oncomplete = () => { db.close(); resolve(); };
    tx.onerror = () => { db.close(); reject(tx.error ?? new Error("Could not clear uploaded session events.")); };
    tx.onabort = () => { db.close(); reject(tx.error ?? new Error("Could not clear uploaded session events.")); };
  });
}
