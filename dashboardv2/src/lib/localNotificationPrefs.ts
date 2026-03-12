export interface LocalNotificationPrefs {
  browser_notifications_enabled: boolean;
  quiet_hours_enabled: boolean;
  quiet_hours_start: number | null;
  quiet_hours_end: number | null;
}

const STORAGE_KEY = 'apptrail:local-notification-prefs';
export const LOCAL_NOTIFICATION_PREFS_EVENT = 'apptrail:local-notification-prefs-changed';

export const DEFAULT_LOCAL_NOTIFICATION_PREFS: LocalNotificationPrefs = {
  browser_notifications_enabled: false,
  quiet_hours_enabled: false,
  quiet_hours_start: null,
  quiet_hours_end: null,
};

export function loadLocalNotificationPrefs(): LocalNotificationPrefs {
  if (typeof window === 'undefined') {
    return DEFAULT_LOCAL_NOTIFICATION_PREFS;
  }

  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (!raw) {
      return DEFAULT_LOCAL_NOTIFICATION_PREFS;
    }
    const parsed = JSON.parse(raw) as Partial<LocalNotificationPrefs>;
    return {
      browser_notifications_enabled: Boolean(parsed.browser_notifications_enabled),
      quiet_hours_enabled: Boolean(parsed.quiet_hours_enabled),
      quiet_hours_start: typeof parsed.quiet_hours_start === 'number' ? parsed.quiet_hours_start : null,
      quiet_hours_end: typeof parsed.quiet_hours_end === 'number' ? parsed.quiet_hours_end : null,
    };
  } catch {
    return DEFAULT_LOCAL_NOTIFICATION_PREFS;
  }
}

export function saveLocalNotificationPrefs(prefs: LocalNotificationPrefs) {
  if (typeof window === 'undefined') {
    return;
  }

  window.localStorage.setItem(STORAGE_KEY, JSON.stringify(prefs));
  window.dispatchEvent(new CustomEvent(LOCAL_NOTIFICATION_PREFS_EVENT, { detail: prefs }));
}

export function isWithinLocalQuietHours(prefs: LocalNotificationPrefs, now = new Date()) {
  if (!prefs.quiet_hours_enabled) return false;
  if (prefs.quiet_hours_start == null || prefs.quiet_hours_end == null) return false;

  const hour = now.getHours();
  if (prefs.quiet_hours_start === prefs.quiet_hours_end) return true;
  if (prefs.quiet_hours_start < prefs.quiet_hours_end) {
    return hour >= prefs.quiet_hours_start && hour < prefs.quiet_hours_end;
  }
  return hour >= prefs.quiet_hours_start || hour < prefs.quiet_hours_end;
}
