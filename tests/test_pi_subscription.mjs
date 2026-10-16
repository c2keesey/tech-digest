import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { runRequest, PiFailure, PROVIDER, MODEL, API, BASE_URL,
  MAX_INPUT_BYTES, MAX_OUTPUT_BYTES, MAX_STREAM_BYTES } from "../scripts/pi_subscription.mjs";

const request = { prompt: "public fixture", system_prompt: "Return bounded JSON", structured: true, timeout: 5 };
const result = () => ({ role: "assistant", provider: PROVIDER, model: MODEL, api: API,
  stopReason: "stop", content: [{ type: "text", text: '{"fixture":true}' }] });

function fakeSdk(overrides = {}) {
  const seen = { creates: 0, streams: 0, models: [] };
  const runtime = {
    getProvider: () => ({ baseUrl: BASE_URL, auth: { oauth: { isSubscription: true } } }),
    checkAuth: async () => ({ type: "oauth" }),
    refresh: async (options) => { seen.refresh = options; return { aborted: false, errors: new Map() }; },
    getModel: (provider, id) => {
      seen.models.push([provider, id]);
      return { provider, id, api: API, baseUrl: BASE_URL };
    },
    streamSimple(model, context, options) {
      seen.streams++;
      Object.assign(seen, { model, context, options });
      const body = { model: model.id, store: false, text: {} };
      seen.payload = options.onPayload(body, model);
      return {
        async *[Symbol.asyncIterator]() { yield { type: "text_delta", delta: "public" }; },
        result: async () => result(),
      };
    },
    ...overrides,
  };
  const sdk = { getAgentDir: () => "/existing/service-pi",
    ModelRuntime: { create: async (options) => {
      seen.creates++;
      seen.createOptions = options;
      return runtime;
    } } };
  return { sdk, runtime, seen };
}

const rejects = (promise, code) => assert.rejects(promise, (error) => error instanceof PiFailure && error.message === code);

test("one explicit subscription model, no tools/sessions, strict structured payload", async () => {
  const { sdk, seen } = fakeSdk();
  const output = await runRequest(request, sdk);
  assert.deepEqual({ provider: output.provider, model: output.model, api: output.api, auth: output.auth },
    { provider: PROVIDER, model: MODEL, api: API, auth: "subscription-oauth" });
  assert.deepEqual(seen.models, [[PROVIDER, MODEL]]);
  assert.deepEqual(seen.context.tools, []);
  assert.equal(seen.context.messages.length, 1);
  assert.equal(seen.options.reasoning, "low");
  assert.equal(seen.options.maxRetries, 0);
  assert.equal(seen.options.transport, "sse");
  assert.equal(seen.payload.store, false);
  assert.equal(seen.payload.tool_choice, "none");
  assert.equal(seen.payload.text.format.type, "json_schema");
  assert.equal(seen.payload.text.format.strict, true);
  assert.equal(seen.payload.text.format.schema.additionalProperties, false);
  assert.equal(seen.payload.text.format.schema.properties.summary.maxLength, 350);
  assert.equal(seen.options.signal.aborted, true, "request resources cancelled after completion");
  assert.equal(seen.createOptions.allowModelNetwork, false);
  assert.equal(seen.createOptions.refreshOnCreate, false);
  assert.equal(seen.createOptions.modelsStorePath, "/existing/service-pi/models-store.json");
  assert.deepEqual(JSON.parse(readFileSync(seen.createOptions.modelsPath)), { providers: {} });
  assert.deepEqual(seen.refresh.providers, [PROVIDER]);
  assert.equal(seen.refresh.allowNetwork, false);
});

test("missing OAuth or an API-key credential fails before inference", async () => {
  for (const auth of [undefined, { type: "api_key" }]) {
    const { sdk, seen } = fakeSdk({ checkAuth: async () => auth });
    await rejects(runRequest(request, sdk), "pi-subscription-required");
    assert.equal(seen.streams, 0);
    assert.deepEqual(seen.models, []);
  }
});

test("provider with paid/API-key auth or wrong endpoint is rejected", async () => {
  for (const provider of [
    { baseUrl: BASE_URL, auth: { oauth: { isSubscription: true }, apiKey: {} } },
    { baseUrl: "https://api.openai.com/v1", auth: { oauth: { isSubscription: true } } },
    { baseUrl: BASE_URL, auth: { oauth: { isSubscription: false } } },
  ]) {
    const { sdk, seen } = fakeSdk({ getProvider: () => provider });
    await rejects(runRequest(request, sdk), "pi-provider-mismatch");
    assert.equal(seen.streams, 0);
  }
});

test("model unavailable means no fuzzy/default/paid fallback", async () => {
  const { sdk, seen } = fakeSdk({ getModel: () => undefined });
  await rejects(runRequest(request, sdk), "pi-model-unavailable");
  assert.equal(seen.streams, 0);
});

test("wrong model ID, provider, API or endpoint cannot dispatch", async () => {
  for (const invalid of [{ id: "gpt-5.4" }, { provider: "openai" },
                          { api: "openai-responses" }, { baseUrl: "https://api.openai.com/v1" }]) {
    const { sdk, seen } = fakeSdk({ getModel: () => ({ id: MODEL, provider: PROVIDER, api: API, baseUrl: BASE_URL, ...invalid }) });
    await rejects(runRequest(request, sdk), "pi-provider-mismatch");
    assert.equal(seen.streams, 0);
  }
});

test("advisory uses same subscription with no structured schema or tools", async () => {
  const { sdk, seen } = fakeSdk();
  await runRequest({ ...request, structured: false }, sdk);
  assert.equal(seen.payload.text.format, undefined);
  assert.deepEqual(seen.context.tools, []);
  assert.equal(seen.streams, 1);
});

test("untrusted API-key/provider/model input and timeout range rejected before startup", async () => {
  for (const invalid of [null, { api_key: "fake-secret" }, { provider: "openai" },
                          { model: "gpt-5.4" }, { timeout: 0 }, { timeout: 121 }, { prompt: "" }]) {
    const { sdk, seen } = fakeSdk();
    await rejects(runRequest(invalid === null ? null : { ...request, ...invalid }, sdk), "pi-invalid-request");
    assert.equal(seen.creates, 0);
  }
});

test("observed 128KB release batch fits without truncating any release", async () => {
  const { sdk, seen } = fakeSdk();
  const prompt = "x".repeat(128 * 1024);
  await runRequest({ ...request, prompt }, sdk);
  assert.equal(seen.context.messages[0].content, prompt);
  assert.equal(seen.streams, 1);
});

test("oversized input is not truncated or sent", async () => {
  const { sdk, seen } = fakeSdk();
  await rejects(runRequest({ ...request, prompt: "x".repeat(MAX_INPUT_BYTES) }, sdk), "pi-input-too-large");
  assert.equal(seen.creates, 0);
});

test("quota/network/provider failures have no fallback and no raw diagnostic", async () => {
  const { sdk, seen } = fakeSdk();
  seen.streams = 0;
  sdk.ModelRuntime.create = async () => ({
    getProvider: () => ({ baseUrl: BASE_URL, auth: { oauth: { isSubscription: true } } }),
    checkAuth: async () => ({ type: "oauth" }), refresh: async () => ({ aborted: false }),
    getModel: () => ({ id: MODEL, provider: PROVIDER, api: API, baseUrl: BASE_URL }),
    streamSimple: () => { seen.streams++; throw new Error("fake-secret private account usage limit"); },
  });
  await rejects(runRequest(request, sdk), "pi-provider-failed");
  assert.equal(seen.streams, 1);
});

function streamingSdk(events, message, seen = {}) {
  return fakeSdk({ streamSimple(model, context, options) {
    seen.signal = options.signal;
    return {
      async *[Symbol.asyncIterator]() { for (const event of events) yield event; },
      result: async () => message,
    };
  } }).sdk;
}

test("oversized thinking stream aborts instead of growing output unbounded", async () => {
  const seen = {};
  const sdk = streamingSdk([{ type: "thinking_delta", delta: "x".repeat(MAX_STREAM_BYTES + 1) }], result(), seen);
  await rejects(runRequest(request, sdk), "pi-output-too-large");
  assert.equal(seen.signal.aborted, true);
});

test("oversized final text rejected", async () => {
  const message = { ...result(), content: [{ type: "text", text: "x".repeat(MAX_OUTPUT_BYTES + 1) }] };
  await rejects(runRequest(request, streamingSdk([], message)), "pi-output-too-large");
});

test("truncated/error/foreign-model/tool-call responses fail closed", async () => {
  for (const invalid of [{ stopReason: "length" }, { provider: "openai" }, { model: "gpt-5.4" },
                         { api: "openai-responses" }, { content: [] },
                         { content: [{ type: "toolCall", name: "bash" }] }]) {
    await rejects(runRequest(request, streamingSdk([], { ...result(), ...invalid })), "pi-invalid-result");
  }
  await rejects(runRequest(request, streamingSdk([], { ...result(), stopReason: "error", errorMessage: "fake-secret" })), "pi-provider-failed");
  await rejects(runRequest(request, streamingSdk([{ type: "toolcall_start" }], result())), "pi-invalid-result");
});

test("hard deadline rejects a delayed stream and cancels resources", async () => {
  let signal;
  const { sdk } = fakeSdk({ streamSimple(model, context, options) {
    signal = options.signal;
    return {
      async *[Symbol.asyncIterator]() {
        await new Promise((resolve) => setTimeout(resolve, 1050));
        yield { type: "text_delta", delta: "late" };
      }, result: async () => result(),
    };
  } });
  await rejects(runRequest({ ...request, timeout: 1 }, sdk), "pi-timeout");
  assert.equal(signal.aborted, true);
});
