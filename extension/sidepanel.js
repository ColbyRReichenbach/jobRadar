import { buildApiUrl, getApiBase, getApiKey } from "./config.js";
import { detectPlatform } from "./detector.js";

let currentJobData = null;
let currentUrl = null;
let currentDetection = null;

// Settings defaults
const SETTINGS_KEY = "apptrail_settings";
const DEFAULT_SETTINGS = {
  linkedinAutoExtract: true,
};
const DEFAULT_NO_JOB_MESSAGE = "Navigate to a job posting page to get started.";
const UNAVAILABLE_NO_JOB_MESSAGE = "This job posting is unavailable or has been removed.";

async function getSettings() {
  const data = await chrome.storage.local.get(SETTINGS_KEY);
  return { ...DEFAULT_SETTINGS, ...(data[SETTINGS_KEY] || {}) };
}

async function saveSetting(key, value) {
  const settings = await getSettings();
  settings[key] = value;
  await chrome.storage.local.set({ [SETTINGS_KEY]: settings });
}

// --- Helpers ---

async function apiFetch(path, options = {}) {
  const [apiBase, apiKey] = await Promise.all([getApiBase(), getApiKey()]);
  return fetch(buildApiUrl(apiBase, path), {
    ...options,
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${apiKey}`,
      ...(options.headers || {}),
    },
  });
}

function show(id) {
  document.getElementById(id).classList.remove("hidden");
}
function hide(id) {
  document.getElementById(id).classList.add("hidden");
}

function setNoJobCtaVisible(isVisible) {
  const button = document.getElementById("report-undetected-btn");
  if (!button) return;

  button.classList.toggle("hidden", !isVisible);
  button.toggleAttribute("hidden", !isVisible);
  button.setAttribute("aria-hidden", isVisible ? "false" : "true");
}

function setNoJobMessage(message) {
  const copy = document.querySelector("#no-job > p");
  if (copy) {
    copy.textContent = message;
  }
}

function showDefaultNoJobState() {
  setNoJobMessage(DEFAULT_NO_JOB_MESSAGE);
  setNoJobCtaVisible(true);
  hide("undetected-form");
  show("no-job");
  hide("loading");
  hide("job-data");
}

function showUnavailableState() {
  setNoJobMessage(UNAVAILABLE_NO_JOB_MESSAGE);
  setNoJobCtaVisible(false);
  hide("undetected-form");
  show("no-job");
  hide("loading");
  hide("job-data");
}

function clearElement(element) {
  element.replaceChildren();
}

function appendTextElement(parent, tagName, className, text) {
  const element = document.createElement(tagName);
  if (className) {
    element.className = className;
  }
  element.textContent = text;
  parent.appendChild(element);
  return element;
}

function renderAlert(container, variant, message) {
  clearElement(container);
  appendTextElement(container, "div", `alert alert-${variant}`, message);
}

function isNetworkError(error) {
  return error instanceof TypeError;
}

function isSafeExternalUrl(url) {
  try {
    const parsed = new URL(url);
    return parsed.protocol === "https:" || parsed.protocol === "http:";
  } catch {
    return false;
  }
}

function readEditableValue(element) {
  if (!element || element.classList.contains("placeholder")) {
    return null;
  }
  const text = element.textContent?.trim();
  return text || null;
}

function bindEditablePlaceholderBehavior(element, placeholder) {
  if (!element || element.dataset.placeholderBound === "true") {
    return;
  }

  element.dataset.placeholderBound = "true";

  element.addEventListener("focus", () => {
    if (element.classList.contains("placeholder")) {
      element.textContent = "";
      element.classList.remove("placeholder");
    }
  });

  element.addEventListener("blur", () => {
    if (!element.textContent.trim()) {
      element.textContent = placeholder;
      element.classList.add("placeholder");
    }
  });
}

function createContactCard(contact) {
  const card = document.createElement("div");
  card.className = "contact-card";

  appendTextElement(card, "div", "contact-name", contact.name || "Unknown");
  appendTextElement(card, "div", "contact-title", contact.title || "");

  if (contact.email) {
    appendTextElement(card, "div", "contact-email", contact.email);
  }

  if (contact.confidence_score) {
    const confidence = document.createElement("div");
    confidence.style.fontSize = "11px";
    confidence.style.color = "#94a3b8";
    confidence.textContent = `Confidence: ${Math.round(contact.confidence_score * 100)}%`;
    card.appendChild(confidence);
  }

  const label = document.createElement("label");
  label.className = "contact-check";

  const checkbox = document.createElement("input");
  checkbox.type = "checkbox";
  checkbox.dataset.contactId = String(contact.id);
  checkbox.checked = Boolean(contact.reached_out);
  label.appendChild(checkbox);
  label.append(" I reached out to this person");

  card.appendChild(label);
  return card;
}

function renderLinkedinLink(container, url, company) {
  clearElement(container);
  if (!url || !isSafeExternalUrl(url)) {
    return;
  }

  const link = document.createElement("a");
  link.href = url;
  link.target = "_blank";
  link.rel = "noopener noreferrer";
  link.style.display = "block";
  link.style.marginTop = "8px";
  link.style.fontSize = "12px";
  link.textContent = `Search alumni at ${company} on LinkedIn`;
  container.appendChild(link);
}

function renderBrowsingNudge(container, domain, visitCount) {
  clearElement(container);

  const nudge = document.createElement("div");
  nudge.className = "nudge";

  appendTextElement(nudge, "div", "nudge-title", `Interested in ${domain}?`);
  appendTextElement(
    nudge,
    "div",
    "nudge-text",
    `You've visited their careers page ${visitCount} times. Want to track this company?`
  );

  const button = document.createElement("button");
  button.className = "btn-nudge";
  button.id = "nudge-track-btn";
  button.textContent = "Save to Pipeline";
  nudge.appendChild(button);

  container.appendChild(nudge);
}

function renderSavedNudge(container, domain) {
  clearElement(container);

  const nudge = document.createElement("div");
  nudge.className = "nudge";
  appendTextElement(nudge, "div", "nudge-title", "Saved!");
  appendTextElement(nudge, "div", "nudge-text", `${domain} added to your pipeline.`);
  container.appendChild(nudge);
}

function extractDomain(url) {
  try {
    const hostname = new URL(url).hostname;
    const parts = hostname.split(".");
    return parts.length > 2 ? parts.slice(-2).join(".") : hostname;
  } catch {
    return "";
  }
}

// --- Init ---

let setupOpened = false;

async function init() {
  const apiKey = await getApiKey();
  if (!apiKey) {
    if (!setupOpened) {
      setupOpened = true;
      chrome.tabs.create({ url: "setup.html" });
    }
    showDefaultNoJobState();
    return;
  }

  // Try session storage first, then detect from active tab URL directly
  let detection = null;
  const data = await chrome.storage.session.get("detection");
  if (data.detection) {
    detection = data.detection;
  } else {
    // Detect from the current tab URL (handles pages loaded before extension refresh)
    const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
    if (tab?.url) {
      const result = detectPlatform(tab.url);
      if (result) {
        detection = { platform: result.platform, params: result.params, url: tab.url };
        await chrome.storage.session.set({ detection });
      }
    }
  }

  if (!detection) {
    showDefaultNoJobState();
    return;
  }

  currentUrl = detection.url;
  currentDetection = detection;

  hide("no-job");
  show("loading");

  const settings = await getSettings();
  const isLinkedIn = detection.platform === "linkedin";

  // LinkedIn with auto-extract disabled → show manual form with disclaimer
  if (isLinkedIn && !settings.linkedinAutoExtract) {
    displayJobData({
      title: null,
      company: null,
      location: null,
      description: null,
      source: "manual",
      _linkedinManual: true,
    });
    return;
  }

  try {
    let extracted = false;

    // Try content script extraction for ALL platforms (not just LinkedIn)
    const [tab] = await chrome.tabs.query({
      active: true,
      currentWindow: true,
    });
    if (tab) {
      try {
        const response = await chrome.tabs.sendMessage(tab.id, {
          type: "EXTRACT_JOB",
        });
        if (response?._page_state === "unavailable") {
          showUnavailableState();
          return;
        }
        if (response && (response.title || response.company)) {
          displayJobData(response);
          extracted = true;
        }
      } catch {
        // Content script not injected — fall through to backend parse
      }
    }

    // Also try session storage for extraction from MutationObserver
    if (!extracted) {
      const stored = await chrome.storage.session.get("extractedJob");
      if (stored.extractedJob?._page_state === "unavailable") {
        showUnavailableState();
        return;
      }
      if (stored.extractedJob && (stored.extractedJob.title || stored.extractedJob.company)) {
        displayJobData(stored.extractedJob);
        extracted = true;
      }
    }

    if (!extracted) {
      await fallbackParse(currentUrl);
    }
  } catch (e) {
    showDefaultNoJobState();
    renderAlert(
      document.getElementById("no-job"),
      "error",
      "Failed to load job data."
    );
  }
}

async function fallbackParse(url) {
  try {
    const resp = await apiFetch("/api/jobs/parse", {
      method: "POST",
      body: JSON.stringify({ url }),
    });

    if (resp.status === 401 || resp.status === 403) {
      hide("loading");
      show("no-job");
      renderAlert(
        document.getElementById("no-job"),
        "error",
        "Extension authentication failed. Reconnect your API key in setup."
      );
      return;
    }

    const result = await resp.json();
    if (result.status === "ok" && result.data && (result.data.title || result.data.company)) {
      displayJobData(result.data);
    } else {
      // Backend couldn't parse — show editable form with URL-derived defaults
      displayJobData({
        title: null,
        company: null,
        location: null,
        description: null,
        source: "manual",
      });
    }
  } catch (error) {
    hide("loading");
    show("no-job");
    renderAlert(
      document.getElementById("no-job"),
      "error",
      isNetworkError(error)
        ? "You appear to be offline or the backend is unavailable."
        : "Failed to load job data."
    );
  }
}

function setFieldValue(id, value, placeholder) {
  const el = document.getElementById(id);
  if (value) {
    el.textContent = value;
    el.classList.remove("placeholder");
  } else {
    el.textContent = placeholder;
    el.classList.add("placeholder");
  }

  bindEditablePlaceholderBehavior(el, placeholder);
}

function displayJobData(data) {
  currentJobData = data;
  hide("loading");
  hide("no-job");
  show("job-data");

  // Show platform badge
  const badgeContainer = document.getElementById("platform-badge-container");
  clearElement(badgeContainer);
  const detection = currentDetection;
  if (detection && detection.platform && detection.platform !== "generic") {
    const badge = document.createElement("span");
    badge.className = "platform-badge";
    badge.textContent = detection.platform.replace("_", " ");
    badgeContainer.appendChild(badge);
  }

  // Show extraction method badge
  if (data._method) {
    const methodBadge = document.createElement("span");
    methodBadge.className = "method-badge";
    methodBadge.textContent = data._method === "json-ld" ? "structured data" : data._method;
    badgeContainer.appendChild(methodBadge);
  }

  setFieldValue("job-company", data.company, "Enter company name");
  setFieldValue("job-title", data.title, "Enter job title");
  setFieldValue("job-location", data.location, "Enter location");
  setFieldValue("job-salary", data.salary, "Not listed");

  // Description — editable textarea with auto-resize
  const descEl = document.getElementById("job-description");
  const descCount = document.getElementById("desc-char-count");
  const descExpand = document.getElementById("desc-expand-btn");
  descEl.value = data.description || "";
  autoResizeTextarea(descEl);
  updateDescMeta(descEl, descCount, descExpand);

  // Show LinkedIn disclaimer if applicable
  const disclaimerEl = document.getElementById("linkedin-disclaimer");
  if (detection && detection.platform === "linkedin") {
    disclaimerEl.classList.remove("hidden");
    // Show the right variant
    if (data._linkedinManual) {
      document.getElementById("linkedin-manual-msg").classList.remove("hidden");
      document.getElementById("linkedin-auto-msg").classList.add("hidden");
    } else {
      document.getElementById("linkedin-manual-msg").classList.add("hidden");
      document.getElementById("linkedin-auto-msg").classList.remove("hidden");
    }
  } else {
    disclaimerEl.classList.add("hidden");
  }
}

// --- Status picker ---

let selectedStatus = "saved";

document.querySelectorAll(".status-option").forEach((btn) => {
  btn.addEventListener("click", () => {
    document.querySelectorAll(".status-option").forEach((b) => b.classList.remove("active"));
    btn.classList.add("active");
    selectedStatus = btn.dataset.status;
  });
});

// --- Track Job ---

document.getElementById("track-btn").addEventListener("click", async () => {
  const btn = document.getElementById("track-btn");
  const statusEl = document.getElementById("track-status");
  btn.disabled = true;
  btn.textContent = "Tracking...";
  clearElement(statusEl);

  // Read from editable fields (user may have edited them)
  const companyEl = document.getElementById("job-company");
  const titleEl = document.getElementById("job-title");
  const locationEl = document.getElementById("job-location");
  const salaryEl = document.getElementById("job-salary");
  const companyText = readEditableValue(companyEl);
  const titleText = readEditableValue(titleEl);
  const locationText = readEditableValue(locationEl);
  const salaryText = readEditableValue(salaryEl);

  const descriptionEl = document.getElementById("job-description");
  const descriptionText = descriptionEl?.value?.trim() || null;

  if (!companyText || !titleText) {
    renderAlert(
      statusEl,
      "warning",
      "Enter both the company and job title before tracking this listing."
    );
    btn.disabled = false;
    btn.textContent = "Track This Job";
    return;
  }

  const payload = {
    company: companyText,
    role_title: titleText,
    job_url: currentUrl,
    source: currentJobData.source || "manual",
    status: selectedStatus,
    department: currentJobData.department || null,
    description_text: descriptionText || currentJobData.description || null,
    salary: salaryText || currentJobData.salary || null,
    location: locationText || currentJobData.location || null,
  };

  try {
    const resp = await apiFetch("/api/jobs", {
      method: "POST",
      body: JSON.stringify(payload),
    });

    if (resp.status === 201) {
      const appData = await resp.json();
      renderAlert(statusEl, "success", "Job tracked successfully!");
      btn.textContent = "Tracked";

      // Find contacts
      const domain = extractDomain(currentUrl);
      await findContacts(appData.id, payload.company, domain);
    } else if (resp.status === 409) {
      const detail = (await resp.json()).detail;
      renderAlert(
        statusEl,
        "warning",
        `Already tracked: ${detail.existing.company} - ${detail.existing.role_title}`
      );
      btn.textContent = "Already Tracked";
    } else {
      renderAlert(statusEl, "error", "Failed to track job.");
      btn.disabled = false;
      btn.textContent = "Track This Job";
    }
  } catch (e) {
    renderAlert(
      statusEl,
      "error",
      isNetworkError(e)
        ? "You appear to be offline or the backend is unavailable."
        : "Error connecting to backend."
    );
    btn.disabled = false;
    btn.textContent = "Track This Job";
  }
});

// --- Contacts ---

async function findContacts(applicationId, company, domain) {
  try {
    const resp = await apiFetch("/api/contacts/find", {
      method: "POST",
      body: JSON.stringify({
        application_id: applicationId,
        company: company,
        domain: domain,
      }),
    });

    if (!resp.ok) return;

    const data = await resp.json();
    const contacts = data.contacts || [];

    if (contacts.length === 0 && !data.linkedin_search_url) return;

    show("contacts-section");
    const listEl = document.getElementById("contacts-list");
    clearElement(listEl);

    for (const contact of contacts) {
      listEl.appendChild(createContactCard(contact));
    }

    // Checkbox handlers
    listEl.querySelectorAll('input[type="checkbox"]').forEach((cb) => {
      cb.addEventListener("change", async (e) => {
        const contactId = e.target.dataset.contactId;
        await apiFetch(`/api/contacts/${contactId}`, {
          method: "PATCH",
          body: JSON.stringify({
            reached_out: e.target.checked,
          }),
        });
      });
    });

    // LinkedIn search URL
    if (data.linkedin_search_url) {
      renderLinkedinLink(
        document.getElementById("linkedin-link"),
        data.linkedin_search_url,
        company
      );
    }
  } catch (e) {
    console.error("Failed to find contacts:", e);
  }
}

// --- Sprint 17: Browsing Nudge ---

async function checkBrowsingNudge() {
  // Get current tab domain
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  if (!tab || !tab.url) return;

  const detection = detectPlatform(tab.url);
  if (detection && detection.platform !== "generic") {
    return;
  }

  const domain = extractDomain(tab.url);
  if (!domain) return;

  // Check visit history from storage
  const key = `visits_${domain}`;
  const data = await chrome.storage.local.get(key);
  const visits = data[key];

  if (!visits || visits.visitCount < 3) return; // Only nudge after 3+ visits

  const nudgeEl = document.getElementById("browsing-nudge");
  renderBrowsingNudge(nudgeEl, domain, visits.visitCount);
  nudgeEl.classList.remove("hidden");

  document.getElementById("nudge-track-btn").addEventListener("click", async () => {
    const btn = document.getElementById("nudge-track-btn");
    btn.disabled = true;
    btn.textContent = "Saving...";

    try {
      const resp = await apiFetch("/api/jobs", {
        method: "POST",
        body: JSON.stringify({
          company: domain.split(".")[0].charAt(0).toUpperCase() + domain.split(".")[0].slice(1),
          role_title: "General Interest",
          job_url: tab.url,
          source: "extension_nudge",
        }),
      });

      if (resp.status === 201) {
        btn.textContent = "Saved!";
        renderSavedNudge(nudgeEl, domain);
      } else if (resp.status === 409) {
        btn.textContent = "Already Tracked";
      } else {
        btn.textContent = "Failed";
        btn.disabled = false;
      }
    } catch (e) {
      btn.textContent = "Error";
      btn.disabled = false;
    }
  });
}

// --- Report issue ---

document.getElementById("report-issue-btn")?.addEventListener("click", () => {
  const panel = document.getElementById("report-panel");
  panel.classList.toggle("hidden");
});

// Toggle field checkboxes
document.querySelectorAll(".report-field-check").forEach((label) => {
  label.addEventListener("click", () => {
    label.classList.toggle("selected");
    const cb = label.querySelector("input[type='checkbox']");
    if (cb) cb.checked = !cb.checked;
  });
});

document.getElementById("submit-report-btn")?.addEventListener("click", async () => {
  const btn = document.getElementById("submit-report-btn");
  const statusEl = document.getElementById("report-status");
  btn.disabled = true;
  btn.textContent = "Submitting...";
  clearElement(statusEl);

  // Gather flagged fields
  const flagged = [];
  document.querySelectorAll(".report-field-check.selected").forEach((label) => {
    flagged.push(label.dataset.field);
  });

  // Read current editable fields as corrected data
  const companyEl = document.getElementById("job-company");
  const titleEl = document.getElementById("job-title");
  const locationEl = document.getElementById("job-location");
  const salaryEl = document.getElementById("job-salary");
  const descEl = document.getElementById("job-description");

  const corrected = {
    company: companyEl?.classList.contains("placeholder") ? null : companyEl?.textContent?.trim(),
    title: titleEl?.classList.contains("placeholder") ? null : titleEl?.textContent?.trim(),
    location: locationEl?.classList.contains("placeholder") ? null : locationEl?.textContent?.trim(),
    salary: salaryEl?.classList.contains("placeholder") ? null : salaryEl?.textContent?.trim(),
    description: descEl?.value?.trim() || null,
  };

  const notes = document.getElementById("report-notes")?.value?.trim() || null;

  const payload = {
    report_type: flagged.length > 0 ? "wrong_data" : "missing_data",
    url: currentUrl || window.location.href,
    domain: extractDomain(currentUrl || ""),
    platform_detected: currentDetection?.platform || null,
    extraction_method: currentJobData?._method || null,
    extracted_data: currentJobData
      ? { title: currentJobData.title, company: currentJobData.company, location: currentJobData.location, salary: currentJobData.salary, description: currentJobData.description ? currentJobData.description.substring(0, 200) : null }
      : null,
    corrected_data: corrected,
    fields_flagged: flagged.length > 0 ? flagged : null,
    user_agent: navigator.userAgent,
    extension_version: chrome.runtime.getManifest().version,
    extractor_version: currentJobData?._extractor_version || null,
    notes,
  };

  try {
    const resp = await apiFetch("/api/extraction-reports", {
      method: "POST",
      body: JSON.stringify(payload),
    });
    if (resp.ok) {
      renderAlert(statusEl, "success", "Thanks! Report submitted.");
      btn.textContent = "Submitted";
      // Clear selections
      document.querySelectorAll(".report-field-check.selected").forEach((l) => {
        l.classList.remove("selected");
        const cb = l.querySelector("input");
        if (cb) cb.checked = false;
      });
      document.getElementById("report-notes").value = "";
    } else {
      renderAlert(statusEl, "error", "Failed to submit report.");
      btn.disabled = false;
      btn.textContent = "Submit Report";
    }
  } catch {
    renderAlert(statusEl, "error", "Failed to connect to backend.");
    btn.disabled = false;
    btn.textContent = "Submit Report";
  }
});

// --- "Report a job page" (undetected site) in empty state ---

document.getElementById("report-undetected-btn")?.addEventListener("click", async () => {
  const form = document.getElementById("undetected-form");
  form.classList.toggle("hidden");

  // Set up editable field placeholder behavior for manual fields
  ["manual-company", "manual-title", "manual-location", "manual-salary"].forEach((id) => {
    const el = document.getElementById(id);
    if (!el) return;
    if (el.dataset.manualPlaceholderBound === "true") return;

    const placeholder = el.textContent;
    el.dataset.manualPlaceholderBound = "true";
    el.addEventListener("focus", () => {
      if (el.style.fontStyle === "italic") {
        el.textContent = "";
        el.style.color = "#1e293b";
        el.style.fontStyle = "normal";
      }
    });
    el.addEventListener("blur", () => {
      if (!el.textContent.trim()) {
        el.textContent = placeholder;
        el.style.color = "#94a3b8";
        el.style.fontStyle = "italic";
      }
    });
  });
});

// Status picker in the undetected form
let manualSelectedStatus = "saved";
document.querySelectorAll("#undetected-form .status-option").forEach((btn) => {
  btn.addEventListener("click", () => {
    document.querySelectorAll("#undetected-form .status-option").forEach((b) => b.classList.remove("active"));
    btn.classList.add("active");
    manualSelectedStatus = btn.dataset.status;
  });
});

document.getElementById("manual-track-btn")?.addEventListener("click", async () => {
  const btn = document.getElementById("manual-track-btn");
  const statusEl = document.getElementById("manual-track-status");
  btn.disabled = true;
  btn.textContent = "Tracking...";
  clearElement(statusEl);

  const getManualVal = (id) => {
    const el = document.getElementById(id);
    return (el && el.style.fontStyle !== "italic") ? el.textContent.trim() : null;
  };

  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  const url = tab?.url || "";

  const jobPayload = {
    company: getManualVal("manual-company"),
    role_title: getManualVal("manual-title"),
    job_url: url,
    source: "manual",
    status: manualSelectedStatus,
    location: getManualVal("manual-location") || null,
    salary: getManualVal("manual-salary") || null,
  };

  if (!jobPayload.company || !jobPayload.role_title) {
    renderAlert(statusEl, "warning", "Enter both the company and job title before tracking this job.");
    btn.disabled = false;
    btn.textContent = "Track & Report";
    return;
  }

  try {
    // Track the job
    const trackResp = await apiFetch("/api/jobs", {
      method: "POST",
      body: JSON.stringify(jobPayload),
    });

    if (trackResp.status === 201 || trackResp.status === 409) {
      // Also submit undetected site report
      await apiFetch("/api/extraction-reports", {
        method: "POST",
        body: JSON.stringify({
          report_type: "undetected_site",
          url,
          domain: extractDomain(url),
          user_agent: navigator.userAgent,
          extension_version: chrome.runtime.getManifest().version,
        }),
      }).catch(() => {}); // Report is best-effort

      if (trackResp.status === 201) {
        renderAlert(statusEl, "success", "Job tracked & site reported. Thanks!");
        btn.textContent = "Tracked";
      } else {
        renderAlert(statusEl, "warning", "Already tracked. Site reported.");
        btn.textContent = "Already Tracked";
      }
    } else {
      renderAlert(statusEl, "error", "Failed to track job.");
      btn.disabled = false;
      btn.textContent = "Track & Report";
    }
  } catch {
    renderAlert(statusEl, "error", "Failed to connect.");
    btn.disabled = false;
    btn.textContent = "Track & Report";
  }
});

// --- Settings panel ---

async function initSettings() {
  const settings = await getSettings();
  const toggle = document.getElementById("linkedin-extract-toggle");
  if (toggle) {
    toggle.checked = settings.linkedinAutoExtract;
    toggle.addEventListener("change", async (e) => {
      await saveSetting("linkedinAutoExtract", e.target.checked);
    });
  }
}

// Toggle settings panel visibility
document.getElementById("settings-btn")?.addEventListener("click", () => {
  const panel = document.getElementById("settings-panel");
  panel.classList.toggle("hidden");
});

// Textarea auto-resize helper
function autoResizeTextarea(el) {
  el.style.height = "auto";
  el.style.height = Math.min(el.scrollHeight, 300) + "px";
}

function updateDescMeta(el, countEl, expandBtn) {
  const len = el.value.length;
  countEl.textContent = len > 0 ? `${len.toLocaleString()} chars` : "";
  if (el.scrollHeight > 300) {
    expandBtn.classList.remove("hidden");
  } else {
    expandBtn.classList.add("hidden");
  }
}

// Wire up description textarea events
const _descEl = document.getElementById("job-description");
const _descCount = document.getElementById("desc-char-count");
const _descExpand = document.getElementById("desc-expand-btn");

_descEl?.addEventListener("input", () => {
  autoResizeTextarea(_descEl);
  updateDescMeta(_descEl, _descCount, _descExpand);
});

_descExpand?.addEventListener("click", () => {
  const isExpanded = _descEl.style.maxHeight === "none";
  if (isExpanded) {
    _descEl.style.maxHeight = "300px";
    _descExpand.textContent = "Expand";
  } else {
    _descEl.style.maxHeight = "none";
    _descExpand.textContent = "Collapse";
  }
});

// Reset UI to initial state before re-detecting
function resetUI() {
  currentJobData = null;
  currentUrl = null;
  currentDetection = null;
  setNoJobMessage(DEFAULT_NO_JOB_MESSAGE);
  setNoJobCtaVisible(true);
  hide("undetected-form");
  hide("job-data");
  hide("loading");
  hide("contacts-section");
  hide("browsing-nudge");
  const statusEl = document.getElementById("track-status");
  clearElement(statusEl);
  const btn = document.getElementById("track-btn");
  btn.disabled = false;
  btn.textContent = "Track This Job";
  clearElement(document.getElementById("contacts-list"));
  clearElement(document.getElementById("linkedin-link"));
  // Reset status picker
  selectedStatus = "saved";
  document.querySelectorAll(".status-option").forEach((b) => {
    b.classList.toggle("active", b.dataset.status === "saved");
  });
  // Clear stored detection so init() re-reads from active tab
  chrome.storage.session.remove("detection");
}

// Re-init when user switches tabs or navigates within a tab
chrome.tabs.onActivated.addListener(() => {
  resetUI();
  init();
  checkBrowsingNudge();
});
chrome.tabs.onUpdated.addListener((tabId, changeInfo) => {
  if (changeInfo.status === "complete") {
    chrome.tabs.query({ active: true, currentWindow: true }, ([tab]) => {
      if (tab && tab.id === tabId) {
        resetUI();
        init();
        checkBrowsingNudge();
      }
    });
  }
});

// Run on load
init();
initSettings();
checkBrowsingNudge();
