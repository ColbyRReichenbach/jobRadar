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
    document.getElementById("no-job").innerHTML =
      '<p class="alert alert-error">Failed to load job data.</p>';
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
  statusEl.innerHTML = "";

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
      statusEl.innerHTML =
        '<div class="alert alert-success">Job tracked successfully!</div>';
      btn.textContent = "Tracked";

      // Find contacts
      const domain = extractDomain(currentUrl);
      await findContacts(appData.id, payload.company, domain);
    } else if (resp.status === 409) {
      const detail = (await resp.json()).detail;
      statusEl.innerHTML = `<div class="alert alert-warning">Already tracked: ${detail.existing.company} - ${detail.existing.role_title}</div>`;
      btn.textContent = "Already Tracked";
    } else {
      statusEl.innerHTML =
        '<div class="alert alert-error">Failed to track job.</div>';
      btn.disabled = false;
      btn.textContent = "Track This Job";
    }
  } catch (e) {
    statusEl.innerHTML =
      '<div class="alert alert-error">Error connecting to backend.</div>';
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
    listEl.innerHTML = "";

    for (const contact of contacts) {
      const card = document.createElement("div");
      card.className = "contact-card";
      card.innerHTML = `
        <div class="contact-name">${contact.name || "Unknown"}</div>
        <div class="contact-title">${contact.title || ""}</div>
        ${contact.email ? `<div class="contact-email">${contact.email}</div>` : ""}
        ${contact.confidence_score ? `<div style="font-size:11px;color:#94a3b8;">Confidence: ${Math.round(contact.confidence_score * 100)}%</div>` : ""}
        <label class="contact-check">
          <input type="checkbox" data-contact-id="${contact.id}" ${contact.reached_out ? "checked" : ""}>
          I reached out to this person
        </label>
      `;
      listEl.appendChild(card);
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
      document.getElementById("linkedin-link").innerHTML = `
        <a href="${data.linkedin_search_url}" target="_blank" style="display:block;margin-top:8px;font-size:12px;">
          Search UNC alumni at ${company} on LinkedIn
        </a>
      `;
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
  nudgeEl.innerHTML = `
    <div class="nudge">
      <div class="nudge-title">Interested in ${domain}?</div>
      <div class="nudge-text">You've visited their careers page ${visits.visitCount} times. Want to track this company?</div>
      <button class="btn-nudge" id="nudge-track-btn">Save to Pipeline</button>
    </div>
  `;
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
        nudgeEl.innerHTML = `<div class="nudge"><div class="nudge-title">Saved!</div><div class="nudge-text">${domain} added to your pipeline.</div></div>`;
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
