// Service worker: URL detection only. No backend calls.
import { detectPlatform } from "./detector.js";
import { buildApiUrl, getApiBase, getApiKey } from "./config.js";

const SYNC_QUEUE_KEY = "syncQueue";
const MAX_SYNC_QUEUE_ITEMS = 50;

// On install, open setup page if no API key stored
chrome.runtime.onInstalled.addListener(async () => {
  const apiKey = await getApiKey();
  if (!apiKey) {
    chrome.tabs.create({ url: "setup.html" });
  }
  await flushSyncQueue();
});

chrome.runtime.onStartup.addListener(async () => {
  await flushSyncQueue();
});

// Enable side panel on action click
chrome.sidePanel
  .setPanelBehavior({ openPanelOnActionClick: true })
  .catch(() => {});

function isTrustedExtensionSender(sender) {
  return sender?.id === chrome.runtime.id;
}

async function postToBackend(path, payload, apiKey, apiBase) {
  const response = await fetch(buildApiUrl(apiBase, path), {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${apiKey}`,
    },
    body: JSON.stringify(payload),
  });
  return response.ok;
}

async function enqueueSyncRequest(entry) {
  const data = await chrome.storage.local.get(SYNC_QUEUE_KEY);
  const queue = data[SYNC_QUEUE_KEY] || [];
  queue.push({
    ...entry,
    enqueued_at: Date.now(),
  });

  await chrome.storage.local.set({
    [SYNC_QUEUE_KEY]: queue.slice(-MAX_SYNC_QUEUE_ITEMS),
  });
}

async function flushSyncQueue() {
  const [apiKey, apiBase, queueData] = await Promise.all([
    getApiKey(),
    getApiBase(),
    chrome.storage.local.get(SYNC_QUEUE_KEY),
  ]);

  if (!apiKey) {
    return;
  }

  const queue = queueData[SYNC_QUEUE_KEY] || [];
  if (queue.length === 0) {
    return;
  }

  const remaining = [];
  for (let i = 0; i < queue.length; i += 1) {
    const entry = queue[i];
    try {
      const ok = await postToBackend(entry.path, entry.payload, apiKey, apiBase);
      if (!ok) {
        remaining.push(...queue.slice(i));
        break;
      }
    } catch {
      remaining.push(...queue.slice(i));
      break;
    }
  }

  await chrome.storage.local.set({ [SYNC_QUEUE_KEY]: remaining });
}

// --- Sprint 17: Handle tracker.js messages ---
chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (!isTrustedExtensionSender(sender)) {
    sendResponse({ ok: false, error: "untrusted_sender" });
    return false;
  }

  if (message.type === "OPEN_SIDE_PANEL") {
    // Open side panel from toast click
    const tabId = sender.tab?.id;
    if (tabId) {
      chrome.sidePanel.open({ tabId }).catch(() => {});
    } else {
      chrome.tabs.query({ active: true, currentWindow: true }, ([tab]) => {
        if (tab) {
          chrome.sidePanel.open({ tabId: tab.id }).catch(() => {});
        }
      });
    }
    sendResponse({ ok: true });
    return false;
  }
  if (message.type === "REPORT_FALSE_POSITIVE") {
    handleFalsePositiveReport(message).then(() => sendResponse({ ok: true }));
    return true;
  }
  if (message.type === "CAREER_PAGE_VISIT") {
    // Store visit data for nudge display in side panel
    handleCareerPageVisit(message).then(() => sendResponse({ ok: true }));
    return true; // async response
  }
  if (message.type === "APPLICATION_SUBMITTED") {
    handleApplicationSubmitted(message).then(() => sendResponse({ ok: true }));
    return true;
  }
});

async function handleCareerPageVisit({ domain, url, visitCount }) {
  // Aggregate visits in storage for nudge logic
  const key = `visits_${domain}`;
  const data = await chrome.storage.local.get(key);
  const existing = data[key] || { domain, visitCount: 0, urls: [], firstVisit: Date.now() };
  existing.visitCount = visitCount;
  existing.lastVisit = Date.now();
  if (!existing.urls.includes(url)) {
    existing.urls.push(url);
  }
  await chrome.storage.local.set({ [key]: existing });

  // Sync to backend if API key is set
  const [apiKey, apiBase] = await Promise.all([getApiKey(), getApiBase()]);
  if (apiKey) {
    try {
      await flushSyncQueue();
      const payload = { domain, url, visit_count: visitCount };
      const ok = await postToBackend(
        "/api/company-visits",
        payload,
        apiKey,
        apiBase
      );
      if (!ok) {
        await enqueueSyncRequest({
          path: "/api/company-visits",
          payload,
        });
      }
    } catch {
      await enqueueSyncRequest({
        path: "/api/company-visits",
        payload: { domain, url, visit_count: visitCount },
      });
    }
  }
}

async function handleApplicationSubmitted({ platform, url, domain, enrichment }) {
  const [apiKey, apiBase] = await Promise.all([getApiKey(), getApiBase()]);
  if (!apiKey) return;

  try {
    await flushSyncQueue();
    const payload = { platform, url, domain, enrichment };
    const ok = await postToBackend(
      "/api/company-visits/submission",
      payload,
      apiKey,
      apiBase
    );
    if (!ok) {
      await enqueueSyncRequest({
        path: "/api/company-visits/submission",
        payload,
      });
    }
  } catch {
    await enqueueSyncRequest({
      path: "/api/company-visits/submission",
      payload: { platform, url, domain, enrichment },
    });
  }
}

async function handleFalsePositiveReport({ url, domain }) {
  const [apiKey, apiBase] = await Promise.all([getApiKey(), getApiBase()]);
  if (!apiKey) return;

  const payload = {
    report_type: "false_positive",
    url,
    domain,
    user_agent: "extension-background",
    extension_version: chrome.runtime.getManifest().version,
  };

  try {
    await postToBackend("/api/extraction-reports", payload, apiKey, apiBase);
  } catch {
    await enqueueSyncRequest({ path: "/api/extraction-reports", payload });
  }
}

// --- Programmatic content script injection ---
// Manifest content_scripts only inject on full page loads. For SPAs like LinkedIn,
// Workday, etc., the URL changes via pushState without a full reload.
// We programmatically inject on:
//   1. tabs.onUpdated (catches SPA navigation + full loads)
//   2. tabs.onActivated (catches switching to an already-loaded job tab)
// content.js and banner.js both have their own duplicate-injection guards.

async function injectScripts(tabId) {
  try {
    await chrome.scripting.executeScript({
      target: { tabId },
      files: ["content.js"],
    });
  } catch {
    // Tab may not be injectable (chrome://, about:, etc.)
  }

  try {
    await chrome.scripting.executeScript({
      target: { tabId },
      files: ["banner.js"],
    });
  } catch {
    // Same — swallow injection errors
  }
}

// Detect job URLs on every tab update
chrome.tabs.onUpdated.addListener(async (tabId, changeInfo, tab) => {
  if (changeInfo.status !== "complete" || !tab.url) return;

  const detection = detectPlatform(tab.url);

  if (detection) {
    // Green badge
    chrome.action.setBadgeText({ text: "\u25CF", tabId });
    chrome.action.setBadgeBackgroundColor({ color: "#22c55e", tabId });

    // Store detection in session storage
    await chrome.storage.session.set({
      detection: {
        platform: detection.platform,
        params: detection.params,
        url: tab.url,
      },
    });

    // Inject content + toast scripts (guards inside handle duplicates)
    await injectScripts(tabId);
  } else {
    // Clear badge
    chrome.action.setBadgeText({ text: "", tabId });
    await chrome.storage.session.remove("detection");
  }
});

// Also inject when user switches to an already-loaded tab with a job URL
chrome.tabs.onActivated.addListener(async ({ tabId }) => {
  try {
    const tab = await chrome.tabs.get(tabId);
    if (!tab.url) return;
    const detection = detectPlatform(tab.url);
    if (detection) {
      chrome.action.setBadgeText({ text: "\u25CF", tabId });
      chrome.action.setBadgeBackgroundColor({ color: "#22c55e", tabId });
      await chrome.storage.session.set({
        detection: {
          platform: detection.platform,
          params: detection.params,
          url: tab.url,
        },
      });
      // Inject — guards inside will prevent duplicate listeners/observers
      // Banner cooldown will prevent toast spam on tab switching
      await injectScripts(tabId);
    }
  } catch {
    // Tab may have been closed between activation and get()
  }
});
