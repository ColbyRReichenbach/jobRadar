// Toast notification for trackable job pages.
// Visually matches the AppTrail dashboard and side panel design language:
// warm off-white tones, Inter font, indigo accents, subtle card styling.
// Guarded against duplicate injection with per-URL cooldown.

(function () {
  const extracted = typeof window.__apptrailExtract === "function"
    ? window.__apptrailExtract()
    : null;
  if (extracted?._page_state === "unavailable") return;
  if (!extracted || (!extracted.title && !extracted.company)) return;

  // Per-URL cooldown: don't re-show toast for the same URL within 30s.
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
  // Matches the app's card style: white bg, 12px radius, subtle border + shadow
  const toast = document.createElement("div");
  toast.id = "apptrail-toast";
  toast.setAttribute("style", [
    "position: fixed",
    "bottom: 20px",
    "right: 20px",
    "z-index: 2147483647",
    "display: flex",
    "align-items: center",
    "gap: 12px",
    "padding: 12px 16px",
    "background: #ffffff",
    "color: #1e293b",
    "font-family: 'Inter', ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, sans-serif",
    "font-size: 13px",
    "font-weight: 500",
    "border-radius: 14px",
    "border: 1px solid rgba(226, 232, 240, 0.8)",
    "box-shadow: 0 8px 32px rgba(0,0,0,0.08), 0 2px 8px rgba(0,0,0,0.04)",
    "transform: translateY(120%) scale(0.97)",
    "opacity: 0",
    "transition: transform 0.4s cubic-bezier(0.16, 1, 0.3, 1), opacity 0.35s ease",
    "max-width: 360px",
    "letter-spacing: -0.01em",
    "pointer-events: auto",
    "-webkit-font-smoothing: antialiased",
  ].join(";"));

  // --- Logo icon (indigo circle with A) ---
  const logoWrap = document.createElement("span");
  logoWrap.setAttribute("style", [
    "width: 32px",
    "height: 32px",
    "border-radius: 9px",
    "background: #0f172a",
    "display: flex",
    "align-items: center",
    "justify-content: center",
    "flex-shrink: 0",
  ].join(";"));
  // Simple trail/path SVG matching the app's favicon
  logoWrap.innerHTML = '<svg width="18" height="18" viewBox="0 0 24 24" fill="none"><path d="M4 20L12 4L20 20" stroke="white" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"/><path d="M8 13H16" stroke="white" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" stroke-dasharray="4 4"/></svg>';
  toast.appendChild(logoWrap);

  // --- Text block ---
  const textBlock = document.createElement("div");
  textBlock.setAttribute("style", "flex: 1; min-width: 0;");

  const title = document.createElement("div");
  title.setAttribute("style", [
    "font-size: 13px",
    "font-weight: 600",
    "color: #0f172a",
    "line-height: 1.3",
    "letter-spacing: -0.01em",
  ].join(";"));
  title.textContent = "Job posting detected";
  textBlock.appendChild(title);

  const subtitle = document.createElement("div");
  subtitle.setAttribute("style", [
    "font-size: 11px",
    "font-weight: 400",
    "color: #94a3b8",
    "line-height: 1.3",
    "margin-top: 1px",
  ].join(";"));
  subtitle.textContent = "Open AppTrail to track this listing";
  textBlock.appendChild(subtitle);

  toast.appendChild(textBlock);

  // --- Open button (primary indigo) ---
  const openBtn = document.createElement("button");
  openBtn.textContent = "Open";
  openBtn.setAttribute("style", [
    "background: linear-gradient(135deg, #0f172a 0%, #1d4ed8 100%)",
    "color: white",
    "border: none",
    "border-radius: 9px",
    "padding: 6px 14px",
    "font-size: 12px",
    "font-weight: 600",
    "cursor: pointer",
    "font-family: 'Inter', ui-sans-serif, system-ui, sans-serif",
    "transition: box-shadow 0.2s, transform 0.15s",
    "white-space: nowrap",
    "flex-shrink: 0",
    "box-shadow: 0 2px 8px rgba(15, 23, 42, 0.15)",
    "letter-spacing: -0.01em",
  ].join(";"));
  openBtn.addEventListener("mouseenter", () => {
    openBtn.style.boxShadow = "0 4px 12px rgba(15, 23, 42, 0.25)";
    openBtn.style.transform = "translateY(-1px)";
  });
  openBtn.addEventListener("mouseleave", () => {
    openBtn.style.boxShadow = "0 2px 8px rgba(15, 23, 42, 0.15)";
    openBtn.style.transform = "translateY(0)";
  });
  openBtn.addEventListener("click", () => {
    chrome.runtime.sendMessage({ type: "OPEN_SIDE_PANEL" });
    dismissToast();
  });
  toast.appendChild(openBtn);

  // --- "Not a job" link (muted, matches app secondary text) ---
  const notJobBtn = document.createElement("button");
  notJobBtn.textContent = "Not a job";
  notJobBtn.setAttribute("style", [
    "background: none",
    "border: none",
    "color: #94a3b8",
    "font-size: 11px",
    "font-weight: 500",
    "cursor: pointer",
    "font-family: 'Inter', ui-sans-serif, system-ui, sans-serif",
    "transition: color 0.15s",
    "white-space: nowrap",
    "flex-shrink: 0",
    "padding: 2px 4px",
  ].join(";"));
  notJobBtn.addEventListener("mouseenter", () => {
    notJobBtn.style.color = "#64748b";
  });
  notJobBtn.addEventListener("mouseleave", () => {
    notJobBtn.style.color = "#94a3b8";
  });
  notJobBtn.addEventListener("click", () => {
    // Send false positive report to backend
    chrome.runtime.sendMessage({
      type: "REPORT_FALSE_POSITIVE",
      url: window.location.href,
      domain: window.location.hostname,
    });
    // Show brief confirmation matching app's success alert style
    title.textContent = "Reported";
    subtitle.textContent = "Thanks! We won't show this again.";
    title.style.color = "#065f46";
    openBtn.style.display = "none";
    notJobBtn.style.display = "none";
    closeBtn.style.display = "none";
    // Swap logo bg to success green
    logoWrap.style.background = "#ecfdf5";
    logoWrap.innerHTML = '<svg width="16" height="16" viewBox="0 0 16 16" fill="none"><path d="M3 8.5L6.5 12L13 4" stroke="#059669" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg>';
    setTimeout(() => dismissToast(), 1800);
  });
  toast.appendChild(notJobBtn);

  // --- Close button (subtle, slate) ---
  const closeBtn = document.createElement("button");
  closeBtn.innerHTML = '<svg width="14" height="14" viewBox="0 0 16 16" fill="none"><path d="M4 4L12 12M12 4L4 12" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/></svg>';
  closeBtn.setAttribute("style", [
    "background: none",
    "border: none",
    "color: #cbd5e1",
    "cursor: pointer",
    "padding: 2px",
    "line-height: 0",
    "transition: color 0.15s",
    "flex-shrink: 0",
    "border-radius: 6px",
  ].join(";"));
  closeBtn.addEventListener("mouseenter", () => {
    closeBtn.style.color = "#64748b";
  });
  closeBtn.addEventListener("mouseleave", () => {
    closeBtn.style.color = "#cbd5e1";
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
    toast.style.transform = "translateY(120%) scale(0.97)";
    toast.style.opacity = "0";
    setTimeout(() => toast.remove(), 400);
  }

  // --- Mount and animate in ---
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
