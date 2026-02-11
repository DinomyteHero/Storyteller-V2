/**
 * UI state store — theme, toggles, drawer state.
 *
 * Persisted to localStorage for cross-session preference retention.
 */
import { writable } from 'svelte/store';
import { browser } from '$app/environment';
import { DEFAULT_THEME } from '$lib/themes/tokens';

const STORAGE_KEY = 'storyteller-ui-prefs';

interface UIPrefs {
  theme: string;
  enableStreaming: boolean;
  enableTypewriter: boolean;
  showDebug: boolean;
  drawerOpen: boolean;
  drawerTab: string;
}

const DEFAULT_PREFS: UIPrefs = {
  theme: DEFAULT_THEME,
  enableStreaming: true,
  enableTypewriter: false,
  showDebug: false,
  drawerOpen: false,
  drawerTab: 'character',
};

function loadPrefs(): UIPrefs {
  if (!browser) return { ...DEFAULT_PREFS };
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (raw) {
      const parsed = JSON.parse(raw);
      return { ...DEFAULT_PREFS, ...parsed };
    }
  } catch {
    // Ignore corrupt storage
  }
  return { ...DEFAULT_PREFS };
}

function savePrefs(prefs: UIPrefs): void {
  if (!browser) return;
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(prefs));
  } catch {
    // Ignore quota errors
  }
}

function createUIStore() {
  const initial = loadPrefs();
  const { subscribe, set, update } = writable<UIPrefs>(initial);

  // Auto-save on change
  subscribe((val) => savePrefs(val));

  return {
    subscribe,
    set,
    update,

    setTheme(name: string) {
      update((s) => ({ ...s, theme: name }));
    },

    toggleStreaming() {
      update((s) => ({ ...s, enableStreaming: !s.enableStreaming }));
    },

    toggleTypewriter() {
      update((s) => ({ ...s, enableTypewriter: !s.enableTypewriter }));
    },

    toggleDebug() {
      update((s) => ({ ...s, showDebug: !s.showDebug }));
    },

    toggleDrawer() {
      update((s) => ({ ...s, drawerOpen: !s.drawerOpen }));
    },

    openDrawer(tab?: string) {
      update((s) => ({ ...s, drawerOpen: true, drawerTab: tab ?? s.drawerTab }));
    },

    closeDrawer() {
      update((s) => ({ ...s, drawerOpen: false }));
    },

    setDrawerTab(tab: string) {
      update((s) => ({ ...s, drawerTab: tab }));
    },
  };
}

export const ui = createUIStore();
