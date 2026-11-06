"use client";

import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { api, ApiError, getApiBaseUrl, type BrowserSessionEvent } from "@/lib/api";
import { persistSessionEvents, readSessionEvents, removeSessionEvents } from "@/lib/session-outbox";
import { ACTIVE_SESSION_KEY, activeTabLeaseCount, claimTabId, createWithExpiredSessionRecovery, getOrCreateSessionRecord, isSessionExpiredDetail, releaseTabLease, renewTabLease, replaceExpiredSessionRecord, withSessionIdentityLock } from "@/lib/session-identity.mjs";
import { instrumentConsole, instrumentNetwork, sanitizeRequestUrl, sanitizeRrwebEvent } from "@/lib/session-instrumentation.mjs";
import { MAX_PACKETS_PER_UPLOAD, MEMORY_BUFFER_LIMIT, MEMORY_FLUSH_DELAY_MS, MEMORY_FLUSH_SIZE, PACKET_PACING_MS, groupEventsBySession, retryDelay, restoreUnsentBatch, shouldPersistBuffer, UPLOAD_BATCH_SIZE, UPLOAD_INTERVAL_MS } from "@/lib/session-buffer-policy.mjs";
import { shouldStartSessionRecording } from "@/lib/session-recording-policy.mjs";
import { useAuth } from "@/components/providers/AuthProvider";

type RecordingChoice = "loading" | "enabled" | "disabled";
type SessionRecordingContextValue = {
  sessionId: string | null;
  recordingChoice: RecordingChoice;
  recorderReady: boolean;
  recordingError: string | null;
  enableRecording: () => Promise<void>;
  disableRecording: () => void;
  retryRecording: () => Promise<void>;
  addSessionMarker: (name: string, details?: Record<string, unknown>) => void;
};
const SessionRecordingContext = createContext<SessionRecordingContextValue | null>(null);
const CONSENT_KEY = "paytrace_session_recording_consent";
const SESSION_CREATE_RETRY_KEY = "paytrace_browser_session_id_v2";
const SESSION_IDLE_TIMEOUT_MS = Number(process.env.NEXT_PUBLIC_SESSION_IDLE_TIMEOUT_MS) || 1_800_000;
const memoryStorage = new Map<string, string>();
const memoryAdapter = { getItem: (key: string) => memoryStorage.get(key) ?? null, setItem: (key: string, value: string) => { memoryStorage.set(key, String(value)); }, removeItem: (key: string) => { memoryStorage.delete(key); } };
function availableStorage(storage: Storage) {
  try { const key = "__paytrace_storage_probe__"; storage.setItem(key, "1"); storage.removeItem(key); return storage; } catch { return memoryAdapter; }
}

function metadata() {
  const userAgentData = (navigator as Navigator & { userAgentData?: { brands?: Array<{ brand: string; version: string }>; mobile?: boolean; platform?: string } }).userAgentData;
  return {
    source: "paytrace_web",
    initial_path: sanitizeRequestUrl(window.location.href, window.location.href).replace(window.location.origin, ""),
    viewport: { width: window.innerWidth, height: window.innerHeight },
    screen: { width: window.screen.width, height: window.screen.height },
    device_pixel_ratio: window.devicePixelRatio,
    locale: navigator.language,
    timezone: Intl.DateTimeFormat().resolvedOptions().timeZone,
    platform: navigator.platform,
    browser: userAgentData?.brands?.map(({ brand, version }) => `${brand} ${version}`).join(", ") || "Unknown",
    device_category: userAgentData?.mobile === true ? "mobile" : userAgentData?.mobile === false ? "desktop" : "unknown",
  };
}

function isSessionExpiredError(error: unknown) {
  return error instanceof ApiError && error.status === 409 && isSessionExpiredDetail(error.detail);
}

async function createReplacementSession(expiredId: string, sharedStorage: Pick<Storage, "getItem" | "setItem">, tabStorage: Pick<Storage, "setItem">) {
  const { replacement: record, session } = await createWithExpiredSessionRecovery({
    expiredSessionId: expiredId,
    rotateSession: (staleId: string) => replaceExpiredSessionRecord(sharedStorage, staleId),
    createSession: (candidate: { id: string }) => {
      const visitorRef = `anon_${candidate.id}`;
      tabStorage.setItem("paytrace_visitor_ref", visitorRef);
      return api.createSession({ session_id: candidate.id, visitor_ref: visitorRef, user_agent: navigator.userAgent, metadata: metadata() });
    },
    isExpired: isSessionExpiredError,
    maxAttempts: 2,
  });
  return { record, session };
}

export function SessionRecordingProvider({ children }: { children: ReactNode }) {
  const { ready: authReady } = useAuth();
  const [recordingChoice, setRecordingChoice] = useState<RecordingChoice>("loading");
  const recordingChoiceRef = useRef<RecordingChoice>("loading");
  const [recorderReady, setRecorderReady] = useState(false);
  const [recorderGeneration, setRecorderGeneration] = useState(0);
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [recordingError, setRecordingError] = useState<string | null>(null);
  const pendingEvents = useRef<BrowserSessionEvent[]>([]);
  const tabClaim = useRef<ReturnType<typeof claimTabId> | null>(null);
  const sessionStartedAt = useRef(0);
  const activeSessionId = useRef<string | null>(null);
  const flushMemoryTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const uploadTimer = useRef<ReturnType<typeof setInterval> | null>(null);
  const createRetryTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const sessionCreateRetryTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const retryAttempt = useRef(0);
  const creating = useRef<Promise<string> | null>(null);
  const recovering = useRef<Map<string, Promise<string>>>(new Map());
  const expiredSessionIds = useRef<Set<string>>(new Set());
  const stopRequested = useRef(false);

  useEffect(() => { recordingChoiceRef.current = recordingChoice; }, [recordingChoice]);

  const decorate = useCallback((event: BrowserSessionEvent): BrowserSessionEvent => {
    const claim = tabClaim.current;
    const occurredAt = event.occurred_at ?? new Date().toISOString();
    const occurrenceMs = Date.parse(occurredAt);
    return {
      ...event,
      occurred_at: occurredAt,
      session_id: activeSessionId.current ?? undefined,
      tab_id: event.tab_id ?? claim?.tabId ?? null,
      segment_id: event.segment_id ?? claim?.owner ?? null,
      session_offset_ms: event.session_offset_ms ?? (Number.isFinite(occurrenceMs) ? Math.max(0, occurrenceMs - sessionStartedAt.current) : undefined),
      route: event.route ?? window.location.pathname,
      source: event.source ?? "browser",
      attributes: event.attributes ?? {},
    };
  }, []);

  const enqueue = useCallback((raw: BrowserSessionEvent) => {
    const event = decorate(raw);
    try {
      if (new TextEncoder().encode(JSON.stringify({ payload: event.payload ?? {}, attributes: event.attributes ?? {} })).byteLength > 950_000) {
        setRecordingError("An oversized replay event was skipped to stay within the server's per-event limit.");
        return;
      }
    } catch {
      setRecordingError("A malformed event could not be queued for upload.");
      return;
    }
    pendingEvents.current.push(event);
    if (pendingEvents.current.length > MEMORY_BUFFER_LIMIT) {
      pendingEvents.current.splice(0, pendingEvents.current.length - MEMORY_BUFFER_LIMIT);
      setRecordingError("The in-memory event limit was reached while offline; oldest unsent events were dropped.");
    }
    if (shouldPersistBuffer(pendingEvents.current.length)) {
      if (flushMemoryTimer.current) clearTimeout(flushMemoryTimer.current);
      flushMemoryTimer.current = setTimeout(() => void persistBuffer(), 0);
    } else if (!flushMemoryTimer.current) {
      flushMemoryTimer.current = setTimeout(() => void persistBuffer(), MEMORY_FLUSH_DELAY_MS);
    }
  }, [decorate]);

  const ensureSession = useCallback(async () => {
    if (activeSessionId.current) return activeSessionId.current;
    if (creating.current) return creating.current;
    const task = (async () => {
      const sharedStorage = availableStorage(localStorage);
      const tabStorage = availableStorage(sessionStorage);
      const session = await withSessionIdentityLock(async () => {
        let record = getOrCreateSessionRecord(sharedStorage, { idleTimeout: SESSION_IDLE_TIMEOUT_MS });
        sessionStartedAt.current = record.record.created_at;
        if (record.expiredSessionId) {
          try { await api.stopSession(record.expiredSessionId); } catch { /* Existing event and session data remain available for replay. */ }
        }
        const id = record.record.id;
        const visitorRef = tabStorage.getItem("paytrace_visitor_ref") ?? `anon_${id}`;
        tabStorage.setItem("paytrace_visitor_ref", visitorRef);
        try {
          return await api.createSession({ session_id: id, visitor_ref: visitorRef, user_agent: navigator.userAgent, metadata: metadata() });
        } catch (error) {
          if (!isSessionExpiredError(error)) throw error;
          expiredSessionIds.current.add(id);
          const replacement = await createReplacementSession(id, sharedStorage, tabStorage);
          sessionStartedAt.current = replacement.record.created_at;
          return replacement.session;
        }
      }, { storage: sharedStorage as Storage });
      availableStorage(sessionStorage).setItem(SESSION_CREATE_RETRY_KEY, session.id);
      activeSessionId.current = session.id;
      setSessionId(session.id);
      setRecordingError(null);
      return session.id;
    })();
    creating.current = task;
    try { return await task; } finally { creating.current = null; }
  }, []);

  const recoverExpiredSession = useCallback((expiredId: string): Promise<string> => {
    const existing = recovering.current.get(expiredId);
    if (existing) return existing;
    expiredSessionIds.current.add(expiredId);
    const sharedStorage = availableStorage(localStorage);
    const tabStorage = availableStorage(sessionStorage);
    const task = withSessionIdentityLock(
      async () => createReplacementSession(expiredId, sharedStorage, tabStorage),
      { storage: sharedStorage as Storage },
    ).then(({ record, session }) => {
      sessionStartedAt.current = record.created_at;
      activeSessionId.current = session.id;
      setSessionId(session.id);
      availableStorage(sessionStorage).setItem(SESSION_CREATE_RETRY_KEY, session.id);
      setRecordingError(null);
      return session.id;
    }).catch((error) => {
      activeSessionId.current = null;
      setSessionId(null);
      throw error;
    });
    recovering.current.set(expiredId, task);
    void task.then(
      () => { if (recovering.current.get(expiredId) === task) recovering.current.delete(expiredId); },
      () => { if (recovering.current.get(expiredId) === task) recovering.current.delete(expiredId); },
    );
    return task;
  }, []);

  const persistBuffer = useCallback(async () => {
    if (flushMemoryTimer.current) { clearTimeout(flushMemoryTimer.current); flushMemoryTimer.current = null; }
    const id = activeSessionId.current;
    if (!id || pendingEvents.current.length === 0) return;
    const batch = pendingEvents.current.splice(0, MEMORY_FLUSH_SIZE);
    try {
      let evicted = 0;
      for (const [eventSessionId, events] of Array.from(groupEventsBySession(batch, id).entries())) evicted += await persistSessionEvents(eventSessionId, events);
      if (evicted > 0) setRecordingError(`The local event queue reached its ${MEMORY_BUFFER_LIMIT}-event limit; ${evicted} oldest replay event(s) were evicted to preserve investigation events.`);
    } catch {
      const restored = restoreUnsentBatch(pendingEvents.current, batch, MEMORY_BUFFER_LIMIT);
      pendingEvents.current = restored.events;
      setRecordingError(restored.dropped > 0
        ? `Browser storage is unavailable and the in-memory limit was exceeded; ${restored.dropped} newest unsent event(s) could not be retained.`
        : "Browser storage is unavailable. Session events are held temporarily in memory.");
      return;
    }
    if (pendingEvents.current.length > 0) flushMemoryTimer.current = setTimeout(() => void persistBuffer(), MEMORY_FLUSH_DELAY_MS);
  }, []);

  const uploadOutbox = useCallback(async () => {
    const id = activeSessionId.current;
    if (!id || expiredSessionIds.current.has(id)) return;
    await persistBuffer();
    try {
      let remaining = 0;
      await withSessionIdentityLock(async () => {
        for (let packet = 0; packet < MAX_PACKETS_PER_UPLOAD; packet += 1) {
          const batch = await readSessionEvents(id, UPLOAD_BATCH_SIZE);
          if (batch.length === 0) break;
          await api.ingestSessionEvents(id, batch);
          await removeSessionEvents(id, batch);
          if (packet < MAX_PACKETS_PER_UPLOAD - 1) await new Promise((resolve) => setTimeout(resolve, PACKET_PACING_MS));
        }
        remaining = (await readSessionEvents(id, 1)).length;
      });
      retryAttempt.current = 0;
      setRecordingError(null);
      if (remaining > 0 || pendingEvents.current.length > 0) {
        if (!createRetryTimer.current) createRetryTimer.current = setTimeout(() => { createRetryTimer.current = null; void uploadOutbox(); }, PACKET_PACING_MS);
      } else if (stopRequested.current && activeSessionId.current === id && activeTabLeaseCount(availableStorage(localStorage)) > 0) {
        if (!createRetryTimer.current) createRetryTimer.current = setTimeout(() => { createRetryTimer.current = null; void uploadOutbox(); }, 500);
      } else if (stopRequested.current && activeSessionId.current === id) {
        await api.stopSession(id);
        activeSessionId.current = null;
        setSessionId(null);
        availableStorage(sessionStorage).removeItem(SESSION_CREATE_RETRY_KEY);
        availableStorage(localStorage).removeItem(ACTIVE_SESSION_KEY);
        stopRequested.current = false;
      } else if (!uploadTimer.current && recordingChoiceRef.current === "enabled") {
        uploadTimer.current = setInterval(() => void uploadOutbox(), 4000);
      }
    } catch (error) {
      if (isSessionExpiredError(error)) {
        try {
          await recoverExpiredSession(id);
          retryAttempt.current = 0;
          if (!createRetryTimer.current) createRetryTimer.current = setTimeout(() => { createRetryTimer.current = null; void uploadOutbox(); }, 0);
        } catch {
          setRecordingError("The previous session expired. Its queued events remain attached to that session while PayTrace reconnects.");
        }
        return;
      }
      setRecordingError("Session events are waiting to upload. They will retry automatically when PayTrace is reachable.");
      const delay = retryDelay(retryAttempt.current++);
      if (uploadTimer.current) { clearInterval(uploadTimer.current); uploadTimer.current = null; }
      if (!createRetryTimer.current) createRetryTimer.current = setTimeout(() => {
        createRetryTimer.current = null;
        if (activeSessionId.current) void uploadOutbox();
      }, delay);
    }
  }, [persistBuffer, recoverExpiredSession]);

  const enableRecording = useCallback(async () => {
    const alreadyEnabled = recordingChoiceRef.current === "enabled";
    recordingChoiceRef.current = "enabled";
    availableStorage(localStorage).setItem(CONSENT_KEY, "enabled");
    stopRequested.current = false;
    setRecordingChoice("enabled");
    setRecordingError(null);
    try {
      await ensureSession();
      if (alreadyEnabled) setRecorderGeneration((generation) => generation + 1);
      else enqueue({ id: crypto.randomUUID(), event_type: "recording_enabled", category: "lifecycle", occurred_at: new Date().toISOString(), payload: { name: "recording_enabled" } });
    } catch (err) {
      setRecordingError(err instanceof Error ? err.message : "Could not start session recording.");
      if (alreadyEnabled) setRecorderGeneration((generation) => generation + 1);
    }
  }, [enqueue, ensureSession]);

  const disableRecording = useCallback(() => {
    if (recordingChoiceRef.current !== "enabled" || stopRequested.current) return;
    enqueue({ id: crypto.randomUUID(), event_type: "recording_disabled", category: "lifecycle", occurred_at: new Date().toISOString(), payload: { name: "recording_disabled" } });
    availableStorage(localStorage).setItem(CONSENT_KEY, "disabled");
    stopRequested.current = true;
    recordingChoiceRef.current = "disabled";
    setRecorderReady(false);
    setRecordingChoice("disabled");
    if (flushMemoryTimer.current) clearTimeout(flushMemoryTimer.current);
    if (uploadTimer.current) clearInterval(uploadTimer.current);
    if (createRetryTimer.current) clearTimeout(createRetryTimer.current);
    void (async () => {
      await persistBuffer();
      await uploadOutbox();
    })();
  }, [enqueue, persistBuffer, uploadOutbox]);

  const addSessionMarker = useCallback((name: string, details: Record<string, unknown> = {}) => {
    if (recordingChoice !== "enabled") return;
    enqueue({ id: crypto.randomUUID(), event_type: "marker", category: "application", occurred_at: new Date().toISOString(), attributes: details, payload: { name } });
  }, [enqueue, recordingChoice]);

  const retryRecording = useCallback(async () => {
    if (recordingChoiceRef.current !== "enabled") {
      await enableRecording();
      return;
    }
    setRecordingError(null);
    try {
      await ensureSession();
      await uploadOutbox();
      setRecorderGeneration((generation) => generation + 1);
    } catch (err) { setRecordingError(err instanceof Error ? err.message : "Could not connect to PayTrace."); }
  }, [enableRecording, ensureSession, uploadOutbox]);

  useEffect(() => {
    if (!authReady) return;
    const sharedStorage = availableStorage(localStorage);
    const tabStorage = availableStorage(sessionStorage);
    const consent = sharedStorage.getItem(CONSENT_KEY);
    const shouldRecord = shouldStartSessionRecording(consent);
    setRecordingChoice(shouldRecord ? "enabled" : "disabled");
    if (!shouldRecord) return;
    sessionStartedAt.current = Date.now();
    try { tabClaim.current = claimTabId(tabStorage, sharedStorage); } catch { tabClaim.current = null; }
    const record = getOrCreateSessionRecord(sharedStorage, { idleTimeout: SESSION_IDLE_TIMEOUT_MS });
    sessionStartedAt.current = record.record.created_at;
    void ensureSession().catch((err) => setRecordingError(err instanceof Error ? err.message : "Could not create a session."));
    const lease = setInterval(() => {
      const claim = tabClaim.current;
      if (claim && !renewTabLease(sharedStorage, claim)) tabClaim.current = claimTabId(tabStorage, sharedStorage);
      const current = sharedStorage.getItem("paytrace_active_session_v2");
      if (current && activeSessionId.current) {
        try {
          const parsed = JSON.parse(current);
          sharedStorage.setItem("paytrace_active_session_v2", JSON.stringify({ ...parsed, last_activity_at: Date.now() }));
        } catch { /* A corrupt record is replaced on next start. */ }
      }
    }, 10_000);
    const release = () => { if (tabClaim.current) releaseTabLease(sharedStorage, tabClaim.current); };
    window.addEventListener("pagehide", release);
    return () => { clearInterval(lease); window.removeEventListener("pagehide", release); release(); };
  }, [authReady, ensureSession, recordingChoice]);

  useEffect(() => {
    const onConsentChange = (event: StorageEvent) => {
      if (event.key !== CONSENT_KEY) return;
      if (event.newValue === "disabled" && recordingChoiceRef.current === "enabled") disableRecording();
      else if (event.newValue === "enabled" && recordingChoiceRef.current !== "enabled") void enableRecording();
    };
    window.addEventListener("storage", onConsentChange);
    return () => window.removeEventListener("storage", onConsentChange);
  }, [disableRecording, enableRecording]);

  useEffect(() => {
    if (recordingChoice !== "enabled" || sessionId) return;
    let active = true;
    let delay = 1000;
    let attempts = 0;
    const maxAttempts = 5;
    const retry = () => {
      if (!active || attempts >= maxAttempts) return;
      void ensureSession().then(() => { delay = 1000; }).catch((err) => {
        if (!active) return;
        setRecordingError(err instanceof Error ? err.message : "Session setup is offline; retrying automatically.");
        attempts += 1;
        if (attempts >= maxAttempts) return;
        sessionCreateRetryTimer.current = setTimeout(retry, delay);
        delay = Math.min(30_000, delay * 2);
      });
    };
    const onOnline = () => { attempts = 0; delay = 1000; retry(); };
    const onVisible = () => { if (document.visibilityState === "visible") onOnline(); };
    window.addEventListener("online", onOnline);
    document.addEventListener("visibilitychange", onVisible);
    retry();
    return () => {
      active = false;
      window.removeEventListener("online", onOnline);
      document.removeEventListener("visibilitychange", onVisible);
      if (sessionCreateRetryTimer.current) clearTimeout(sessionCreateRetryTimer.current);
      sessionCreateRetryTimer.current = null;
    };
  }, [ensureSession, recordingChoice, sessionId]);

  useEffect(() => {
    if (recordingChoice === "disabled" && sessionId && stopRequested.current) void uploadOutbox();
  }, [recordingChoice, sessionId, uploadOutbox]);

  useEffect(() => {
    if (!authReady || recordingChoice !== "enabled") { setRecorderReady(false); return; }
    let disposed = false;
    let teardown: (() => void) | undefined;
    setRecorderReady(false);
    uploadTimer.current = setInterval(() => void uploadOutbox(), UPLOAD_INTERVAL_MS);
    void import("rrweb").then(({ record }) => {
      if (disposed) return;
      const stop = record({
        emit: (event) => enqueue({ id: crypto.randomUUID(), event_type: "rrweb", category: "replay", occurred_at: new Date(event.timestamp).toISOString(), payload: sanitizeRrwebEvent(event, window.location.href) as Record<string, unknown> }),
        maskAllInputs: true,
        maskTextSelector: "[data-rr-mask], .rr-mask",
        blockSelector: "[data-rr-block], .rr-block, [contenteditable='true']",
        sampling: { mousemove: false, scroll: 150 },
        checkoutEveryNms: 60_000,
        recordCanvas: false,
        inlineImages: false,
      });
      const tabId = tabClaim.current?.tabId ?? "unknown";
      const tabStartedKey = `paytrace_tab_started_v2:${tabId}`;
      const recordingStartedKey = `paytrace_recording_started_v2:${tabId}`;
      const perTab = availableStorage(sessionStorage);
      if (!perTab.getItem(tabStartedKey)) {
        perTab.setItem(tabStartedKey, "1");
        enqueue({ id: crypto.randomUUID(), event_type: "tab_started", category: "lifecycle", occurred_at: new Date().toISOString(), payload: { name: "tab_started" } });
      }
      if (!perTab.getItem(recordingStartedKey)) {
        perTab.setItem(recordingStartedKey, "1");
        enqueue({ id: crypto.randomUUID(), event_type: "recording_started", category: "lifecycle", occurred_at: new Date().toISOString(), payload: { name: "recording_started" } });
      }
      let previousRoute = window.location.pathname;
      const onRoute = () => {
        const route = window.location.pathname;
        if (route === previousRoute) return;
        previousRoute = route;
        enqueue({ id: crypto.randomUUID(), event_type: "route_changed", category: "lifecycle", occurred_at: new Date().toISOString(), payload: { name: "route_changed" }, route });
      };
      const originalPushState = history.pushState;
      const originalReplaceState = history.replaceState;
      history.pushState = function (...args) { const result = originalPushState.apply(this, args); onRoute(); return result; };
      history.replaceState = function (...args) { const result = originalReplaceState.apply(this, args); onRoute(); return result; };
      const onVisibility = () => enqueue({ id: crypto.randomUUID(), event_type: document.visibilityState === "hidden" ? "visibility_hidden" : "visibility_visible", category: "lifecycle", occurred_at: new Date().toISOString(), payload: { visibility: document.visibilityState } });
      let resizeTimer: ReturnType<typeof setTimeout> | null = null;
      const onResize = () => {
        if (resizeTimer) clearTimeout(resizeTimer);
        resizeTimer = setTimeout(() => enqueue({ id: crypto.randomUUID(), event_type: "viewport_changed", category: "lifecycle", occurred_at: new Date().toISOString(), payload: { viewport: { width: window.innerWidth, height: window.innerHeight }, device_pixel_ratio: window.devicePixelRatio } }), 500);
      };
      window.addEventListener("popstate", onRoute);
      document.addEventListener("visibilitychange", onVisibility);
      window.addEventListener("resize", onResize, { passive: true });
      const context = () => ({ session_id: activeSessionId.current, tab_id: tabClaim.current?.tabId, segment_id: tabClaim.current?.owner, route: window.location.pathname });
      const stopNetwork = instrumentNetwork({ apiBaseUrl: getApiBaseUrl(), context, emit: enqueue });
      const stopConsole = instrumentConsole({ context, emit: enqueue });
      setRecorderReady(true);
      teardown = () => {
        stop?.(); stopNetwork(); stopConsole();
        window.removeEventListener("popstate", onRoute);
        document.removeEventListener("visibilitychange", onVisibility);
        window.removeEventListener("resize", onResize);
        if (resizeTimer) clearTimeout(resizeTimer);
        if (history.pushState !== originalPushState) history.pushState = originalPushState;
        if (history.replaceState !== originalReplaceState) history.replaceState = originalReplaceState;
      };
    }).catch(() => {
      if (disposed) return;
      setRecorderReady(false);
      setRecordingError("Session recording could not load in this browser. Use Retry recording in Settings to try again.");
    });
    return () => { disposed = true; teardown?.(); if (uploadTimer.current) clearInterval(uploadTimer.current); if (createRetryTimer.current) clearTimeout(createRetryTimer.current); };
  }, [authReady, enqueue, recordingChoice, recorderGeneration, uploadOutbox]);

  useEffect(() => () => {
    if (flushMemoryTimer.current) clearTimeout(flushMemoryTimer.current);
    if (uploadTimer.current) clearInterval(uploadTimer.current);
    if (createRetryTimer.current) clearTimeout(createRetryTimer.current);
    if (sessionCreateRetryTimer.current) clearTimeout(sessionCreateRetryTimer.current);
    void persistBuffer();
  }, [persistBuffer]);

  const value = useMemo(() => ({ sessionId, recordingChoice, recorderReady, recordingError, enableRecording, disableRecording, retryRecording, addSessionMarker }), [sessionId, recordingChoice, recorderReady, recordingError, enableRecording, disableRecording, retryRecording, addSessionMarker]);
  return <SessionRecordingContext.Provider value={value}>{children}</SessionRecordingContext.Provider>;
}

export function useSessionRecording() {
  const value = useContext(SessionRecordingContext);
  if (!value) throw new Error("useSessionRecording must be used inside SessionRecordingProvider");
  return value;
}
