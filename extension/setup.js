const API_BASE = "http://localhost:8000";

document.getElementById("saveBtn").addEventListener("click", async () => {
  const apiKey = document.getElementById("apiKey").value.trim();
  const statusEl = document.getElementById("status");
  const btn = document.getElementById("saveBtn");

  if (!apiKey) {
    statusEl.className = "status error";
    statusEl.textContent = "Please enter an API key.";
    return;
  }

  btn.disabled = true;
  btn.textContent = "Validating...";

  try {
    const resp = await fetch(`${API_BASE}/api/auth/api-key/validate`, {
      method: "POST",
      headers: { Authorization: `Bearer ${apiKey}` },
    });

    if (resp.ok) {
      const data = await resp.json();
      await chrome.storage.local.set({ apiKey });
      statusEl.className = "status success";
      statusEl.textContent = `Connected successfully as ${data.user?.email || "your account"}. You can close this tab.`;
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
chrome.storage.local.get("apiKey", (data) => {
  if (data.apiKey) {
    document.getElementById("apiKey").value = data.apiKey;
  }
});
