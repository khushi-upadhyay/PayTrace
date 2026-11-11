import test from "node:test";
import assert from "node:assert/strict";
import { instrumentConsole, instrumentNetwork, sanitizeLogText, sanitizeRequestUrl, sanitizeRrwebEvent } from "./session-instrumentation.mjs";

test("sanitizes request paths, sensitive query values, and console secrets", () => {
  assert.equal(sanitizeRequestUrl("https://api.paytrace.test/api/v1/payments/632dad74-055c-43bf-9651-55bf6ea953bf?access_token=private&limit=20", "https://app.paytrace.test"), "https://api.paytrace.test/api/v1/payments/:id?limit=20");
  assert.equal(sanitizeLogText("authorization: Bearer abc123 password=hunter2"), "authorization=[REDACTED] password=[REDACTED]");
});

test("rrweb URL attributes and text are redacted before persistence", () => {
  const event = sanitizeRrwebEvent({ type: 4, data: { href: "https://app.test/checkout?access_token=secret&campaign=spring", node: { textContent: "Contact alice@example.test at https://app.test/reset?token=hidden" }, form: { password: "secret-value" }, image: { src: "data:image/png;base64,private" } } }, "https://app.test/checkout");
  assert.equal(event.data.href, "https://app.test/checkout");
  assert.match(event.data.node.textContent, /\[EMAIL\]/);
  assert.doesNotMatch(JSON.stringify(event), /secret-value|alice@example\.test|access_token=secret|token=hidden|base64,private/);
  assert.equal(event.data.form.password, "[REDACTED]");
  assert.equal(event.data.image.src, "[REDACTED_URL]");
});

test("inlined stylesheet text is preserved untruncated for replay fidelity", () => {
  const longCssText = `:root { --slate-400: 71 85 105; --slate-500: 100 116 139; }${"\n.util { color: red; }".repeat(50)}`;
  const event = sanitizeRrwebEvent({ type: 2, attributes: { _cssText: longCssText } }, "https://app.test/checkout");
  assert.equal(event.attributes._cssText, longCssText);
});

test("fetch instrumentation records real request details once and omits upload traffic", async () => {
  const events = [];
  const target = {
    location: { origin: "https://app.paytrace.test", href: "https://app.paytrace.test/checkout" },
    fetch: async (input) => ({ status: 201, ok: true, redirected: false, url: String(input), headers: { get: () => "application/json" } }),
  };
  const original = target.fetch;
  const restore = instrumentNetwork({ target, apiBaseUrl: "https://api.paytrace.test", context: () => ({ session_id: "session-1", tab_id: "tab-1" }), emit: (event) => events.push(event) });
  const response = await target.fetch("https://api.paytrace.test/api/v1/paypal/orders?buyer_email=secret", { method: "POST", headers: { "content-type": "application/json" } });
  assert.equal(response.status, 201);
  await target.fetch("https://api.paytrace.test/api/v1/sessions/session-1/events", { method: "POST" });
  assert.equal(events.length, 1);
  assert.equal(events[0].attributes.method, "POST");
  assert.doesNotMatch(events[0].attributes.url, /buyer_email|secret/);
  assert.equal(events[0].attributes.status, 201);
  assert.equal(events[0].tab_id, "tab-1");
  restore();
  assert.equal(target.fetch, original);
});

test("fetch failures distinguish abort from timeout and preserve thrown errors", async () => {
  const events = [];
  const error = Object.assign(new Error("request aborted"), { name: "AbortError" });
  const target = { location: { origin: "https://app.test", href: "https://app.test/" }, fetch: async () => { throw error; } };
  const restore = instrumentNetwork({ target, apiBaseUrl: "https://app.test", context: () => ({}), emit: (event) => events.push(event) });
  await assert.rejects(target.fetch("/api/v1/paypal/orders"), error);
  assert.equal(events[0].attributes.outcome, "aborted");
  restore();
});

test("XMLHttpRequest captures safe request metadata and restores wrapped methods", () => {
  class MockXHR {
    status = 204;
    listeners = new Map();
    open(method, url) { this.method = method; this.url = url; }
    setRequestHeader() {}
    send() { for (const listener of this.listeners.get("loadend") ?? []) listener.call(this); }
    addEventListener(name, listener) { this.listeners.set(name, [...(this.listeners.get(name) ?? []), listener]); }
    getResponseHeader() { return "application/json"; }
  }
  const originalOpen = MockXHR.prototype.open;
  const originalSend = MockXHR.prototype.send;
  const events = [];
  const target = { location: { origin: "https://app.test", href: "https://app.test/" }, XMLHttpRequest: MockXHR };
  const restore = instrumentNetwork({ target, apiBaseUrl: "https://app.test", context: () => ({ tab_id: "tab-x" }), emit: (event) => events.push(event) });
  const xhr = new MockXHR();
  xhr.open("POST", "/api/v1/paypal/orders/19F21486TU6821704/capture");
  xhr.setRequestHeader("Content-Type", "application/json");
  xhr.send("ignored request body");
  assert.equal(events.length, 1);
  assert.equal(events[0].order_id, "19F21486TU6821704");
  assert.equal(events[0].attributes.method, "POST");
  assert.equal(events[0].attributes.request_content_type, "application/json");
  assert.equal(events[0].attributes.response_content_type, "application/json");
  assert.equal(events[0].attributes.url, "https://app.test/api/v1/paypal/orders/:id/capture");
  restore();
  assert.equal(MockXHR.prototype.open, originalOpen);
  assert.equal(MockXHR.prototype.send, originalSend);
});

test("console instrumentation captures safe levels and restores original methods", () => {
  const events = [];
  const calls = [];
  const target = Object.fromEntries(["debug", "info", "warn", "error"].map((level) => [level, (...args) => calls.push([level, ...args])]));
  const original = target.warn;
  const restore = instrumentConsole({ target, context: () => ({ tab_id: "tab-1" }), emit: (event) => events.push(event) });
  target.warn("password=hunter2", { arbitrary: "object", authorization: "Bearer abc123", email: "alice@example.test" });
  assert.equal(events.length, 1);
  assert.match(events[0].payload.message, /password=\[REDACTED\]/);
  assert.equal(events[0].attributes.args[1].authorization, "[REDACTED]");
  assert.equal(events[0].attributes.args[1].email, "[REDACTED]");
  assert.equal(calls[0][0], "warn");
  restore();
  assert.equal(target.warn, original);
});

test("rrweb sanitising keeps SVG geometry and long attribute values intact", () => {
  const path = "M423.5 12.25 L244.75 154.5 C573.111,221,543.9 10 20 30 ".repeat(8);
  const classes = "flex items-center gap-2 rounded-xl border px-3 py-2 ".repeat(8);
  const event = sanitizeRrwebEvent({ type: 2, attributes: { d: path, viewBox: "0 0 24 24", x1: "423.5", class: classes } }, "https://app.test/");
  assert.equal(event.attributes.d, path);
  assert.equal(event.attributes.viewBox, "0 0 24 24");
  assert.equal(event.attributes.x1, "423.5");
  assert.equal(event.attributes.class, classes);
  assert.match(sanitizeRrwebEvent({ text: "Call +1 (415) 555-0199 now" }, "https://app.test/").text, /REDACTED_NUMBER/);
});
