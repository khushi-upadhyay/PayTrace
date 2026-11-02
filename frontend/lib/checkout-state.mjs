/**
 * Helper state machine logic for managing in-flight checkout actions, network failures,
 * and PayPal return token resolution. Pure JavaScript (ESM).
 */

export function classifyFetchFailure(err) {
  if (err && typeof err === "object") {
    const errorObj = err;
    const name = typeof errorObj.name === "string" ? errorObj.name.toLowerCase() : "";
    const msg = typeof errorObj.message === "string" ? errorObj.message.toLowerCase() : "";

    if (name === "aborterror" || msg.includes("aborted")) {
      return { kind: "aborted", message: "Request was aborted" };
    }
    if (name === "timeouterror" || msg.includes("timeout") || msg.includes("timed out")) {
      return { kind: "timeout", message: "Request timed out" };
    }
    if (msg.includes("failed to fetch") || msg.includes("network error") || msg.includes("cors")) {
      return { kind: "network_or_cors", message: "Network connection or CORS error" };
    }
  }

  return {
    kind: "network_or_cors",
    message: err && err.message ? String(err.message) : "Network error during payment processing",
  };
}

export function beginOrderRequest(inFlightOrders, orderId) {
  if (inFlightOrders.has(orderId)) {
    return false;
  }
  inFlightOrders.add(orderId);
  return true;
}

export function resolvePayPalReturnOrder(tokenParam, activeOrderId, storedOrderId) {
  const returnOrderId = tokenParam || activeOrderId || storedOrderId || null;
  if (!returnOrderId) {
    return { orderId: null, mismatch: false };
  }

  const mismatch = Boolean(
    (tokenParam && activeOrderId && tokenParam !== activeOrderId) ||
    (tokenParam && storedOrderId && tokenParam !== storedOrderId)
  );

  return { orderId: mismatch ? null : returnOrderId, mismatch };
}

export function clearCheckoutOnCancellation(callbacks) {
  if (callbacks.setProcessing) callbacks.setProcessing(false);
  if (callbacks.setVerifying) callbacks.setVerifying(false);
  if (callbacks.setWaitingApproval) callbacks.setWaitingApproval(false);
  if (callbacks.removePending) callbacks.removePending();
}

export async function withCheckoutLoading(fn, setProcessing) {
  setProcessing(true);
  try {
    return await fn();
  } finally {
    setProcessing(false);
  }
}

export function captureOutcomeMayBeUnknown(err) {
  if (!err) return false;
  if (err.kind === "timeout" || err.kind === "aborted" || err.kind === "network_or_cors" || err.kind === "network") {
    return true;
  }
  if (typeof err.status === "number" && (err.status === 408 || err.status === 504 || err.status === 0)) {
    return true;
  }
  const msg = String(err.message || "").toLowerCase();
  return (
    msg.includes("timeout") ||
    msg.includes("timed out") ||
    msg.includes("network") ||
    msg.includes("failed to fetch")
  );
}
