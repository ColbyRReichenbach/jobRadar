import {
  DEFAULT_API_BASE,
  buildApiUrl,
  clearApiKey,
  getApiBase,
  getApiKey,
  setApiBase,
  setApiKey,
} from "./config.js";

function isNetworkError(error) {
  return error instanceof TypeError;
}

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
	      await setApiKey(apiKey);
	      statusEl.className = "status success";
	      statusEl.textContent = `Connected successfully to ${apiBase} as ${data.user?.email || "your account"}. This key is stored locally in Chrome until you clear it.`;
    } else {
      statusEl.className = "status error";
      statusEl.textContent = `Validation failed (${resp.status}). Generate a fresh key from dashboard Settings and try again.`;
    }
  } catch (e) {
    statusEl.className = "status error";
    statusEl.textContent = isNetworkError(e)
      ? "Could not reach the backend. Check your network connection and backend URL."
      : "Could not save extension settings.";
  }

  btn.disabled = false;
	  btn.textContent = "Save & Validate";
	});

document.getElementById("clearBtn").addEventListener("click", async () => {
  const statusEl = document.getElementById("status");
  await clearApiKey();
  document.getElementById("apiKey").value = "";
  statusEl.className = "status info";
  statusEl.textContent = "Stored extension key cleared from this browser. Revoke the key in dashboard Settings to invalidate it everywhere.";
});

// Restore current setup state without displaying the full saved key.
Promise.all([getApiKey(), getApiBase()]).then(
  ([apiKey, apiBase]) => {
    if (apiKey) {
      const statusEl = document.getElementById("status");
      statusEl.className = "status info";
      statusEl.textContent = "A key is already saved locally. Enter a new key to replace it or clear the stored key below.";
    }
    document.getElementById("apiBase").value = apiBase || DEFAULT_API_BASE;
  }
);
