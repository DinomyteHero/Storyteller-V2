/**
 * LLM provider configuration store — V12.0 refactor.
 *
 * API keys are now stored in the backend DB (via /v2/settings/providers).
 * This store is a thin cache over the backend API. No more localStorage keys.
 */
import { writable, get } from 'svelte/store';
import {
  getProviders,
  setProviderKey as apiSetKey,
  removeProviderKey as apiRemoveKey,
  testProvider as apiTestProvider,
  type ProviderStatus,
  type TestResult,
} from '$lib/api/campaigns';

export type { ProviderStatus };

/** Re-export for backward compat with existing imports */
export interface ProviderConfig {
  id: string;
  label: string;
  apiKeyEnvVar: string;
  apiKey: string;
  baseUrl: string;
  enabled: boolean;
}

function createProviderStore() {
  const { subscribe, set, update } = writable<ProviderStatus[]>([]);
  let loaded = false;

  return {
    subscribe,

    /** Fetch provider statuses from backend. Call on app init. */
    async load() {
      try {
        const statuses = await getProviders();
        set(statuses);
        loaded = true;
      } catch {
        // Backend unreachable — leave empty, will retry
      }
    },

    /** Whether the store has been loaded at least once. */
    get loaded() {
      return loaded;
    },

    /** Set or update an API key in the backend DB. */
    async setKey(providerId: string, apiKey: string): Promise<ProviderStatus | null> {
      try {
        const updated = await apiSetKey(providerId, apiKey);
        update((list) =>
          list.map((p) => (p.provider_id === providerId ? updated : p))
        );
        return updated;
      } catch {
        return null;
      }
    },

    /** Remove an API key from the backend DB. */
    async removeKey(providerId: string): Promise<ProviderStatus | null> {
      try {
        const updated = await apiRemoveKey(providerId);
        update((list) =>
          list.map((p) => (p.provider_id === providerId ? updated : p))
        );
        return updated;
      } catch {
        return null;
      }
    },

    /** Test provider connectivity. */
    async test(providerId: string): Promise<TestResult> {
      return apiTestProvider(providerId);
    },

    /** Check if any cloud provider has a key configured. */
    get hasAnyCloudKey(): boolean {
      const list = get({ subscribe });
      return list.some((p) => p.has_key);
    },

    /** Get list of provider IDs that have keys configured. */
    getConnectedProviders(): ProviderStatus[] {
      return get({ subscribe }).filter((p) => p.has_key);
    },

    // ── Backward compat shims ──────────────────────────────

    /** @deprecated Use setKey() instead */
    setApiKey(id: string, key: string) {
      // Fire-and-forget for backward compat (old wizard/settings code)
      this.setKey(id, key);
    },

    /** @deprecated Use removeKey() instead */
    removeApiKey(id: string) {
      this.removeKey(id);
    },

    /** @deprecated Use load() instead */
    updateProvider(_id: string, _changes: Partial<ProviderConfig>) {
      // No-op — base URLs are now in the backend registry
    },

    reset() {
      set([]);
      loaded = false;
    },
  };
}

export const providers = createProviderStore();

/** Get the list of connected provider IDs */
export function getEnabledProviders(providerList: ProviderStatus[]): string[] {
  return providerList.filter((p) => p.has_key).map((p) => p.provider_id);
}
