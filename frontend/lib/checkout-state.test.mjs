import test from "node:test";
import assert from "node:assert/strict";
import {
  beginOrderRequest,
  captureOutcomeMayBeUnknown,
  classifyFetchFailure,
  clearCheckoutOnCancellation,
  resolvePayPalReturnOrder,
  withCheckoutLoading,
} from "./checkout-state.mjs";

test("checkout loading clears after successful capture", async () => {
  const states = [];
  const result = await withCheckoutLoading(async () => "CAPTURED", (value) => states.push(value));
  assert.equal(result, "CAPTURED");
  assert.deepEqual(states, [true, false]);
});

test("checkout loading clears after provider failure", async () => {
  const states = [];
  await assert.rejects(
    withCheckoutLoading(async () => { throw new Error("provider unavailable"); }, (value) => states.push(value)),
    /provider unavailable/
  );
  assert.deepEqual(states, [true, false]);
});

test("checkout loading clears after request timeout", async () => {
  const states = [];
  await assert.rejects(
    withCheckoutLoading(() => new Promise((_, reject) => setTimeout(() => reject(new Error("timeout")), 1)), (value) => states.push(value)),
    /timeout/
  );
  assert.deepEqual(states, [true, false]);
});

test("PayPal cancellation clears all loading states and pending order", () => {
  const state = { processing: true, verifying: true, waitingApproval: true, removed: false };
  clearCheckoutOnCancellation({
    setProcessing: (value) => { state.processing = value; },
    setVerifying: (value) => { state.verifying = value; },
    setWaitingApproval: (value) => { state.waitingApproval = value; },
    removePending: () => { state.removed = true; },
  });
  assert.deepEqual(state, { processing: false, verifying: false, waitingApproval: false, removed: true });
});


test("capture timeout, abort, connection/CORS and backend HTTP errors stay distinct", () => {
  const timeout = classifyFetchFailure(Object.assign(new Error("signal timed out"), { name: "TimeoutError" }));
  const aborted = classifyFetchFailure(Object.assign(new Error("cancelled"), { name: "AbortError" }));
  const network = classifyFetchFailure(new TypeError("fetch failed"));
  assert.equal(timeout.kind, "timeout");
  assert.equal(aborted.kind, "aborted");
  assert.equal(network.kind, "network_or_cors");
  assert.equal(captureOutcomeMayBeUnknown({ kind: "timeout", status: 0 }), true);
  assert.equal(captureOutcomeMayBeUnknown({ kind: "aborted", status: 0 }), true);
  assert.equal(captureOutcomeMayBeUnknown({ kind: "http", status: 504 }), true);
  assert.equal(captureOutcomeMayBeUnknown({ kind: "http", status: 422 }), false);
});

test("duplicate clicks admit only the first in-flight request for an order", () => {
  const inFlight = new Set();
  assert.equal(beginOrderRequest(inFlight, "ORDER-1"), true);
  assert.equal(beginOrderRequest(inFlight, "ORDER-1"), false);
  assert.equal(beginOrderRequest(inFlight, "ORDER-2"), true);
});

test("stale PayPal return token cannot replace the pending order", () => {
  assert.deepEqual(
    resolvePayPalReturnOrder("ORDER-OLD", "ORDER-NEW", "ORDER-NEW"),
    { orderId: null, mismatch: true }
  );
  assert.deepEqual(
    resolvePayPalReturnOrder("ORDER-NEW", null, "ORDER-NEW"),
    { orderId: "ORDER-NEW", mismatch: false }
  );
});


test("loading state also clears after an explicit abort", async () => {
  const states = [];
  await assert.rejects(
    withCheckoutLoading(
      async () => { throw Object.assign(new Error("request cancelled"), { name: "AbortError" }); },
      (value) => states.push(value)
    ),
    /request cancelled/
  );
  assert.deepEqual(states, [true, false]);
});


test("a finished uncertain attempt releases the order lock for safe retry", () => {
  const inFlight = new Set();
  assert.equal(beginOrderRequest(inFlight, "ORDER-RETRY"), true);
  inFlight.delete("ORDER-RETRY");
  assert.equal(beginOrderRequest(inFlight, "ORDER-RETRY"), true);
});
