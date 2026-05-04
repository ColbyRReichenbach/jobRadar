#!/usr/bin/env node
import { mkdtemp, rm } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { createRequire } from "node:module";
import { fileURLToPath } from "node:url";

const require = createRequire(new URL("../../dashboardv2/package.json", import.meta.url));
const { chromium } = require("@playwright/test");

const ROOT_DIR = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../..");
const DEFAULT_API_BASE = "https://api.apptrail.com";

function envFlag(name, defaultValue = false) {
  const value = process.env[name];
  if (value == null || value === "") return defaultValue;
  return ["1", "true", "yes", "on"].includes(value.toLowerCase());
}

function requiredEnv(name) {
  const value = process.env[name]?.trim();
  if (!value) {
    throw new Error(`${name} is required.`);
  }
  return value;
}

function normalizeApiBase(value) {
  const parsed = new URL(value || DEFAULT_API_BASE);
  parsed.pathname = "";
  parsed.search = "";
  parsed.hash = "";
  return parsed.toString().replace(/\/$/, "");
}

function extensionPath() {
  return path.resolve(ROOT_DIR, process.env.APPTRAIL_EXTENSION_PATH || "extension");
}

async function waitForExtensionServiceWorker(context) {
  let [serviceWorker] = context.serviceWorkers();
  if (!serviceWorker) {
    serviceWorker = await context.waitForEvent("serviceworker", { timeout: 15_000 });
  }
  const url = new URL(serviceWorker.url());
  if (url.protocol !== "chrome-extension:") {
    throw new Error(`Unexpected extension service worker URL: ${serviceWorker.url()}`);
  }
  return { serviceWorker, extensionId: url.hostname };
}

async function validateSetupPage(context, extensionId, { apiBase, apiKey, expectedEmail }) {
  const setup = await context.newPage();
  await setup.goto(`chrome-extension://${extensionId}/setup.html`);
  await setup.locator("#apiBase").fill(apiBase);
  await setup.locator("#apiKey").fill(apiKey);
  await setup.locator("#saveBtn").click();
  await setup.waitForFunction(() => {
    const text = document.querySelector("#status")?.textContent || "";
    return text.includes("Connected successfully") || text.includes("Validation failed");
  }, null, { timeout: 30_000 });

  const statusText = (await setup.locator("#status").textContent()) || "";
  if (!statusText.includes("Connected successfully")) {
    throw new Error(`Extension setup validation failed: ${statusText}`);
  }
  if (expectedEmail && !statusText.includes(expectedEmail)) {
    throw new Error(`Validated key, but setup page did not show expected email ${expectedEmail}.`);
  }
  await setup.close();
  return statusText.replace(apiKey, "[REDACTED]");
}

async function assertExtensionStorage(serviceWorker, { apiBase }) {
  const storageState = await serviceWorker.evaluate(async () => {
    const data = await chrome.storage.local.get(["apiBase", "apiKey"]);
    return {
      apiBase: data.apiBase || null,
      hasApiKey: Boolean(data.apiKey),
    };
  });
  if (storageState.apiBase !== apiBase) {
    throw new Error(`Stored API base mismatch: expected ${apiBase}, got ${storageState.apiBase}`);
  }
  if (!storageState.hasApiKey) {
    throw new Error("API key was not stored in extension local storage.");
  }
}

async function createSmokeJob(serviceWorker, { apiBase }) {
  return serviceWorker.evaluate(async ({ apiBase: targetApiBase }) => {
    const { apiKey } = await chrome.storage.local.get("apiKey");
    const unique = Date.now();
    const response = await fetch(`${targetApiBase}/api/jobs`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${apiKey}`,
      },
      body: JSON.stringify({
        company: "AppTrail Extension Smoke",
        role_title: `Smoke Test ${unique}`,
        job_url: `https://boards.greenhouse.io/apptrail-smoke/jobs/${unique}`,
        source: "extension_smoke",
        status: "saved",
      }),
    });
    const text = await response.text();
    return {
      ok: response.ok || response.status === 409,
      status: response.status,
      body: text.slice(0, 500),
    };
  }, { apiBase });
}

async function clearStoredKey(serviceWorker) {
  await serviceWorker.evaluate(async () => {
    await Promise.all([
      chrome.storage.local.remove("apiKey"),
      chrome.storage.session.remove("apiKey"),
    ]);
  });
}

async function main() {
  const apiKey = requiredEnv("APPTRAIL_EXTENSION_API_KEY");
  const apiBase = normalizeApiBase(process.env.APPTRAIL_EXTENSION_API_BASE || DEFAULT_API_BASE);
  const expectedEmail = process.env.APPTRAIL_EXTENSION_EXPECTED_EMAIL?.trim() || "";
  const extPath = extensionPath();
  const headed = !envFlag("APPTRAIL_EXTENSION_HEADLESS", false);
  const createJob = envFlag("APPTRAIL_EXTENSION_CREATE_SMOKE_JOB", false);
  const clearKeyAfter = envFlag("APPTRAIL_EXTENSION_CLEAR_KEY_AFTER", true);
  const keepProfile = envFlag("APPTRAIL_EXTENSION_KEEP_PROFILE", false);
  const profileDir = process.env.APPTRAIL_EXTENSION_PROFILE_DIR
    ? path.resolve(process.env.APPTRAIL_EXTENSION_PROFILE_DIR)
    : await mkdtemp(path.join(os.tmpdir(), "apptrail-extension-smoke-"));

  const context = await chromium.launchPersistentContext(profileDir, {
    headless: !headed,
    args: [
      `--disable-extensions-except=${extPath}`,
      `--load-extension=${extPath}`,
    ],
  });

  try {
    const { serviceWorker, extensionId } = await waitForExtensionServiceWorker(context);
    const status = await validateSetupPage(context, extensionId, { apiBase, apiKey, expectedEmail });
    await assertExtensionStorage(serviceWorker, { apiBase });

    console.log(`Extension smoke setup passed for ${apiBase}.`);
    console.log(status);

    if (createJob) {
      const result = await createSmokeJob(serviceWorker, { apiBase });
      if (!result.ok) {
        throw new Error(`Smoke job create failed (${result.status}): ${result.body}`);
      }
      console.log(`Optional smoke job create returned ${result.status}.`);
    }

    if (clearKeyAfter) {
      await clearStoredKey(serviceWorker);
      console.log("Stored extension key cleared from the smoke profile.");
    }
  } finally {
    await context.close();
    if (!keepProfile && !process.env.APPTRAIL_EXTENSION_PROFILE_DIR) {
      await rm(profileDir, { recursive: true, force: true });
    }
  }
}

main().catch((error) => {
  console.error(`Chrome extension smoke failed: ${error.message}`);
  process.exit(1);
});
