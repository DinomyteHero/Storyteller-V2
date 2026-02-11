/**
 * Formatting utilities — ported from streamlit_app.py.
 */
import { LOCATION_DISPLAY_NAMES } from './constants';

/**
 * Convert a raw location ID into a readable Star Wars-appropriate name.
 * Uses a known lookup table first, then falls back to generic cleanup.
 */
export function humanizeLocation(locId: string | null | undefined): string {
  if (!locId || locId === '—') return '—';
  const raw = locId.trim();
  if (!raw) return '—';

  // Check known display names
  const display = LOCATION_DISPLAY_NAMES[raw.toLowerCase()];
  if (display) return display;

  // Fallback: strip prefix and title-case
  let cleaned = raw;
  for (const prefix of ['loc-', 'loc_', 'location-', 'location_']) {
    if (cleaned.toLowerCase().startsWith(prefix)) {
      cleaned = cleaned.slice(prefix.length);
      break;
    }
  }
  cleaned = cleaned.replace(/[-_]/g, ' ').trim();
  if (!cleaned) return raw;
  return cleaned
    .split(' ')
    .map((w) => w.charAt(0).toUpperCase() + w.slice(1).toLowerCase())
    .join(' ');
}

/**
 * Return [day, timeStr] from total world time in minutes.
 * day = (minutes // 1440) + 1; timeStr = HH:MM from remainder.
 */
export function worldClockParts(worldTimeMinutes: number | null | undefined): [number, string] {
  let m = worldTimeMinutes ?? 0;
  if (m < 0) m = 0;
  const day = Math.floor(m / 1440) + 1;
  const remainder = m % 1440;
  const hour = Math.floor(remainder / 60);
  const minute = remainder % 60;
  const timeStr = `${String(hour).padStart(2, '0')}:${String(minute).padStart(2, '0')}`;
  return [day, timeStr];
}

/**
 * Format a time delta in minutes as "+N min" or "+N hrs".
 * Returns null if minutes <= 0.
 */
export function formatTimeDelta(minutes: number | null | undefined): string | null {
  const m = minutes ?? 0;
  if (m <= 0) return null;
  if (m >= 60) {
    const hrs = m / 60;
    return hrs === Math.floor(hrs) ? `+${hrs} hrs` : `+${hrs.toFixed(1)} hrs`;
  }
  return `+${m} min`;
}

/**
 * Safe integer conversion with fallback.
 */
export function safeInt(val: unknown, fallback = 0): number {
  if (typeof val === 'number') return Math.floor(val);
  const n = Number(val);
  return Number.isFinite(n) ? Math.floor(n) : fallback;
}
