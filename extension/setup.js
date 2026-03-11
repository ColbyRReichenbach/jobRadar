import { DEFAULT_API_BASE, buildApiUrl, getApiBase, setApiBase } from "./config.js";

document.getElementById("saveBtn").addEventListener("click", async () => {
  const apiKey = document.getElementById("apiKey").value.trim();
  const apiBaseInput = document.getElementById("apiBase");
  const statusEl = document.getElementById("status");
  const btn = document.getElementById("saveBtn");
  let apiBase;

  if (!apiKey) {
    statusEl.className = "status error";
    statusEl.textContent = "Please enter an API key.";
    return;
  }

  try {
    apiBase = await setApiBase(apiBaseInput.value);
  } catch (error) {
    statusEl.className = "status error";
    statusEl.textContent = error.message;
    return;
  }

  btn.disabled = true;
  btn.textContent = "Validating...";

  try {
    const resp = await fetch(buildApiUrl(apiBase, "/api/auth/api-key/validate"), {
      method: "POST",
      headers: { Authorization: `Bearer ${apiKey}` },
    });

    if (resp.ok) {
      const data = await resp.json();
      await chrome.storage.local.set({ apiKey });
      statusEl.className = "status success";
      statusEl.textContent = `Connected successfully to ${apiBase} as ${data.user?.email || "your account"}. You can close this tab.`;
    } else {
      statusEl.className = "status error";
      statusEl.textContent = `Validation failed (${resp.status}). Generate a fresh key from dashboard Settings and try again.`;
    }
  } catch (e) {
    statusEl.className = "status error";
    statusEl.textContent = "Could not reach backend. Is the server running?";
  }

  btn.disabled = false;
  btn.textContent = "Save & Validate";
});

// Pre-fill if key already stored
Promise.all([chrome.storage.local.get("apiKey"), getApiBase()]).then(
  ([data, apiBase]) => {
    if (data.apiKey) {
      document.getElementById("apiKey").value = data.apiKey;
    }
    document.getElementById("apiBase").value = apiBase || DEFAULT_API_BASE;
  }
);
