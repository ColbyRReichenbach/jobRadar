const API_BASE = "http://localhost:8000";

let currentJobData = null;
let currentUrl = null;

// --- Helpers ---

async function getApiKey() {
  const data = await chrome.storage.local.get("apiKey");
  return data.apiKey || "";
}

async function apiFetch(path, options = {}) {
  const apiKey = await getApiKey();
  return fetch(`${API_BASE}${path}`, {
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

function isSafeExternalUrl(url) {
  try {
    const parsed = new URL(url);
    return parsed.protocol === "https:" || parsed.protocol === "http:";
  } catch {
    return false;
  }
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
  link.textContent = `Search UNC alumni at ${company} on LinkedIn`;
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

async function init() {
  const apiKey = await getApiKey();
  if (!apiKey) {
    chrome.tabs.create({ url: "setup.html" });
    return;
  }

  const data = await chrome.storage.session.get("detection");
  if (!data.detection) {
    show("no-job");
    hide("loading");
    hide("job-data");
    return;
  }

  const detection = data.detection;
  currentUrl = detection.url;

  hide("no-job");
  show("loading");

  try {
    if (detection.platform === "linkedin") {
      // Message content script
      const [tab] = await chrome.tabs.query({
        active: true,
        currentWindow: true,
      });
      if (tab) {
        chrome.tabs.sendMessage(
          tab.id,
          { type: "EXTRACT_LINKEDIN_JOB" },
          (response) => {
            if (response) {
              displayJobData(response);
            } else {
              fallbackParse(currentUrl);
            }
          }
        );
      } else {
        await fallbackParse(currentUrl);
      }
    } else {
      await fallbackParse(currentUrl);
    }
  } catch (e) {
    hide("loading");
    show("no-job");
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
    const result = await resp.json();
    if (result.status === "ok" && result.data) {
      displayJobData(result.data);
    } else {
      hide("loading");
      show("no-job");
    }
  } catch {
    hide("loading");
    show("no-job");
  }
}

function displayJobData(data) {
  currentJobData = data;
  hide("loading");
  hide("no-job");
  show("job-data");

  document.getElementById("job-company").textContent =
    data.company || "Unknown";
  document.getElementById("job-title").textContent = data.title || "Unknown";
  document.getElementById("job-location").textContent =
    data.location || "Not specified";
}

// --- Track Job ---

document.getElementById("track-btn").addEventListener("click", async () => {
  const btn = document.getElementById("track-btn");
  const statusEl = document.getElementById("track-status");
  btn.disabled = true;
  btn.textContent = "Tracking...";
  clearElement(statusEl);

  const payload = {
    company: currentJobData.company || "Unknown",
    role_title: currentJobData.title || "Unknown Role",
    job_url: currentUrl,
    source: currentJobData.source || "manual",
    department: currentJobData.department || null,
    description_text: currentJobData.description || null,
    salary: currentJobData.salary || null,
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
    renderAlert(statusEl, "error", "Error connecting to backend.");
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

// Run on load
init();
checkBrowsingNudge();
