#!/usr/bin/env node
/** One bounded call through Pi's public ModelRuntime API; no agent/resources/tools.
 * Uses the existing service user's Pi OAuth store in place. Never accepts keys,
 * alternate providers/models, paid fallback, or user model/provider overrides.
 */
import { fileURLToPath, pathToFileURL } from "node:url";
import { dirname, resolve, join } from "node:path";

export const PROVIDER = "openai-codex";
export const MODEL = "gpt-6.1-sol";
export const API = "openai-codex-responses";
export const BASE_URL = "https://chatgpt.com/backend-api";
export const MAX_INPUT_BYTES = 192 * 1024;
export const MAX_OUTPUT_BYTES = 16 * 1024;
export const MAX_STREAM_BYTES = 64 * 1024;
export const MAX_REQUEST_BYTES = 256 * 1024;
const here = dirname(fileURLToPath(import.meta.url));
const ERROR_CODES = new Set([
  "pi-invalid-request", "pi-input-too-large", "pi-runtime-unavailable",
  "pi-subscription-required", "pi-model-unavailable", "pi-provider-mismatch",
  "pi-timeout", "pi-output-too-large", "pi-invalid-result", "pi-provider-failed",
]);

export class PiFailure extends Error {}
const fail = (code) => { throw new PiFailure(code); };

// Structured output is enforced by the Codex Responses payload AND Python
// validation. Empty categories are allowed; top-level fields are always present.
const items = (length, count) => ({ type: "array", maxItems: count,
  items: { type: "string", minLength: 1, maxLength: length } });
export const RELEASE_SCHEMA = {
  type: "object", additionalProperties: false,
  required: ["summary", "try_this", "categories"],
  properties: {
    summary: { type: "string", minLength: 1, maxLength: 350 },
    try_this: items(160, 2),
    categories: {
      type: "object", additionalProperties: false,
      required: ["New Features", "Improvements", "Bug Fixes", "Changes"],
      properties: Object.fromEntries(["New Features", "Improvements", "Bug Fixes", "Changes"]
        .map((category) => [category, items(80, 8)])),
    },
  },
};

export async function runRequest(request, sdk) {
  if (!request || typeof request !== "object" || Array.isArray(request)
      || Object.keys(request).some((key) => !["prompt", "system_prompt", "structured", "timeout"].includes(key))
      || typeof request.prompt !== "string" || !request.prompt.trim()
      || typeof request.system_prompt !== "string" || !request.system_prompt.trim()
      || typeof request.structured !== "boolean"
      || !Number.isFinite(request.timeout) || request.timeout < 1 || request.timeout > 120) {
    fail("pi-invalid-request");
  }
  if (Buffer.byteLength(request.prompt) + Buffer.byteLength(request.system_prompt) > MAX_INPUT_BYTES) {
    fail("pi-input-too-large");
  }
  const controller = new AbortController();
  const deadline = AbortSignal.timeout(Math.ceil(request.timeout * 1000));
  const signal = AbortSignal.any([deadline, controller.signal]);
  try {
    // Explicit empty override config; reuse only the PUBLIC supported catalog
    // cache from the normal Pi agent directory. No network catalog refresh,
    // settings/hooks/extensions/session/context loading or credential copying.
    const runtime = await sdk.ModelRuntime.create({
      modelsPath: resolve(here, "../config/pi-models.json"),
      modelsStorePath: join(sdk.getAgentDir(), "models-store.json"),
      allowModelNetwork: false, refreshOnCreate: false, signal,
    });
    const provider = runtime.getProvider(PROVIDER);
    if (!provider?.auth?.oauth?.isSubscription || provider.auth.apiKey
        || provider.baseUrl !== BASE_URL) fail("pi-provider-mismatch");
    const auth = await runtime.checkAuth(PROVIDER, { signal });
    if (auth?.type !== "oauth") fail("pi-subscription-required");
    const refreshed = await runtime.refresh({ providers: [PROVIDER], allowNetwork: false, signal });
    if (refreshed.aborted) fail("pi-timeout");
    const model = runtime.getModel(PROVIDER, MODEL);
    if (!model) fail("pi-model-unavailable");
    if (model.id !== MODEL || model.provider !== PROVIDER || model.api !== API
        || model.baseUrl !== BASE_URL) fail("pi-provider-mismatch");

    const stream = runtime.streamSimple(model, {
      systemPrompt: request.system_prompt,
      messages: [{ role: "user", content: request.prompt, timestamp: Date.now() }],
      tools: [],
    }, {
      signal, timeoutMs: Math.ceil(request.timeout * 1000), maxRetries: 0,
      reasoning: "low", transport: "sse", cacheRetention: "none",
      // The Codex adapter ignores maxTokens; enforce byte limits while streaming
      // and a hard deadline instead of pretending there is a server token cap.
      onPayload(payload, actualModel) {
        if (actualModel.id !== MODEL || actualModel.provider !== PROVIDER || actualModel.api !== API
            || actualModel.baseUrl !== BASE_URL || payload.model !== MODEL
            || payload.store !== false || payload.tools?.length) fail("pi-provider-mismatch");
        payload.tool_choice = "none";
        if (request.structured) {
          payload.text = { ...payload.text, format: {
            type: "json_schema", name: "tech_digest_release", strict: true, schema: RELEASE_SCHEMA,
          } };
        }
        return payload;
      },
    });
    let streamBytes = 0;
    for await (const event of stream) {
      if (signal.aborted) fail("pi-timeout");
      if (["text_delta", "thinking_delta", "toolcall_delta"].includes(event.type)) {
        streamBytes += Buffer.byteLength(event.delta || "");
        if (streamBytes > MAX_STREAM_BYTES) fail("pi-output-too-large");
      }
      if (event.type.startsWith("toolcall")) fail("pi-invalid-result");
    }
    const result = await stream.result();
    if (result.stopReason === "error" || result.stopReason === "aborted") fail("pi-provider-failed");
    if (result.role !== "assistant" || result.stopReason !== "stop"
        || result.provider !== PROVIDER || result.model !== MODEL || result.api !== API
        || !Array.isArray(result.content)
        || result.content.some((block) => !["text", "thinking"].includes(block.type))) {
      fail("pi-invalid-result");
    }
    const text = result.content.filter((block) => block.type === "text").map((block) => block.text).join("");
    if (!text.trim()) fail("pi-invalid-result");
    if (Buffer.byteLength(text) > MAX_OUTPUT_BYTES) fail("pi-output-too-large");
    return { ok: true, provider: PROVIDER, model: MODEL, api: API, auth: "subscription-oauth", text };
  } catch (error) {
    if (deadline.aborted) fail("pi-timeout");
    if (error instanceof PiFailure) throw error;
    // Do NOT emit raw provider errorMessage, credentials, identifiers or URLs.
    fail("pi-provider-failed");
  } finally {
    controller.abort(); // Cancel a stream immediately on a local output/validation bound.
  }
}

async function main() {
  try {
    let size = 0;
    const chunks = [];
    for await (const chunk of process.stdin) {
      size += chunk.length;
      if (size > MAX_REQUEST_BYTES) fail("pi-input-too-large");
      chunks.push(chunk);
    }
    let request;
    try { request = JSON.parse(Buffer.concat(chunks).toString("utf8")); }
    catch { fail("pi-invalid-request"); }
    // The parent resolves this to the installed Pi executable's public SDK
    // entrypoint. No npm install, user extensions or arbitrary fallback runner.
    let sdk;
    try { sdk = await import(pathToFileURL(process.argv[2]).href); }
    catch { fail("pi-runtime-unavailable"); }
    const result = await runRequest(request, sdk);
    process.stdout.write(JSON.stringify(result) + "\n");
  } catch (error) {
    const code = error instanceof PiFailure && ERROR_CODES.has(error.message)
      ? error.message : "pi-provider-failed";
    process.stdout.write(JSON.stringify({ ok: false, error: code }) + "\n");
    process.exitCode = 1;
  }
}

if (process.argv[1] && resolve(process.argv[1]) === resolve(fileURLToPath(import.meta.url))) {
  await main();
}
