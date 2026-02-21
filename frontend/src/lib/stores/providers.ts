/**
 * LLM provider configuration store.
 *
 * API keys are stored in localStorage (never sent to our backend
 * except as Authorization headers when cloud LLMs are used).
 * Provider configs are managed locally and synced to the backend
 * via the /settings endpoints.
 */
import { writable } from 'svelte/store';

export interface ProviderConfig {
  id: string;
  label: string;
  apiKeyEnvVar: string;
  apiKey: string;
  baseUrl: string;
  enabled: boolean;
}

export interface AgentModelAssignment {
  role: string;
  label: string;
  provider: string;
  model: string;
}

const STORAGE_KEY = 'storyteller-providers';

const DEFAULT_PROVIDERS: ProviderConfig[] = [
  {
    id: 'ollama',
    label: 'Ollama (Local)',
    apiKeyEnvVar: '',
    apiKey: '',
    baseUrl: 'http://localhost:11434',
    enabled: true,
  },
  {
    id: 'anthropic',
    label: 'Anthropic (Claude)',
    apiKeyEnvVar: 'ANTHROPIC_API_KEY',
    apiKey: '',
    baseUrl: '',
    enabled: false,
  },
  {
    id: 'openai',
    label: 'OpenAI',
    apiKeyEnvVar: 'OPENAI_API_KEY',
    apiKey: '',
    baseUrl: '',
    enabled: false,
  },
  {
    id: 'openai_compat',
    label: 'OpenAI-Compatible',
    apiKeyEnvVar: '',
    apiKey: '',
    baseUrl: '',
    enabled: false,
  },
];

function loadProviders(): ProviderConfig[] {
  try {
    const stored = localStorage.getItem(STORAGE_KEY);
    if (stored) {
      const parsed = JSON.parse(stored) as ProviderConfig[];
      // Merge with defaults to handle new providers added in updates
      return DEFAULT_PROVIDERS.map((def) => {
        const saved = parsed.find((p) => p.id === def.id);
        return saved ? { ...def, ...saved } : def;
      });
    }
  } catch {
    // Corrupted storage — use defaults
  }
  return DEFAULT_PROVIDERS.map((p) => ({ ...p }));
}

function saveProviders(providers: ProviderConfig[]) {
  try {
    // Strip API keys from anything that shouldn't be persisted
    // (we DO persist them locally — they never leave the browser
    // except as headers to the user's own backend)
    localStorage.setItem(STORAGE_KEY, JSON.stringify(providers));
  } catch {
    // Storage full or unavailable
  }
}

function createProviderStore() {
  const { subscribe, set, update } = writable<ProviderConfig[]>(loadProviders());

  return {
    subscribe,
    updateProvider(id: string, changes: Partial<ProviderConfig>) {
      update((providers) => {
        const updated = providers.map((p) =>
          p.id === id ? { ...p, ...changes } : p
        );
        saveProviders(updated);
        return updated;
      });
    },
    setApiKey(id: string, key: string) {
      update((providers) => {
        const updated = providers.map((p) =>
          p.id === id ? { ...p, apiKey: key, enabled: !!key || p.id === 'ollama' } : p
        );
        saveProviders(updated);
        return updated;
      });
    },
    removeApiKey(id: string) {
      update((providers) => {
        const updated = providers.map((p) =>
          p.id === id ? { ...p, apiKey: '', enabled: p.id === 'ollama' } : p
        );
        saveProviders(updated);
        return updated;
      });
    },
    reset() {
      const defaults = DEFAULT_PROVIDERS.map((p) => ({ ...p }));
      saveProviders(defaults);
      set(defaults);
    },
  };
}

export const providers = createProviderStore();

/** Get the list of enabled provider IDs */
export function getEnabledProviders(providerList: ProviderConfig[]): string[] {
  return providerList.filter((p) => p.enabled).map((p) => p.id);
}
