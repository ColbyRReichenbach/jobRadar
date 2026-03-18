// macOS-style toast notification for trackable job pages.
// Shows a floating pill in the bottom-right corner with slide-up animation.
// Guarded against duplicate injection with per-URL cooldown.

(function () {
  // Per-URL cooldown: don't re-show toast for the same URL within 30s.
  // Using a per-URL key means navigating to a different job still triggers the toast.
  const COOLDOWN_MS = 30000;
  const now = Date.now();
  const currentUrl = window.location.href;

  // Store cooldown data on window to survive re-injection
  if (!window.__apptrailToastCooldowns) {
    window.__apptrailToastCooldowns = {};
  }

  const lastShown = window.__apptrailToastCooldowns[currentUrl] || 0;
  if (now - lastShown < COOLDOWN_MS) return;

  // Remove any existing toast before creating a new one
  const existing = document.getElementById("apptrail-toast");
  if (existing) existing.remove();

  window.__apptrailToastCooldowns[currentUrl] = now;

  // --- Toast container ---
  const toast = document.createElement("div");
  toast.id = "apptrail-toast";
  toast.setAttribute("style", [
    "position: fixed",
    "bottom: 20px",
    "right: 20px",
    "z-index: 2147483647",
    "display: flex",
    "align-items: center",
    "gap: 10px",
    "padding: 10px 14px",
    "background: #0f172a",
    "color: white",
    "font-family: -apple-system, BlinkMacSystemFont, 'Inter', 'Segoe UI', system-ui, sans-serif",
    "font-size: 13px",
    "font-weight: 500",
    "border-radius: 12px",
    "box-shadow: 0 8px 32px rgba(0,0,0,0.18), 0 2px 8px rgba(0,0,0,0.12)",
    "transform: translateY(120%) scale(0.95)",
    "opacity: 0",
    "transition: transform 0.35s cubic-bezier(0.16, 1, 0.3, 1), opacity 0.35s ease",
    "max-width: 320px",
    "backdrop-filter: blur(12px)",
    "-webkit-backdrop-filter: blur(12px)",
    "letter-spacing: -0.01em",
    "pointer-events: auto",
  ].join(";"));

  // --- Green dot ---
  const dot = document.createElement("span");
  dot.setAttribute("style", [
    "width: 8px",
    "height: 8px",
    "border-radius: 50%",
    "background: #22c55e",
    "flex-shrink: 0",
    "box-shadow: 0 0 6px rgba(34, 197, 94, 0.5)",
  ].join(";"));
  toast.appendChild(dot);

  // --- Text ---
  const text = document.createElement("span");
  text.setAttribute("style", "flex: 1; line-height: 1.3;");
  text.textContent = "Job posting detected";
  toast.appendChild(text);

  // --- Open button ---
  const openBtn = document.createElement("button");
  openBtn.textContent = "Open";
  openBtn.setAttribute("style", [
    "background: rgba(255,255,255,0.15)",
    "color: white",
    "border: none",
    "border-radius: 8px",
    "padding: 5px 12px",
    "font-size: 12px",
    "font-weight: 600",
    "cursor: pointer",
    "font-family: -apple-system, BlinkMacSystemFont, 'Inter', 'Segoe UI', system-ui, sans-serif",
    "transition: background 0.15s",
    "white-space: nowrap",
    "flex-shrink: 0",
  ].join(";"));
  openBtn.addEventListener("mouseenter", () => {
    openBtn.style.background = "rgba(255,255,255,0.25)";
  });
  openBtn.addEventListener("mouseleave", () => {
    openBtn.style.background = "rgba(255,255,255,0.15)";
  });
  openBtn.addEventListener("click", () => {
    chrome.runtime.sendMessage({ type: "OPEN_SIDE_PANEL" });
    dismissToast();
  });
  toast.appendChild(openBtn);

  // --- "Not a job" button ---
  const notJobBtn = document.createElement("button");
  notJobBtn.textContent = "Not a job";
  notJobBtn.setAttribute("style", [
    "background: none",
    "border: none",
    "color: rgba(255,255,255,0.4)",
    "font-size: 11px",
    "cursor: pointer",
    "font-family: -apple-system, BlinkMacSystemFont, 'Inter', 'Segoe UI', system-ui, sans-serif",
    "transition: color 0.15s",
    "white-space: nowrap",
    "flex-shrink: 0",
    "padding: 2px 4px",
  ].join(";"));
  notJobBtn.addEventListener("mouseenter", () => {
    notJobBtn.style.color = "rgba(255,255,255,0.8)";
  });
  notJobBtn.addEventListener("mouseleave", () => {
    notJobBtn.style.color = "rgba(255,255,255,0.4)";
  });
  notJobBtn.addEventListener("click", () => {
    // Send false positive report to backend
    chrome.runtime.sendMessage({
      type: "REPORT_FALSE_POSITIVE",
      url: window.location.href,
      domain: window.location.hostname,
    });
    // Show brief confirmation
    text.textContent = "Thanks! Reported.";
    openBtn.style.display = "none";
    notJobBtn.style.display = "none";
    setTimeout(() => dismissToast(), 1500);
  });
  toast.appendChild(notJobBtn);

  // --- Close button ---
  const closeBtn = document.createElement("button");
  closeBtn.textContent = "\u00D7";
  closeBtn.setAttribute("style", [
    "background: none",
    "border: none",
    "color: rgba(255,255,255,0.5)",
    "font-size: 16px",
    "cursor: pointer",
    "padding: 0 2px",
    "line-height: 1",
    "transition: color 0.15s",
    "flex-shrink: 0",
  ].join(";"));
  closeBtn.addEventListener("mouseenter", () => {
    closeBtn.style.color = "rgba(255,255,255,0.9)";
  });
  closeBtn.addEventListener("mouseleave", () => {
    closeBtn.style.color = "rgba(255,255,255,0.5)";
  });
  closeBtn.addEventListener("click", () => {
    dismissToast();
  });
  toast.appendChild(closeBtn);

  // --- Dismiss ---
  let dismissed = false;
  function dismissToast() {
    if (dismissed) return;
    dismissed = true;
    toast.style.transform = "translateY(120%) scale(0.95)";
    toast.style.opacity = "0";
    setTimeout(() => toast.remove(), 350);
  }

  // --- Mount and animate in ---
  // Wait for body to be available (might run at document_idle but just in case)
  const mount = document.body || document.documentElement;
  mount.appendChild(toast);

  // Use double-rAF to ensure the initial off-screen state is painted before animating
  requestAnimationFrame(() => {
    requestAnimationFrame(() => {
      toast.style.transform = "translateY(0) scale(1)";
      toast.style.opacity = "1";
    });
  });

  // Auto-dismiss after 8 seconds
  setTimeout(() => {
    if (document.getElementById("apptrail-toast")) {
      dismissToast();
    }
  }, 8000);
})();
