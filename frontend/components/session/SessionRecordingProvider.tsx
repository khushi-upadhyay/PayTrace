"use client";

import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { api, getApiBaseUrl, type BrowserSessionEvent } from "@/lib/api";
import { persistSessionEvents, readSessionEvents, removeSessionEvents } from "@/lib/session-outbox";
import { ACTIVE_SESSION_KEY, activeTabLeaseCount, claimTabId, getOrCreateSessionRecord, releaseTabLease, renewTabLease, withSessionIdentityLock } from "@/lib/session-identity.mjs";
import { instrumentConsole, instrumentNetwork, sanitizeRequestUrl, sanitizeRrwebEvent } from "@/lib/session-instrumentation.mjs";
import { MAX_PACKETS_PER_UPLOAD, MEMORY_BUFFER_LIMIT, MEMORY_FLUSH_DELAY_MS, MEMORY_FLUSH_SIZE, PACKET_PACING_MS, retryDelay, restoreUnsentBatch, shouldPersistBuffer, UPLOAD_BATCH_SIZE, UPLOAD_INTERVAL_MS } from "@/lib/session-buffer-policy.mjs";
import { shouldStartSessionRecording } from "@/lib/session-recording-policy.mjs";

type RecordingChoice = "loading" | "enabled" | "disabled";
type SessionRecordingContextValue = {
  sessionId: string | null;
  recordingChoice: RecordingChoice;
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

export function SessionRecordingProvider({ children }: { children: ReactNode }) {
  const [recordingChoice, setRecordingChoice] = useState<RecordingChoice>("loading");
  const recordingChoiceRef = useRef<RecordingChoice>("loading");
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
      if (new TextEncoder().encode(JSON.stringify({ payload: event.payload ?? {}, attributes: event.attributes ?? {} })).byteLength > 95_000) {
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
      const record = await withSessionIdentityLock(() => getOrCreateSessionRecord(sharedStorage, { idleTimeout: SESSION_IDLE_TIMEOUT_MS }), { storage: sharedStorage as Storage });
      sessionStartedAt.current = record.record.created_at;
      if (record.expiredSessionId) {
        try { await api.stopSession(record.expiredSessionId); } catch { /* Expired server sessions are stopped by their idle timeout. */ }
      }
      const saved = availableStorage(sessionStorage).getItem(SESSION_CREATE_RETRY_KEY);
      const id = saved === record.record.id ? saved : record.record.id;
      const tabStorage = availableStorage(sessionStorage);
      const visitorRef = tabStorage.getItem("paytrace_visitor_ref") ?? `anon_${id}`;
      tabStorage.setItem("paytrace_visitor_ref", visitorRef);
      const session = await api.createSession({ session_id: id, visitor_ref: visitorRef, user_agent: navigator.userAgent, metadata: metadata() });
      availableStorage(sessionStorage).setItem(SESSION_CREATE_RETRY_KEY, session.id);
      activeSessionId.current = session.id;
      setSessionId(session.id);
      setRecordingError(null);
      return session.id;
    })();
    creating.current = task;
    try { return await task; } finally { creating.current = null; }
  }, []);

  const persistBuffer = useCallback(async () => {
    if (flushMemoryTimer.current) { clearTimeout(flushMemoryTimer.current); flushMemoryTimer.current = null; }
    const id = activeSessionId.current;
    if (!id || pendingEvents.current.length === 0) return;
    const batch = pendingEvents.current.splice(0, MEMORY_FLUSH_SIZE);
    try {
      const evicted = await persistSessionEvents(id, batch);
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
    if (!id) return;
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
    } catch {
      setRecordingError("Session events are waiting to upload. They will retry automatically when PayTrace is reachable.");
      const delay = retryDelay(retryAttempt.current++);
      if (uploadTimer.current) { clearInterval(uploadTimer.current); uploadTimer.current = null; }
      if (!createRetryTimer.current) createRetryTimer.current = setTimeout(() => {
        createRetryTimer.current = null;
        if (activeSessionId.current) void uploadOutbox();
      }, delay);
    }
  }, [persistBuffer]);

  const enableRecording = useCallback(async () => {
    if (recordingChoiceRef.current === "enabled") return;
    availableStorage(localStorage).setItem(CONSENT_KEY, "enabled");
    stopRequested.current = false;
    setRecordingChoice("enabled");
    setRecordingError(null);
    try { await ensureSession(); } catch (err) { setRecordingError(err instanceof Error ? err.message : "Could not start session recording."); }
    enqueue({ id: crypto.randomUUID(), event_type: "recording_enabled", category: "lifecycle", occurred_at: new Date().toISOString(), payload: { name: "recording_enabled" } });
  }, [enqueue, ensureSession]);

  const disableRecording = useCallback(() => {
    if (recordingChoiceRef.current !== "enabled" || stopRequested.current) return;
    enqueue({ id: crypto.randomUUID(), event_type: "recording_disabled", category: "lifecycle", occurred_at: new Date().toISOString(), payload: { name: "recording_disabled" } });
    availableStorage(localStorage).setItem(CONSENT_KEY, "disabled");
    stopRequested.current = true;
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
    setRecordingError(null);
    try { await ensureSession(); await uploadOutbox(); } catch (err) { setRecordingError(err instanceof Error ? err.message : "Could not connect to PayTrace."); }
  }, [ensureSession, uploadOutbox]);

  useEffect(() => {
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
  }, [ensureSession, recordingChoice]);

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
    const retry = () => {
      void ensureSession().then(() => { delay = 1000; }).catch((err) => {
        if (!active) return;
        setRecordingError(err instanceof Error ? err.message : "Session setup is offline; retrying automatically.");
        sessionCreateRetryTimer.current = setTimeout(retry, delay);
        delay = Math.min(30_000, delay * 2);
      });
    };
    retry();
    return () => { active = false; if (sessionCreateRetryTimer.current) clearTimeout(sessionCreateRetryTimer.current); sessionCreateRetryTimer.current = null; };
  }, [ensureSession, recordingChoice, sessionId]);

  useEffect(() => {
    if (recordingChoice === "disabled" && sessionId && stopRequested.current) void uploadOutbox();
  }, [recordingChoice, sessionId, uploadOutbox]);

  useEffect(() => {
    if (recordingChoice !== "enabled") return;
    let disposed = false;
    let teardown: (() => void) | undefined;
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
      teardown = () => {
        stop?.(); stopNetwork(); stopConsole();
        window.removeEventListener("popstate", onRoute);
        document.removeEventListener("visibilitychange", onVisibility);
        window.removeEventListener("resize", onResize);
        if (resizeTimer) clearTimeout(resizeTimer);
        if (history.pushState !== originalPushState) history.pushState = originalPushState;
        if (history.replaceState !== originalReplaceState) history.replaceState = originalReplaceState;
      };
    }).catch(() => setRecordingError("Session recording could not load in this browser."));
    return () => { disposed = true; teardown?.(); if (uploadTimer.current) clearInterval(uploadTimer.current); if (createRetryTimer.current) clearTimeout(createRetryTimer.current); };
  }, [enqueue, recordingChoice, uploadOutbox]);

  useEffect(() => () => {
    if (flushMemoryTimer.current) clearTimeout(flushMemoryTimer.current);
    if (uploadTimer.current) clearInterval(uploadTimer.current);
    if (createRetryTimer.current) clearTimeout(createRetryTimer.current);
    if (sessionCreateRetryTimer.current) clearTimeout(sessionCreateRetryTimer.current);
    void persistBuffer();
  }, [persistBuffer]);

  const value = useMemo(() => ({ sessionId, recordingChoice, recordingError, enableRecording, disableRecording, retryRecording, addSessionMarker }), [sessionId, recordingChoice, recordingError, enableRecording, disableRecording, retryRecording, addSessionMarker]);
  return <SessionRecordingContext.Provider value={value}>{children}</SessionRecordingContext.Provider>;
}

export function useSessionRecording() {
  const value = useContext(SessionRecordingContext);
  if (!value) throw new Error("useSessionRecording must be used inside SessionRecordingProvider");
  return value;
}

export function RecordingNotice() {
  const { sessionId, recordingChoice, recordingError, enableRecording, disableRecording, retryRecording } = useSessionRecording();
  return <aside className="fixed bottom-4 right-4 z-50 max-w-sm rounded-xl border border-slate-700 bg-slate-950/95 p-3 shadow-xl backdrop-blur" aria-live="polite">
    {recordingChoice === "loading" ? <p className="text-xs text-slate-300">Starting privacy-masked session recording…</p> : recordingChoice === "enabled" ? <div className="flex items-start gap-3"><span className="mt-1 h-2 w-2 shrink-0 rounded-full bg-emerald-400" /><div className="min-w-0 flex-1"><p className="text-xs font-semibold text-slate-100">{sessionId ? "Session recording is on" : "Session recording is buffering"}</p><p className="mt-1 text-[11px] leading-relaxed text-slate-400">Inputs are masked. PayPal-hosted pages are not recorded.</p>{recordingError && <p className="mt-1 text-[11px] text-amber-300">{recordingError}</p>}{recordingError && <button onClick={() => void retryRecording()} className="mt-2 text-[11px] text-cyan-300 hover:underline">Retry connection</button>}</div><button onClick={disableRecording} className="text-[11px] text-slate-400 hover:text-white" aria-label="Stop session recording">Stop</button></div> : <div><p className="text-xs font-semibold text-slate-100">Session recording is off</p><p className="mt-1 text-[11px] leading-relaxed text-slate-400">Recording starts automatically unless stopped here. Inputs are masked; PayPal-hosted pages are not recorded.</p><button onClick={() => void enableRecording()} className="mt-2 rounded bg-cyan-500 px-2.5 py-1.5 text-[11px] font-semibold text-slate-950 hover:bg-cyan-400">Resume recording</button></div>}
  </aside>;
}
