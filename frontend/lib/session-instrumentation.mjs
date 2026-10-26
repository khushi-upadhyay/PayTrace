import { generateSecureId } from "./session-identity.mjs";

const SENSITIVE_QUERY = /token|auth|secret|password|email|phone|buyer|customer|session|credential|key|code/i;
const SECRET_ASSIGNMENT = /\b(authorization|cookie|set-cookie|access[_-]?token|refresh[_-]?token|token|secret|password|credential|cvv|cvc|card[_-]?number)\s*[:=]\s*(?:bearer\s+)?["']?[^\s,;"']+/gi;

export function sanitizeRequestUrl(value, baseUrl) {
  try {
    const url = new URL(value, baseUrl);
    const parts = url.pathname.split("/");
    const sensitiveIdAfter = new Set(["payments", "sessions", "incidents", "orders", "customers", "buyers"]);
    const path = parts.map((part, index) => {
      if (sensitiveIdAfter.has(parts[index - 1]?.toLowerCase())) return ":id";
      if (/^[0-9a-f]{8}-[0-9a-f-]{27,}$/i.test(part) || /^[a-z0-9_-]{16,}$/i.test(part) || /^[\w.+-]+@[\w.-]+\.[a-z]{2,}$/i.test(part)) return ":id";
      return part;
    }).join("/");
    const query = new URLSearchParams();
    for (const [key, entry] of url.searchParams) {
      if (SENSITIVE_QUERY.test(key)) continue;
      else if (["limit", "offset", "page", "page_size"].includes(key)) query.set(key, entry);
    }
    return `${url.origin}${path}${query.size ? `?${query}` : ""}`;
  } catch { return "unavailable"; }
}

export function sanitizeLogText(value) {
  return String(value ?? "")
    .replace(/https?:\/\/\S+/gi, "[URL]")
    .replace(/[\w.+-]+@[\w.-]+\.[a-z]{2,}/gi, "[EMAIL]")
    .replace(SECRET_ASSIGNMENT, "$1=[REDACTED]")
    .replace(/\b(?:\d[ -]*?){13,19}\b/g, "[REDACTED_CARD]")
    .replace(/\+?\d[\d\s().-]{7,}\d/g, "[REDACTED_NUMBER]")
    .slice(0, 240);
}

export function sanitizeRrwebEvent(event, baseUrl) {
  const urlFields = new Set(["href", "src", "action", "formaction", "url"]);
  const sensitiveField = /authorization|token|secret|password|credential|cookie|card|cvv|cvc|email|phone|buyer/i;
  const visit = (value, key = "") => {
    if (typeof value === "string") {
      if (sensitiveField.test(key)) return "[REDACTED]";
      if (urlFields.has(key.toLowerCase())) {
        if (/^(data|blob|javascript):/i.test(value)) return "[REDACTED_URL]";
        return sanitizeRequestUrl(value, baseUrl);
      }
      return sanitizeLogText(value);
    }
    if (Array.isArray(value)) return value.map((entry) => visit(entry, key));
    if (value && typeof value === "object") return Object.fromEntries(Object.entries(value).map(([childKey, entry]) => [childKey, visit(entry, childKey)]));
    return value;
  };
  return visit(event);
}

const SENSITIVE_FIELD = /authorization|token|secret|password|credential|cookie|card|cvv|cvc|email|phone|buyer/i;
function safeValue(value, depth = 0, seen = new WeakSet()) {
  if (value === null || ["string", "number", "boolean"].includes(typeof value)) return typeof value === "string" ? sanitizeLogText(value).slice(0, 240) : value;
  if (typeof value !== "object") return `[${typeof value}]`;
  if (seen.has(value)) return "[Circular]";
  if (value instanceof Error) return { name: value.name, message: sanitizeLogText(value.message), stack: value.stack ? sanitizeLogText(value.stack).slice(0, 1000) : undefined };
  if (depth >= 3) return `[${Array.isArray(value) ? "Array" : value?.constructor?.name ?? "Object"}]`;
  seen.add(value);
  if (Array.isArray(value)) return value.slice(0, 8).map((entry) => safeValue(entry, depth + 1, seen));
  const entries = Object.entries(value).slice(0, 20).map(([key, entry]) => [key.slice(0, 80), SENSITIVE_FIELD.test(key) ? "[REDACTED]" : safeValue(entry, depth + 1, seen)]);
  return Object.fromEntries(entries);
}

function requestId() { return generateSecureId(); }
function firstParty(url, origins) { try { return origins.has(new URL(url).origin); } catch { return false; } }
function shouldIgnore(url, sessionId) {
  try { return !!sessionId && new URL(url).pathname === `/api/v1/sessions/${sessionId}/events`; } catch { return false; }
}
function correlations(url) {
  try {
    const parts = new URL(url).pathname.split("/").filter(Boolean);
    const paymentIndex = parts.indexOf("payments");
    const orderIndex = parts.indexOf("orders");
    return {
      ...(paymentIndex >= 0 && parts[paymentIndex + 1] ? { payment_id: parts[paymentIndex + 1] } : {}),
      ...(orderIndex >= 0 && parts[orderIndex + 1] ? { order_id: parts[orderIndex + 1] } : {}),
    };
  } catch { return {}; }
}
function outcomeForError(error) {
  if (error?.name === "AbortError") return "aborted";
  if (error?.name === "TimeoutError") return "timeout";
  return "network_error";
}
function contentType(headers) {
  try {
    if (headers && typeof headers.get === "function") return headers.get("content-type") ?? "unavailable";
    if (Array.isArray(headers)) return headers.find((entry) => Array.isArray(entry) && String(entry[0]).toLowerCase() === "content-type")?.[1] ?? "unavailable";
  } catch { /* Request metadata must not affect the request. */ }
  return "unavailable";
}

export function instrumentNetwork({ target = globalThis, apiBaseUrl, context, emit }) {
  const originalFetch = target.fetch;
  const xhrPrototype = target.XMLHttpRequest?.prototype;
  const originalOpen = xhrPrototype?.open;
  const originalSend = xhrPrototype?.send;
  const originalSetRequestHeader = xhrPrototype?.setRequestHeader;
  const origins = new Set();
  try { origins.add(new URL(apiBaseUrl, target.location?.href).origin); } catch { /* API origin unavailable */ }
  try { origins.add(target.location.origin); } catch { /* page origin unavailable */ }

  const emitRequest = (details) => {
    try {
      emit({
        ...context(),
        id: requestId(),
        trace_id: details.request_id,
        event_type: "network",
        category: "network",
        source: "browser",
        occurred_at: details.started_at,
        severity: details.outcome === "success" ? "info" : "error",
        attributes: details,
        payment_id: details.payment_id ?? null,
        order_id: details.order_id ?? null,
        payload: { name: `${details.method} ${details.url}`, ...details },
      });
    } catch { /* Telemetry must not change request behavior. */ }
  };

  if (typeof originalFetch === "function") {
    target.fetch = async function instrumentedFetch(input, init) {
      let url = "unavailable";
      let method = "unavailable";
      let requestUrl = "";
      let requestHeadersForMetadata;
      try {
        const request = target.Request && input instanceof target.Request ? input : null;
        requestHeadersForMetadata = request?.headers;
        const rawUrl = request ? request.url : String(input);
        const absolute = new URL(rawUrl, target.location?.href);
        requestUrl = absolute.href;
        if (!origins.has(absolute.origin) || shouldIgnore(absolute.href, context().session_id)) return Reflect.apply(originalFetch, this, arguments);
        url = sanitizeRequestUrl(absolute.href, target.location?.href);
        method = String(init?.method ?? request?.method ?? "GET").toUpperCase();
      } catch { return Reflect.apply(originalFetch, this, arguments); }
      const started = Date.now();
      const startedAt = new Date(started).toISOString();
      const id = requestId();
      try {
        const response = await Reflect.apply(originalFetch, this, arguments);
        const requestContentType = contentType(init?.headers ?? requestHeadersForMetadata);
        let responseContentType = "unavailable";
        try { responseContentType = response.headers?.get("content-type") ?? "unavailable"; } catch { /* Telemetry must not change request behavior. */ }
        let finalUrl = "unavailable";
        try { if (response.url) finalUrl = sanitizeRequestUrl(response.url, target.location?.href); } catch { /* The response URL is optional metadata. */ }
        emitRequest({ request_id: id, ...correlations(requestUrl), method, url, started_at: startedAt, ended_at: new Date().toISOString(), duration_ms: Date.now() - started, status: response.status, outcome: response.ok ? "success" : "http_error", redirected: response.redirected, final_url: finalUrl, request_content_type: requestContentType, response_content_type: responseContentType });
        return response;
      } catch (error) {
        emitRequest({ request_id: id, ...correlations(requestUrl), method, url, started_at: startedAt, ended_at: new Date().toISOString(), duration_ms: Date.now() - started, status: null, outcome: outcomeForError(error), error_name: error?.name ?? "unavailable", error_message: sanitizeLogText(error?.message ?? "unavailable") });
        throw error;
      }
    };
  }

  const xhrRequests = new WeakMap();
  if (xhrPrototype && originalOpen && originalSend) {
    xhrPrototype.open = function instrumentedOpen(method, url, ...rest) {
      try {
        const requestUrl = new URL(String(url), target.location?.href).href;
        xhrRequests.set(this, { method: String(method ?? "unavailable").toUpperCase(), requestUrl });
      } catch { xhrRequests.delete(this); }
      return Reflect.apply(originalOpen, this, [method, url, ...rest]);
    };
    xhrPrototype.send = function instrumentedSend(...args) {
      const request = xhrRequests.get(this);
      if (!request || !firstParty(request.requestUrl, origins) || shouldIgnore(request.requestUrl, context().session_id)) return Reflect.apply(originalSend, this, args);
      const started = Date.now();
      const startedAt = new Date(started).toISOString();
      const id = requestId();
      let emitted = false;
      const finish = (outcome) => {
        if (emitted) return;
        emitted = true;
        let responseContentType = "unavailable";
        try { responseContentType = this.getResponseHeader("content-type") ?? "unavailable"; } catch { /* CORS may hide response metadata. */ }
        emitRequest({ request_id: id, ...correlations(request.requestUrl), method: request.method, url: sanitizeRequestUrl(request.requestUrl, target.location?.href), started_at: startedAt, ended_at: new Date().toISOString(), duration_ms: Date.now() - started, status: typeof this.status === "number" && this.status > 0 ? this.status : null, outcome, request_content_type: request.contentType ?? "unavailable", response_content_type: responseContentType, error_name: outcome === "success" || outcome === "http_error" ? undefined : outcome });
      };
      this.addEventListener("loadend", () => finish(this.status === 0 ? "network_error" : this.status >= 400 ? "http_error" : "success"), { once: true });
      this.addEventListener("error", () => finish("network_error"), { once: true });
      this.addEventListener("abort", () => finish("aborted"), { once: true });
      this.addEventListener("timeout", () => finish("timeout"), { once: true });
      try { return Reflect.apply(originalSend, this, args); }
      catch (error) { finish("network_error"); throw error; }
    };
    if (originalSetRequestHeader) {
      xhrPrototype.setRequestHeader = function instrumentedSetRequestHeader(name, value) {
        if (String(name).toLowerCase() === "content-type") {
          const request = xhrRequests.get(this);
          if (request) request.contentType = sanitizeLogText(value).slice(0, 120);
        }
        return Reflect.apply(originalSetRequestHeader, this, arguments);
      };
    }
  }

  return () => {
    if (target.fetch !== originalFetch && originalFetch) target.fetch = originalFetch;
    if (xhrPrototype && xhrPrototype.open !== originalOpen) xhrPrototype.open = originalOpen;
    if (xhrPrototype && xhrPrototype.send !== originalSend) xhrPrototype.send = originalSend;
    if (xhrPrototype && originalSetRequestHeader && xhrPrototype.setRequestHeader !== originalSetRequestHeader) xhrPrototype.setRequestHeader = originalSetRequestHeader;
  };
}

export function instrumentConsole({ target = globalThis.console, context, emit }) {
  const methods = ["debug", "info", "warn", "error"];
  const originals = new Map(methods.map((method) => [method, target[method]]));
  for (const level of methods) {
    const original = originals.get(level);
    if (typeof original !== "function") continue;
    target[level] = function instrumentedConsole(...args) {
      try {
        const error = args.find((arg) => arg instanceof Error);
        emit({ ...context(), id: requestId(), event_type: "console", category: "console", source: "browser", occurred_at: new Date().toISOString(), severity: level, attributes: { args: args.slice(0, 8).map((value) => safeValue(value)), ...(error ? { error_name: error.name, stack: error.stack ? sanitizeLogText(error.stack).slice(0, 1000) : undefined } : {}) }, payload: { level, message: args.map((arg) => typeof arg === "string" ? sanitizeLogText(arg) : `[${Array.isArray(arg) ? "Array" : arg?.constructor?.name ?? typeof arg}]`).join(" ").slice(0, 500) } });
      } catch { /* Console must remain usable even when telemetry fails. */ }
      return Reflect.apply(original, this, args);
    };
  }
  return () => { for (const method of methods) target[method] = originals.get(method); };
}
