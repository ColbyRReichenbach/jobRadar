export const DEFAULT_API_BASE = "https://api.apptrail.com";

const API_BASE_STORAGE_KEY = "apiBase";
const API_KEY_STORAGE_KEY = "apiKey";
const LOCAL_API_BASE_PATTERN = /^http:\/\/(?:localhost|127\.0\.0\.1)(?::\d+)?$/;

function trimTrailingSlash(value) {
  return value.endsWith("/") ? value.slice(0, -1) : value;
}

export function normalizeApiBase(value) {
  const candidate = (value || "").trim();
  if (!candidate) {
    return DEFAULT_API_BASE;
  }

  let parsed;
  try {
    parsed = new URL(candidate);
  } catch {
    throw new Error("Enter a valid backend URL.");
  }

  const normalizedOrigin = `${parsed.protocol}//${parsed.host}`;
  const normalizedPath = trimTrailingSlash(parsed.pathname || "");
  if (normalizedPath && normalizedPath !== "/") {
    throw new Error("Backend URL must point to the API root.");
  }

  if (normalizedOrigin === DEFAULT_API_BASE) {
    return DEFAULT_API_BASE;
  }

  if (LOCAL_API_BASE_PATTERN.test(normalizedOrigin)) {
    return normalizedOrigin;
  }

  throw new Error(
    "Use https://api.apptrail.com or a local http://localhost URL."
  );
}

export async function getApiBase() {
  const data = await chrome.storage.local.get(API_BASE_STORAGE_KEY);
  try {
    return normalizeApiBase(data[API_BASE_STORAGE_KEY]);
  } catch {
    return DEFAULT_API_BASE;
  }
}

export async function setApiBase(value) {
  const apiBase = normalizeApiBase(value);
  await chrome.storage.local.set({ [API_BASE_STORAGE_KEY]: apiBase });
  return apiBase;
}

export async function getApiKey() {
  const data = await chrome.storage.local.get(API_KEY_STORAGE_KEY);
  return data[API_KEY_STORAGE_KEY] || "";
}

export function buildApiUrl(apiBase, path) {
  if (path.startsWith("http://") || path.startsWith("https://")) {
    return path;
  }
  const normalizedPath = path.startsWith("/") ? path : `/${path}`;
  return `${apiBase}${normalizedPath}`;
}
