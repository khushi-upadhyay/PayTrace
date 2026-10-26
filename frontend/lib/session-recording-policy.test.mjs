import test from "node:test";
import assert from "node:assert/strict";
import { shouldStartSessionRecording } from "./session-recording-policy.mjs";

test("session recording starts by default", () => {
  assert.equal(shouldStartSessionRecording(null), true);
  assert.equal(shouldStartSessionRecording("enabled"), true);
});

test("an explicit stop keeps session recording disabled", () => {
  assert.equal(shouldStartSessionRecording("disabled"), false);
});
