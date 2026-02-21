/**
 * App preferences store — synced with backend DB.
 *
 * Preferences are stored in the backend (app_preferences table) and
 * fetched/updated via the /v2/settings/preferences API.
 */
import { writable } from 'svelte/store';
import { apiFetch } from '$lib/api/client';

export interface AppPreferences {
  enable_choice_fallbacks: boolean;
}

const DEFAULTS: AppPreferences = {
  enable_choice_fallbacks: true,
};

function parsePreferences(raw: Record<string, string>): AppPreferences {
  return {
    enable_choice_fallbacks: (raw.enable_choice_fallbacks ?? 'true') !== 'false',
  };
}

function createPreferencesStore() {
  const { subscribe, set } = writable<AppPreferences>({ ...DEFAULTS });

  return {
    subscribe,

    /** Fetch preferences from backend. Call on settings page mount. */
    async load() {
      try {
        const resp = await apiFetch<{ preferences: Record<string, string> }>(
          '/v2/settings/preferences'
        );
        set(parsePreferences(resp.preferences));
      } catch {
        // Backend unreachable — use defaults
      }
    },

    /** Toggle the choice fallbacks preference and sync to backend. */
    async setChoiceFallbacks(enabled: boolean) {
      set({ ...DEFAULTS, enable_choice_fallbacks: enabled });
      try {
        const resp = await apiFetch<{ preferences: Record<string, string> }>(
          '/v2/settings/preferences',
          {
            method: 'PUT',
            body: JSON.stringify({
              preferences: { enable_choice_fallbacks: String(enabled) },
            }),
          }
        );
        set(parsePreferences(resp.preferences));
      } catch {
        // Revert on failure
        set({ ...DEFAULTS, enable_choice_fallbacks: !enabled });
      }
    },
  };
}

export const preferences = createPreferencesStore();
