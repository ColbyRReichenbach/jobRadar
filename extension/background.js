// Service worker: URL detection only. No backend calls.
import { detectPlatform } from "./detector.js";
import { buildApiUrl, getApiBase, getApiKey } from "./config.js";

// On install, open setup page if no API key stored
chrome.runtime.onInstalled.addListener(async () => {
  const data = await chrome.storage.local.get("apiKey");
  if (!data.apiKey) {
    chrome.tabs.create({ url: "setup.html" });
  }
});

// Enable side panel on action click
chrome.sidePanel
  .setPanelBehavior({ openPanelOnActionClick: true })
  .catch(() => {});

function isTrustedExtensionSender(sender) {
  return sender?.id === chrome.runtime.id;
}

// --- Sprint 17: Handle tracker.js messages ---
chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (!isTrustedExtensionSender(sender)) {
    sendResponse({ ok: false, error: "untrusted_sender" });
    return false;
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
      await fetch(buildApiUrl(apiBase, "/api/company-visits"), {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${apiKey}`,
        },
        body: JSON.stringify({ domain, url, visit_count: visitCount }),
      });
    } catch (e) {
      // Silent fail — visit sync is best-effort
    }
  }
}

async function handleApplicationSubmitted({ platform, url, domain, enrichment }) {
  const [apiKey, apiBase] = await Promise.all([getApiKey(), getApiBase()]);
  if (!apiKey) return;

  try {
    // Notify backend about auto-detected application submission
    await fetch(buildApiUrl(apiBase, "/api/company-visits/submission"), {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${apiKey}`,
      },
      body: JSON.stringify({ platform, url, domain, enrichment }),
    });
  } catch (e) {
    // Silent fail
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
  } else {
    // Clear badge
    chrome.action.setBadgeText({ text: "", tabId });
    await chrome.storage.session.remove("detection");
  }
});
