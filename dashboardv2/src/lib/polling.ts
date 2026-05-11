const rawIntervalSeconds = import.meta.env.VITE_DASHBOARD_POLL_INTERVAL_SECONDS;

function parseIntervalMs(rawValue: string | undefined): number {
  if (rawValue === undefined || rawValue === '') {
    return import.meta.env.DEV ? 30_000 : 0;
  }

  const seconds = Number(rawValue);
  if (!Number.isFinite(seconds) || seconds <= 0) {
    return 0;
  }

  return Math.max(seconds * 1000, 10_000);
}

export const DASHBOARD_POLL_INTERVAL_MS = parseIntervalMs(rawIntervalSeconds);

export function canRunBackgroundRefresh(): boolean {
  return typeof document === 'undefined' || document.visibilityState === 'visible';
}
