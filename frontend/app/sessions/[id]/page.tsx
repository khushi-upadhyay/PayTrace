"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { AgGridReact } from "ag-grid-react";
import { AgGridProvider } from "ag-grid-react";
import { AllCommunityModule, ColDef, themeQuartz } from "ag-grid-community";
import { AlertTriangle, ArrowLeft, Loader2, Pause, Play, Video } from "lucide-react";
import { api, type BrowserSessionEvent, type BrowserSessionReplay } from "@/lib/api";
import { createReplayConfig, normalizeOccurrenceTime, PLAYBACK_SPEEDS, seekPreservingPlayback } from "@/lib/session-playback.mjs";

type PanelTab = "journey" | "events" | "alerts";
type SignalTab = "console" | "network";
type ReplayEvent = BrowserSessionEvent & { id: string; occurred_at: string };
type SignalGridRow = ReplayEvent & { method: string; endpoint: string; status_code: string; duration: string; log_level: string };
function formatTime(milliseconds: number) {
  const seconds = Math.max(0, Math.floor(milliseconds / 1000));
  return `${Math.floor(seconds / 60).toString().padStart(2, "0")}:${(seconds % 60).toString().padStart(2, "0")}`;
}
function labelFor(event: ReplayEvent) {
  const attributes = event.attributes ?? {};
  const payload = event.payload ?? {};
  return String(attributes.name ?? payload.name ?? payload.message ?? event.event_type ?? "Unknown event").replaceAll("_", " ");
}
function safeString(value: unknown, fallback = "Unavailable") {
  return typeof value === "string" && value.length ? value : fallback;
}
function chronologyTime(event: ReplayEvent) {
  const occurrenceUnknown = event.attributes?.timestamp_source === "ingestion_fallback";
  return normalizeOccurrenceTime(occurrenceUnknown ? event.received_at : event.occurred_at);
}
function isAlertEvent(event: ReplayEvent) {
  const attributes = event.attributes ?? {};
  const payload = event.payload ?? {};
  const status = Number(attributes.status ?? payload.status);
  const text = [event.event_type, labelFor(event), attributes.error_name, attributes.error_message, payload.error, payload.message]
    .filter((value): value is string => typeof value === "string")
    .join(" ")
    .toLowerCase();
  return event.severity === "error" || event.severity === "warn" ||
    ((event.category === "network" || event.category === "payment") && Number.isFinite(status) && status >= 400) ||
    /error|exception|failed|failure|denied|timeout|uncertain/.test(text);
}
function isJourneyEvent(event: ReplayEvent) {
  return !["console", "network", "payment"].includes(event.category ?? "") &&
    !["console", "network", "payment"].includes(event.event_type);
}
function eventOffset(event: ReplayEvent, starts: Map<string, number>, ends: Map<string, number>) {
  if (event.attributes?.timestamp_source === "ingestion_fallback") return null;
  const occurred = normalizeOccurrenceTime(event.occurred_at);
  const segment = event.segment_id ?? "legacy";
  const start = starts.get(segment);
  if (occurred === null || start === undefined) return null;
  const offset = occurred - start;
  const end = ends.get(segment);
  return offset >= 0 && (end === undefined || offset <= end - start) ? offset : null;
}

export default function SessionReplayPage() {
  const params = useParams();
  const sessionId = params.id as string;
  const hostRef = useRef<HTMLDivElement>(null);
  const replayerRef = useRef<InstanceType<typeof import("rrweb").Replayer> | null>(null);
  const eventRef = useRef<ReplayEvent[]>([]);
  const loadedPlayerEvents = useRef(0);
  const pendingSeek = useRef<number | null>(null);
  const [replay, setReplay] = useState<BrowserSessionReplay | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [duration, setDuration] = useState(0);
  const [currentTime, setCurrentTime] = useState(0);
  const [playing, setPlaying] = useState(false);
  const [playerError, setPlayerError] = useState<string | null>(null);
  const [speed, setSpeed] = useState(1);
  const [skipInactive, setSkipInactive] = useState(true);
  const inactiveThreshold = 5000;
  const [tab, setTab] = useState<PanelTab>("journey");
  const [signalTab, setSignalTab] = useState<SignalTab>("network");
  const [selectedSegment, setSelectedSegment] = useState<string | null>(null);
  const [selectedEvent, setSelectedEvent] = useState<ReplayEvent | null>(null);
  const [severityFilter, setSeverityFilter] = useState("all");
  const [tabFilter, setTabFilter] = useState("all");
  const [search, setSearch] = useState("");
  const [fromTime, setFromTime] = useState("");
  const [toTime, setToTime] = useState("");
  const [collapseLifecycle, setCollapseLifecycle] = useState(true);

  useEffect(() => {
    let active = true;
    setLoading(true); setError(null); setReplay(null); setSelectedSegment(null);
    api.getSessionReplay(sessionId, 500, 0)
      .then((data) => { if (active) setReplay(data); })
      .catch((err) => { if (active) setError(err instanceof Error ? err.message : "Could not load replay events."); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [sessionId]);

  const allEvents = useMemo(() => {
    const events = (replay?.events ?? []) as ReplayEvent[];
    const paymentEvents = (replay?.payment_events ?? []).map((event) => ({
      ...(event as unknown as ReplayEvent),
      payload: (event.payload as Record<string, unknown> | undefined) ?? {},
    }));
    const unique = new Map<string, ReplayEvent>();
    for (const event of [...events, ...paymentEvents]) unique.set(event.id, event);
    return Array.from(unique.values()).sort((a, b) => (chronologyTime(a) ?? Number.MAX_SAFE_INTEGER) - (chronologyTime(b) ?? Number.MAX_SAFE_INTEGER) || a.id.localeCompare(b.id));
  }, [replay]);
  eventRef.current = (replay?.events ?? []) as ReplayEvent[];

  const segmentMap = useMemo(() => {
    const map = new Map<string, { events: Record<string, unknown>[]; start: number; end: number; tabId: string | null }>();
    for (const event of (replay?.events ?? []) as ReplayEvent[]) {
      if (event.event_type !== "rrweb" || typeof event.payload.type !== "number" || typeof event.payload.timestamp !== "number") continue;
      const segment = event.segment_id ?? "legacy";
      const timestamp = Number(event.payload.timestamp);
      const entry = map.get(segment) ?? { events: [], start: timestamp, end: timestamp, tabId: event.tab_id ?? null };
      entry.events.push(event.payload);
      entry.start = Math.min(entry.start, timestamp);
      entry.end = Math.max(entry.end, timestamp);
      map.set(segment, entry);
    }
    return map;
  }, [replay]);
  const segmentStarts = useMemo(() => new Map(Array.from(segmentMap).map(([id, value]) => [id, value.start])), [segmentMap]);
  const segmentEnds = useMemo(() => new Map(Array.from(segmentMap).map(([id, value]) => [id, value.end])), [segmentMap]);
  const currentSegment = selectedSegment ? segmentMap.get(selectedSegment) : undefined;

  useEffect(() => {
    if (!selectedSegment && segmentMap.size > 0) setSelectedSegment(segmentMap.keys().next().value ?? null);
  }, [selectedSegment, segmentMap]);

  const applyFit = useCallback(() => {
    const host = hostRef.current;
    const player = replayerRef.current;
    if (!host || !player) return;
    const meta = player.getMetaData() as { totalTime: number; width?: number; height?: number };
    const metaEvent = (currentSegment?.events ?? []).find((event) => event.type === 4);
    const recordedSize = metaEvent?.data as { width?: number; height?: number } | undefined;
    const width = recordedSize?.width || meta.width || player.iframe?.contentWindow?.innerWidth || 1280;
    const height = recordedSize?.height || meta.height || player.iframe?.contentWindow?.innerHeight || 720;
    const availableWidth = Math.max(280, host.clientWidth);
    const availableHeight = 900;
    const scale = Math.min(availableWidth / width, availableHeight / height, 1);
    host.style.height = `${Math.max(240, Math.round(height * scale))}px`;
    // Keep the iframe at its recorded resolution and scale the whole wrapper visually,
    // instead of resizing the iframe box (which makes the recorded page reflow and
    // breaks the height estimate above, clipping content until fullscreen).
    player.wrapper.style.width = `${width}px`;
    player.wrapper.style.height = `${height}px`;
    player.wrapper.style.maxWidth = "none";
    player.wrapper.style.transform = `scale(${scale})`;
    player.wrapper.style.transformOrigin = "top left";
    player.iframe.style.width = `${width}px`;
    player.iframe.style.height = `${height}px`;
    player.iframe.style.maxWidth = "none";
  }, [currentSegment]);

  useEffect(() => {
    const host = hostRef.current;
    if (!host || !selectedSegment || !currentSegment || currentSegment.events.length === 0) return;
    let active = true;
    let localPlayer: InstanceType<typeof import("rrweb").Replayer> | null = null;
    host.replaceChildren();
    setPlayerError(null);
    void import("rrweb").then(({ Replayer }) => {
      if (!active) return;
      try {
        const events = (segmentMap.get(selectedSegment)?.events ?? []) as never[];
        localPlayer = new Replayer(events, { root: host, showWarning: false, mouseTail: false, ...createReplayConfig({ speed, skipInactive, inactiveThreshold }) });
        replayerRef.current = localPlayer;
        loadedPlayerEvents.current = events.length;
        setDuration(localPlayer.getMetaData().totalTime);
        setCurrentTime(pendingSeek.current ?? 0);
        if (pendingSeek.current !== null) {
          seekPreservingPlayback(localPlayer, pendingSeek.current, playing);
          pendingSeek.current = null;
        } else {
          // Start playback automatically so the recording doesn't sit on a blank frame
          // waiting for a click.
          localPlayer.play(0);
          setPlaying(true);
        }
        requestAnimationFrame(applyFit);
      } catch (err) { setPlayerError(err instanceof Error ? err.message : "The stored recording could not be replayed."); }
    }).catch(() => setPlayerError("The replay player could not be loaded."));
    return () => {
      active = false;
      localPlayer?.destroy();
      if (replayerRef.current === localPlayer) replayerRef.current = null;
      loadedPlayerEvents.current = 0;
      host.replaceChildren();
    };
  }, [sessionId, selectedSegment]);

  useEffect(() => {
    const player = replayerRef.current;
    const events = currentSegment?.events ?? [];
    if (!player || events.length <= loadedPlayerEvents.current) return;
    for (const event of events.slice(loadedPlayerEvents.current)) player.addEvent(event as never);
    loadedPlayerEvents.current = events.length;
    setDuration(player.getMetaData().totalTime);
  }, [currentSegment]);

  useEffect(() => { replayerRef.current?.setConfig(createReplayConfig({ speed, skipInactive, inactiveThreshold })); }, [speed, skipInactive, inactiveThreshold]);
  useEffect(() => {
    const host = hostRef.current;
    if (!host) return;
    const observer = new ResizeObserver(applyFit);
    observer.observe(host);
    return () => observer.disconnect();
  }, [applyFit]);
  useEffect(() => {
    if (!playing) return;
    const timer = setInterval(() => {
      const player = replayerRef.current;
      if (!player) return;
      const time = player.getCurrentTime();
      setCurrentTime(time);
      const matching = eventRef.current.filter((event) => event.event_type !== "rrweb" && (event.segment_id ?? "legacy") === selectedSegment)
        .find((event) => { const offset = eventOffset(event, segmentStarts, segmentEnds); return offset !== null && Math.abs(offset - time) <= 250; });
      if (matching && matching.id !== selectedEvent?.id) setSelectedEvent(matching);
      if (duration > 0 && time >= duration) setPlaying(false);
    }, 200);
    return () => clearInterval(timer);
  }, [playing, duration, selectedEvent?.id, selectedSegment, segmentStarts, segmentEnds]);

  const seek = (value: number) => {
    const player = replayerRef.current;
    if (!player) return;
    if (!seekPreservingPlayback(player, value, playing)) return;
    setCurrentTime(value);
  };
  const selectEvent = (event: ReplayEvent) => {
    setSelectedEvent(event);
    if (event.event_type === "rrweb") return;
    const segment = event.segment_id ?? "legacy";
    const offset = eventOffset(event, segmentStarts, segmentEnds);
    if (offset === null) return;
    if (segment !== selectedSegment) {
      pendingSeek.current = offset;
      setSelectedSegment(segment);
    } else seek(offset);
  };
  const togglePlayback = () => {
    const player = replayerRef.current;
    if (!player) return;
    if (playing) { player.pause(); setPlaying(false); }
    else { player.play(currentTime >= duration && duration > 0 ? 0 : currentTime); setPlaying(true); }
  };
  const loadMore = async () => {
    if (!replay || !replay.has_more || loadingMore) return;
    setLoadingMore(true);
    try {
      const next = await api.getSessionReplay(sessionId, 500, (replay.offset ?? 0) + (replay.returned_events ?? replay.events.length));
      setReplay((current) => current ? ({ ...current, ...next, events: [...current.events, ...next.events.filter((e) => !current.events.some((old) => old.id === e.id))], payment_events: next.payment_events }) : next);
    } catch (err) { setError(err instanceof Error ? err.message : "Could not load the next event page."); }
    finally { setLoadingMore(false); }
  };

  const investigationEvents = allEvents.filter((event) => event.event_type !== "rrweb");
  const matchesFilters = (event: ReplayEvent) => {
    if (severityFilter !== "all" && (event.severity ?? "info") !== severityFilter) return false;
    if (tabFilter !== "all" && (event.tab_id ?? "unknown") !== tabFilter) return false;
    const occurred = normalizeOccurrenceTime(event.occurred_at);
    if (fromTime && occurred !== null && occurred < new Date(fromTime).getTime()) return false;
    if (toTime && occurred !== null && occurred > new Date(toTime).getTime()) return false;
    if (search) {
      const safeFields = `${labelFor(event)} ${JSON.stringify(event.attributes ?? {})} ${JSON.stringify(event.payload ?? {})}`.toLowerCase();
      if (!safeFields.includes(search.toLowerCase())) return false;
    }
    return true;
  };
  const filteredEvents = investigationEvents.filter(matchesFilters);
  const visibleEvents = tab === "journey" ? filteredEvents.filter(isJourneyEvent)
    : tab === "alerts" ? filteredEvents.filter(isAlertEvent) : filteredEvents;
  const signalEvents = filteredEvents.filter((event) =>
    signalTab === "console" ? event.category === "console" || event.event_type === "console"
      : event.category === "network" || event.event_type === "network",
  );
  const signalGridRows = useMemo<SignalGridRow[]>(() => signalEvents.map((event) => {
    const attributes = (event.attributes ?? {}) as Record<string, unknown>;
    const payload = (event.payload ?? {}) as Record<string, unknown>;
    return {
      ...event,
      method: String(attributes.method ?? payload.method ?? "—"),
      endpoint: String(attributes.url ?? payload.url ?? labelFor(event)),
      status_code: String(attributes.status ?? payload.status ?? (signalTab === "console" ? event.severity ?? "info" : "—")),
      duration: attributes.duration_ms == null && payload.duration_ms == null ? "—" : `${String(attributes.duration_ms ?? payload.duration_ms)} ms`,
      log_level: String(event.severity ?? "info").toUpperCase(),
    };
  }), [signalEvents, signalTab]);
  const signalColumns = useMemo<ColDef<SignalGridRow>[]>(() => [
    { field: "occurred_at", headerName: "Time", minWidth: 175, valueFormatter: ({ value }) => value ? new Date(value).toLocaleString() : "—" },
    ...(signalTab === "network" ? [{ field: "method", headerName: "Method", width: 100 } as ColDef<SignalGridRow>, { field: "endpoint", headerName: "Endpoint", minWidth: 250, flex: 2 } as ColDef<SignalGridRow>, { field: "status_code", headerName: "HTTP status", width: 120 } as ColDef<SignalGridRow>, { field: "duration", headerName: "Duration", width: 110 } as ColDef<SignalGridRow>] : [{ field: "log_level", headerName: "Level", width: 110 } as ColDef<SignalGridRow>, { field: "endpoint", headerName: "Message", minWidth: 250, flex: 2 } as ColDef<SignalGridRow>]),
    { field: "route", headerName: "Route", minWidth: 150, valueFormatter: ({ value }) => value || "—" },
    { field: "tab_id", headerName: "Tab ID", minWidth: 125, valueFormatter: ({ value }) => value ? String(value).slice(0, 10) : "—" },
  ], [signalTab]);
  const timelineGroups: Array<{ event: ReplayEvent; repeats: ReplayEvent[] }> = [];
  for (const event of visibleEvents) {
    const previous = timelineGroups[timelineGroups.length - 1];
    const sameLifecycle = collapseLifecycle && event.category === "lifecycle" && previous?.event.category === "lifecycle"
      && event.event_type === previous.event.event_type && event.route === previous.event.route
      && (normalizeOccurrenceTime(event.occurred_at) ?? 0) - (normalizeOccurrenceTime(previous.repeats[previous.repeats.length - 1]?.occurred_at) ?? 0) <= 30_000;
    if (sameLifecycle) previous.repeats.push(event);
    else timelineGroups.push({ event, repeats: [event] });
  }
  const tabIds = Array.from(new Set(investigationEvents.map((event) => event.tab_id).filter((id): id is string => Boolean(id)))).sort();
  const eventAttributes = (selectedEvent?.attributes ?? {}) as Record<string, unknown>;
  const eventPayload = (selectedEvent?.payload ?? {}) as Record<string, unknown>;
  const detail: Record<string, unknown> = { session_id: selectedEvent?.session_id ?? sessionId, tab_id: selectedEvent?.tab_id ?? "Unavailable", route: selectedEvent?.route ?? "Unavailable", payment_id: selectedEvent?.payment_id ?? null, order_id: selectedEvent?.order_id ?? null, trace_id: selectedEvent?.trace_id ?? null, ...eventPayload, ...eventAttributes };
  const timelineMarkers = investigationEvents.map((event) => ({ event, offset: eventOffset(event, segmentStarts, segmentEnds) }))
    .filter((marker) => (marker.event.segment_id ?? "legacy") === selectedSegment && marker.offset !== null && duration > 0);
  const alertCount = investigationEvents.filter(isAlertEvent).length;

  return <div className="w-full min-w-0 space-y-5 animate-fadeIn">
    <header className="flex flex-wrap items-start justify-between gap-3 border-b border-slate-800 pb-5">
      <div className="min-w-0"><Link href="/sessions" className="mb-2 inline-flex items-center gap-1 text-xs text-slate-400 hover:text-cyan-300"><ArrowLeft className="h-3.5 w-3.5" />All sessions</Link><h1 className="flex items-center gap-2 text-2xl font-bold text-black"><Video className="h-6 w-6 text-cyan-400" />Customer session replay</h1>{replay && <p className="mt-1 break-all font-mono text-[13px] text-slate-500">{replay.session_id} · {replay.visitor_ref}</p>}</div>
      {replay?.payment_ids?.map((paymentId) => <Link key={paymentId} href={`/payments/${paymentId}`} className="rounded-lg border border-slate-700 bg-slate-900 px-3 py-2 text-xs text-cyan-300 hover:bg-slate-800">Open payment {paymentId.slice(0, 8)}</Link>)}
    </header>
    {loading ? <div className="flex justify-center py-20"><Loader2 className="h-7 w-7 animate-spin text-cyan-400" /></div> : error ? <div role="alert" className="rounded-xl border border-rose-500/30 bg-rose-950/20 p-5 text-sm text-rose-200">{error}</div> : <>
      <div className="grid min-w-0 gap-4 xl:grid-cols-[minmax(0,1.35fr)_minmax(360px,0.85fr)]">
        <section className="min-w-0 space-y-3">
          {segmentMap.size > 0 && <div className="rounded-xl border border-slate-800 bg-slate-900/50 p-3">
            <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-400">Recording tabs</p>
            <div className="flex gap-2 overflow-x-auto">
              {Array.from(segmentMap.entries()).map(([id, segment], index) => (
                <button key={id} type="button" aria-pressed={selectedSegment === id}
                  onClick={() => { setSelectedSegment(id); setCurrentTime(0); setPlaying(false); }}
                  className={`shrink-0 rounded-lg border px-3 py-2 text-left text-xs ${selectedSegment === id ? "border-cyan-500 bg-cyan-950/40 text-cyan-200" : "border-slate-700 text-slate-300 hover:bg-slate-800"}`}>
                  <span className="block font-semibold">{segment.tabId ? `Tab ${segment.tabId.slice(0, 8)}` : "Older recording"}</span>
                  <span className="mt-0.5 block text-[10px] text-slate-500">Recording {index + 1}</span>
                </button>
              ))}
            </div>
          </div>}
          <div className="min-w-0 overflow-hidden rounded-xl border border-slate-800 bg-white">
            <div ref={hostRef} className="min-h-[360px] w-full overflow-hidden" />
            {segmentMap.size === 0 && <div className="flex min-h-[360px] flex-col items-center justify-center bg-slate-900 p-8 text-center"><Video className="h-8 w-8 text-slate-500" /><p className="mt-3 text-sm font-semibold text-ink">No replay snapshot is available</p><p className="mt-1 max-w-md text-xs text-slate-400">The session has investigation events, but no stored rrweb snapshot.</p></div>}
          </div>
          {segmentMap.size > 0 && <div className="flex flex-wrap items-center gap-3 rounded-xl border border-slate-800 bg-slate-950 px-3 py-2.5">
            <button onClick={togglePlayback} disabled={!replayerRef.current} aria-label={playing ? "Pause replay" : "Play replay"} className="rounded-lg bg-cyan-500 p-2 text-slate-950 hover:bg-cyan-400 disabled:opacity-50">{playing ? <Pause className="h-4 w-4" /> : <Play className="h-4 w-4" />}</button>
            <span className="font-mono text-xs text-slate-300">{formatTime(currentTime)}</span>
            <div className="relative min-w-[120px] flex-1"><input aria-label="Replay position" type="range" min={0} max={Math.max(duration, 1)} value={Math.min(currentTime, Math.max(duration, 1))} onChange={(event) => seek(Number(event.target.value))} className="w-full accent-cyan-400" />{timelineMarkers.map(({ event, offset }) => <button key={event.id} title={labelFor(event)} aria-label={`Seek to ${labelFor(event)}`} onClick={() => selectEvent(event)} className={`absolute top-1/2 h-1.5 w-1.5 -translate-x-1/2 -translate-y-1/2 rounded-full ${isAlertEvent(event) ? "bg-rose-400" : "bg-amber-400"}`} style={{ left: `${Math.min(100, Math.max(0, ((offset ?? 0) / duration) * 100))}%` }} />)}</div>
            <span className="font-mono text-xs text-slate-400">{formatTime(duration)}</span>
            <label className="flex items-center gap-1.5 text-xs text-slate-300">Speed <select aria-label="Playback speed" value={speed} onChange={(event) => setSpeed(Number(event.target.value))} className="rounded border border-slate-700 bg-slate-900 px-2 py-1">{PLAYBACK_SPEEDS.map((value) => <option key={value} value={value}>{value}×</option>)}</select></label>
            <label className="flex items-center gap-1.5 text-xs text-slate-300"><input type="checkbox" checked={skipInactive} onChange={(event) => setSkipInactive(event.target.checked)} className="accent-cyan-400" />Skip inactive</label>
          </div>}
          {playerError && <p role="alert" className="text-xs text-rose-300">{playerError}</p>}
          <p className="text-[12px] text-slate-500">Inputs are masked. PayPal-hosted checkout pages are not included. Each browser tab and recording segment plays independently.</p>

          <section className="overflow-hidden rounded-xl border border-slate-200 bg-white">
            <div className="flex flex-wrap items-center justify-between gap-2 border-b border-slate-200 px-4 py-3">
              <div><h2 className="text-sm font-semibold text-slate-900">Console & network logs</h2><p className="mt-0.5 text-[11px] text-slate-500">Captured signals from this session · select a row to inspect its replay point</p></div>
              <div className="flex rounded-lg border border-slate-300 p-0.5" role="tablist" aria-label="Session signal logs">
                {(["network", "console"] as SignalTab[]).map((value) => <button key={value} type="button" role="tab" aria-selected={signalTab === value} onClick={() => setSignalTab(value)} className={`rounded-md px-3 py-1.5 text-xs capitalize ${signalTab === value ? "bg-blue-100 text-blue-800" : "text-slate-600 hover:bg-slate-50"}`}>{value}</button>)}
              </div>
            </div>
            <AgGridProvider modules={[AllCommunityModule]}><div className="h-[360px] w-full">
              <AgGridReact<SignalGridRow> theme={themeQuartz.withParams({ backgroundColor: "#ffffff", foregroundColor: "#1e293b", headerBackgroundColor: "#f8fafc", headerTextColor: "#475569", borderColor: "#e2e8f0", rowHoverColor: "#eff6ff", fontFamily: "Inter, sans-serif", fontSize: 12, accentColor: "#0b73c2" })} rowData={signalGridRows} columnDefs={signalColumns} defaultColDef={{ sortable: true, filter: true, resizable: true, minWidth: 100 }} getRowId={({ data }) => data.id} rowHeight={42} onRowClicked={({ data }) => { if (data) selectEvent(data); }} overlayNoRowsTemplate={`<span class='ag-overlay-no-rows-center'>No ${signalTab} logs match the current filters</span>`} />
            </div></AgGridProvider>
          </section>
        </section>
        <aside className="flex min-w-0 flex-col rounded-xl border border-slate-800 bg-slate-900/40 p-4 xl:max-h-[calc(100vh-180px)]">
          <h2 className="text-sm font-semibold text-ink">User journey & alerts</h2>
          <p className="mt-1 text-[13px] text-slate-400">{replay?.total_events ?? 0} persisted events · {replay?.rrweb_events ?? 0} replay records · {alertCount} captured alert signals</p>
          <div className="mt-3 grid grid-cols-3 gap-2">
            <div className="rounded-lg border border-slate-800 bg-slate-950/60 p-2"><span className="block text-[10px] uppercase text-slate-500">Journey</span><span className="mt-1 block text-sm font-semibold text-slate-200">{investigationEvents.filter(isJourneyEvent).length}</span></div>
            <div className="rounded-lg border border-slate-800 bg-slate-950/60 p-2"><span className="block text-[10px] uppercase text-slate-500">Network</span><span className="mt-1 block text-sm font-semibold text-slate-200">{investigationEvents.filter((event) => event.category === "network").length}</span></div>
            <div className={`rounded-lg border p-2 ${alertCount ? "border-rose-900/70 bg-rose-950/20" : "border-slate-800 bg-slate-950/60"}`}><span className="block text-[10px] uppercase text-slate-500">Alerts</span><span className={`mt-1 flex items-center gap-1 text-sm font-semibold ${alertCount ? "text-rose-200" : "text-slate-200"}`}>{alertCount > 0 && <AlertTriangle className="h-3.5 w-3.5" />}{alertCount}</span></div>
          </div>
          <div className="mt-3 grid grid-cols-2 gap-2 rounded-lg border border-slate-800 bg-slate-950/60 p-3 text-[12px] text-slate-400">
            <span>Started</span><span className="text-right text-slate-200">{replay?.started_at ? new Date(replay.started_at).toLocaleString() : "Unknown"}</span><span>Selected replay</span><span className="text-right text-slate-200">{formatTime(duration)}</span>
            <span>Viewport</span><span className="text-right text-slate-200">{String((replay?.metadata_redacted?.viewport as Record<string, unknown> | undefined)?.width ?? "Unknown")} × {String((replay?.metadata_redacted?.viewport as Record<string, unknown> | undefined)?.height ?? "Unknown")}</span>
            <span>Screen / DPI</span><span className="text-right text-slate-200">{String((replay?.metadata_redacted?.screen as Record<string, unknown> | undefined)?.width ?? "Unknown")} × {String((replay?.metadata_redacted?.screen as Record<string, unknown> | undefined)?.height ?? "Unknown")} / {String(replay?.metadata_redacted?.device_pixel_ratio ?? "Unknown")}×</span>
            <span>Locale / zone</span><span className="truncate text-right text-slate-200">{String(replay?.metadata_redacted?.locale ?? "Unknown")} · {String(replay?.metadata_redacted?.timezone ?? "Unknown")}</span>
            <span>Platform / browser</span><span className="truncate text-right text-slate-200">{String(replay?.metadata_redacted?.platform ?? "Unknown")} · {String(replay?.metadata_redacted?.browser ?? "Unknown")}</span>
          </div>
          <div className="mt-3 grid grid-cols-2 gap-2"><input aria-label="Search events" placeholder="Search safe event details" value={search} onChange={(event) => setSearch(event.target.value)} className="col-span-2 rounded border border-slate-700 bg-slate-950 px-2 py-1.5 text-[13px] text-slate-200"/><select aria-label="Filter severity" value={severityFilter} onChange={(event) => setSeverityFilter(event.target.value)} className="rounded border border-slate-700 bg-slate-950 px-2 py-1.5 text-[13px] text-slate-200"><option value="all">All severities</option>{["debug", "info", "warn", "error"].map((value) => <option key={value}>{value}</option>)}</select><select aria-label="Filter tab" value={tabFilter} onChange={(event) => setTabFilter(event.target.value)} className="rounded border border-slate-700 bg-slate-950 px-2 py-1.5 text-[13px] text-slate-200"><option value="all">All tabs</option>{tabIds.map((id) => <option key={id} value={id}>{id.slice(0, 12)}</option>)}</select><label className="text-[12px] text-slate-400">From<input aria-label="Events from time" type="datetime-local" value={fromTime} onChange={(event) => setFromTime(event.target.value)} className="mt-1 w-full rounded border border-slate-700 bg-slate-950 p-1 text-slate-200" /></label><label className="text-[12px] text-slate-400">To<input aria-label="Events to time" type="datetime-local" value={toTime} onChange={(event) => setToTime(event.target.value)} className="mt-1 w-full rounded border border-slate-700 bg-slate-950 p-1 text-slate-200" /></label><label className="col-span-2 flex items-center gap-1 text-[12px] text-slate-400"><input type="checkbox" checked={collapseLifecycle} onChange={(event) => setCollapseLifecycle(event.target.checked)} />Collapse nearby repeated lifecycle events</label></div>
          <div className="mt-3 flex gap-1 border-b border-slate-800" role="tablist" aria-label="Journey and alerts">
            {(["journey", "events", "alerts"] as PanelTab[]).map((value) => <button key={value} role="tab" aria-selected={tab === value} onClick={() => setTab(value)} className={`px-2 py-2 text-xs capitalize ${tab === value ? "border-b-2 border-cyan-400 text-cyan-300" : "text-slate-400 hover:text-ink"}`}>{value}{value === "alerts" ? ` (${alertCount})` : ""}</button>)}
          </div>
          {selectedEvent && <div className="mt-3 rounded-lg border border-cyan-800/60 bg-cyan-950/20 p-3 text-[12px] text-slate-300"><p className="font-semibold text-cyan-200">{labelFor(selectedEvent)}</p><p className="mt-1 break-all">{selectedEvent.event_type} · {selectedEvent.category ?? "Unknown category"} · {selectedEvent.severity ?? "info"}</p>{["method", "url", "status", "duration_ms", "started_at", "ended_at", "request_id", "trace_id", "route", "tab_id", "order_id", "redirected", "final_url", "error_name", "error_message", "request_content_type", "response_content_type"].map((key) => detail[key] !== undefined && detail[key] !== null && <p key={key} className="mt-1 break-all"><span className="text-slate-500">{key.replaceAll("_", " ")}: </span>{String(detail[key])}</p>)}{selectedEvent.payment_id && <Link href={`/payments/${selectedEvent.payment_id}`} className="mt-2 inline-block text-cyan-300 hover:underline">Open related payment</Link>}<details className="mt-2"><summary className="cursor-pointer text-slate-400">Safe structured details</summary><pre className="mt-2 max-h-40 overflow-auto whitespace-pre-wrap break-all text-[13px] text-slate-400">{JSON.stringify(detail, null, 2)}</pre></details></div>}
          <div className="mt-3 max-h-[55vh] space-y-2 overflow-y-auto">
            {timelineGroups.length === 0 ? <p className="text-xs text-slate-500">No matching {tab} events are loaded.</p> : timelineGroups.map(({ event, repeats }) => {
              const offset = eventOffset(event, segmentStarts, segmentEnds);
              const unknownOccurrence = event.attributes?.timestamp_source === "ingestion_fallback";
              const when = unknownOccurrence ? null : normalizeOccurrenceTime(event.occurred_at);
              const received = normalizeOccurrenceTime(event.received_at);
              const alert = isAlertEvent(event);
              return <article key={event.id} className={`rounded-lg border bg-slate-950/60 p-3 ${selectedEvent?.id === event.id ? "border-cyan-500/70" : alert ? "border-rose-900/60" : "border-slate-800"}`}>
                <button onClick={() => selectEvent(event)} className="block w-full text-left"><span className="flex items-center justify-between gap-2"><span className={`truncate text-xs font-medium ${alert ? "text-rose-200" : "text-cyan-200"}`}>{alert && <AlertTriangle className="mr-1 inline h-3 w-3" />}{labelFor(event)}</span><span className={`shrink-0 rounded px-1.5 py-0.5 text-[10px] uppercase ${alert ? "bg-rose-950 text-rose-300" : "bg-slate-800 text-slate-400"}`}>{event.category ?? event.event_type}</span></span><span className="mt-1 block font-mono text-[11px] text-slate-500">{when === null ? `Occurrence time unavailable${received !== null ? ` · received ${new Date(received).toLocaleString()}` : ""}` : new Date(when).toLocaleString()} · {offset === null ? "outside replay range" : formatTime(offset)}</span><span className="mt-1 block text-[11px] text-slate-500">Tab {event.tab_id?.slice(0, 12) ?? "unknown"} · {event.severity ?? "info"}</span></button>
                {event.payment_id && <Link href={`/payments/${event.payment_id}`} className="mt-1 block truncate font-mono text-[12px] text-cyan-300 hover:underline">Payment {event.payment_id}</Link>}
                {repeats.length > 1 && <details className="mt-2"><summary className="cursor-pointer text-[12px] text-amber-300">{repeats.length - 1} similar lifecycle event(s) · expand</summary><div className="mt-2 space-y-1">{repeats.slice(1).map((repeat) => <button key={repeat.id} onClick={() => selectEvent(repeat)} className="block w-full truncate text-left font-mono text-[13px] text-slate-400 hover:text-cyan-200">{new Date(repeat.occurred_at).toLocaleString()} · {repeat.id.slice(0, 8)}</button>)}</div></details>}
              </article>;
            })}
          </div>
          {replay?.has_more && <button disabled={loadingMore} onClick={() => void loadMore()} className="mt-3 w-full rounded border border-slate-700 px-3 py-2 text-xs text-cyan-300 disabled:opacity-50">{loadingMore ? "Loading events…" : "Load next 500 events"}</button>}
          <p className="mt-3 border-t border-slate-800 pt-3 text-[12px] leading-relaxed text-slate-500">Request bodies, authorization headers, cookies, credentials, and raw response bodies are not collected. Missing browser-exposed details stay labeled unavailable.</p>
        </aside>
      </div>
    </>}
  </div>;
}
