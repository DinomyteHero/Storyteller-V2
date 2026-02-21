/**
 * Preset store — thin client over backend /v2/settings/presets API.
 * Caches system + user presets for display in settings UI.
 */
import { writable, get } from 'svelte/store';
import {
  getPresets,
  createPreset as apiCreate,
  updatePreset as apiUpdate,
  deletePreset as apiDelete,
  type Preset,
} from '$lib/api/campaigns';

export type { Preset };

function createPresetStore() {
  const { subscribe, set } = writable<Preset[]>([]);

  return {
    subscribe,

    async load() {
      try {
        const all = await getPresets();
        set(all);
      } catch {
        // Backend unreachable
      }
    },

    async create(
      name: string,
      description: string,
      roleConfigs: Record<string, { provider: string; model: string }>
    ): Promise<Preset | null> {
      try {
        const created = await apiCreate(name, description, roleConfigs);
        // Reload to get consistent list
        await this.load();
        return created;
      } catch {
        return null;
      }
    },

    async update(
      presetId: string,
      updates: { name?: string; description?: string; role_configs?: Record<string, { provider: string; model: string }> }
    ): Promise<Preset | null> {
      try {
        const updated = await apiUpdate(presetId, updates);
        await this.load();
        return updated;
      } catch {
        return null;
      }
    },

    async remove(presetId: string): Promise<boolean> {
      try {
        await apiDelete(presetId);
        await this.load();
        return true;
      } catch {
        return false;
      }
    },

    getSystemPresets(): Preset[] {
      return get({ subscribe }).filter((p) => p.is_system);
    },

    getUserPresets(): Preset[] {
      return get({ subscribe }).filter((p) => !p.is_system);
    },
  };
}

export const presets = createPresetStore();
