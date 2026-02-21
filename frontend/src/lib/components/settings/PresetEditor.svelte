<!--
  PresetEditor: Modal for creating/editing custom LLM presets.
  Each preset maps agent roles to specific provider+model combos.
-->
<script lang="ts">
  import { providers, type ProviderStatus } from '$lib/stores/providers';
  import type { Preset } from '$lib/api/campaigns';

  interface Props {
    /** If editing an existing preset, pass it here. Null = create mode. */
    preset?: Preset | null;
    onSave: (name: string, description: string, roleConfigs: Record<string, { provider: string; model: string }>) => void;
    onCancel: () => void;
  }

  let { preset = null, onSave, onCancel }: Props = $props();

  const AGENT_CATEGORIES: Record<string, { label: string; roles: string[] }> = {
    narrative: {
      label: 'Narrative',
      roles: ['narrator', 'director', 'choice_crafter', 'companion_system'],
    },
    world: {
      label: 'World Building',
      roles: ['bible', 'world_mind', 'era_forge', 'architect'],
    },
    character: {
      label: 'Character & Memory',
      roles: ['biographer', 'casting', 'memory', 'psych_archivist', 'progression'],
    },
    structure: {
      label: 'Structure',
      roles: ['arc_weaver', 'arc_screenplay', 'continuity', 'quest_weaver'],
    },
    special: {
      label: 'Special',
      roles: ['prologue', 'origin', 'mechanic', 'revelation_agent', 'callback_crystallizer'],
    },
  };

  const ROLE_LABELS: Record<string, string> = {
    narrator: 'Narrator', director: 'Director', choice_crafter: 'Choice Crafter',
    companion_system: 'Companion System', architect: 'Architect', bible: 'Campaign Bible',
    world_mind: 'World Mind', era_forge: 'Era Forge', biographer: 'Biographer',
    casting: 'Casting', memory: 'Memory', psych_archivist: 'Psych Archivist',
    progression: 'Progression', arc_weaver: 'Arc Weaver', arc_screenplay: 'Arc Screenplay',
    continuity: 'Continuity', quest_weaver: 'Quest Weaver', prologue: 'Prologue',
    origin: 'Origin Story', mechanic: 'Mechanic', revelation_agent: 'Revelation Agent',
    callback_crystallizer: 'Callback Crystallizer',
  };

  let providerList = $state<ProviderStatus[]>([]);
  providers.subscribe((val) => { providerList = val; });

  let name = $state(preset?.name || '');
  let description = $state(preset?.description || '');

  // Initialize role configs from existing preset or empty
  type RoleEntry = { provider: string; model: string };
  let roleConfigs = $state<Record<string, RoleEntry>>({});

  $effect(() => {
    if (preset?.role_configs) {
      const init: Record<string, RoleEntry> = {};
      for (const [role, cfg] of Object.entries(preset.role_configs)) {
        if (cfg.provider && cfg.model) {
          init[role] = { provider: cfg.provider, model: cfg.model };
        }
      }
      roleConfigs = init;
    }
  });

  function getModelsForProvider(providerId: string): { id: string; label: string }[] {
    const p = providerList.find((x) => x.provider_id === providerId);
    return p?.models || [];
  }

  function setRoleProvider(role: string, providerId: string) {
    if (!providerId) {
      // Clear the role config
      const next = { ...roleConfigs };
      delete next[role];
      roleConfigs = next;
      return;
    }
    const models = getModelsForProvider(providerId);
    const defaultModel = models[0]?.id || '';
    roleConfigs = { ...roleConfigs, [role]: { provider: providerId, model: defaultModel } };
  }

  function setRoleModel(role: string, model: string) {
    if (!roleConfigs[role]) return;
    roleConfigs = { ...roleConfigs, [role]: { ...roleConfigs[role], model } };
  }

  function handleSave() {
    // Filter out roles with no config
    const configs: Record<string, { provider: string; model: string }> = {};
    for (const [role, cfg] of Object.entries(roleConfigs)) {
      if (cfg.provider && cfg.model) {
        configs[role] = cfg;
      }
    }
    onSave(name.trim(), description.trim(), configs);
  }

  $: canSave = name.trim().length > 0 && Object.keys(roleConfigs).length > 0;
  $: connectedProviders = providerList.filter((p) => p.has_key);
</script>

<div class="modal-overlay" role="dialog" aria-modal="true">
  <div class="modal-card">
    <h2>{preset ? 'Edit Preset' : 'Create Custom Preset'}</h2>

    <div class="form-group">
      <label for="preset-name">Preset Name</label>
      <input id="preset-name" type="text" bind:value={name} placeholder="My Mix" />
    </div>

    <div class="form-group">
      <label for="preset-desc">Description (optional)</label>
      <input id="preset-desc" type="text" bind:value={description} placeholder="Budget narrator, quality director" />
    </div>

    {#if connectedProviders.length === 0}
      <p class="warn-text">No cloud providers configured. Add API keys in the Providers section first.</p>
    {:else}
      <div class="role-grid">
        {#each Object.entries(AGENT_CATEGORIES) as [, category]}
          <div class="role-category">
            <h3 class="category-label">{category.label}</h3>
            {#each category.roles as role}
              <div class="role-row">
                <span class="role-name">{ROLE_LABELS[role] || role}</span>
                <select
                  class="provider-select"
                  value={roleConfigs[role]?.provider || ''}
                  onchange={(e) => setRoleProvider(role, (e.target as HTMLSelectElement).value)}
                >
                  <option value="">Local (default)</option>
                  {#each connectedProviders as cp}
                    <option value={cp.provider_id}>{cp.label}</option>
                  {/each}
                </select>
                {#if roleConfigs[role]?.provider}
                  <select
                    class="model-select"
                    value={roleConfigs[role]?.model || ''}
                    onchange={(e) => setRoleModel(role, (e.target as HTMLSelectElement).value)}
                  >
                    {#each getModelsForProvider(roleConfigs[role].provider) as m}
                      <option value={m.id}>{m.label}</option>
                    {/each}
                  </select>
                {/if}
              </div>
            {/each}
          </div>
        {/each}
      </div>
    {/if}

    <div class="modal-actions">
      <button class="btn btn-primary" onclick={handleSave} disabled={!canSave}>
        {preset ? 'Save Changes' : 'Create Preset'}
      </button>
      <button class="btn" onclick={onCancel}>Cancel</button>
    </div>
  </div>
</div>

<style>
  .modal-overlay {
    position: fixed;
    inset: 0;
    background: rgba(0, 0, 0, 0.7);
    display: flex;
    align-items: center;
    justify-content: center;
    z-index: 1200;
    padding: 1rem;
  }

  .modal-card {
    background: var(--bg-overlay);
    border: 1px solid var(--border-panel);
    border-radius: var(--panel-radius);
    padding: 24px;
    max-width: 600px;
    width: 100%;
    max-height: 80vh;
    overflow-y: auto;
  }

  .modal-card h2 {
    margin: 0 0 16px;
    font-size: 1.2rem;
    color: var(--text-heading);
  }

  .form-group {
    margin-bottom: 12px;
  }

  .form-group label {
    display: block;
    font-size: var(--font-small);
    color: var(--text-muted);
    margin-bottom: 4px;
    text-transform: uppercase;
    letter-spacing: 0.5px;
  }

  .warn-text {
    color: var(--accent-danger);
    font-size: var(--font-small);
    padding: 12px;
    border: 1px solid rgba(255, 80, 60, 0.2);
    border-radius: 6px;
  }

  .role-grid {
    display: flex;
    flex-direction: column;
    gap: 12px;
    margin: 12px 0;
  }

  .category-label {
    font-size: var(--font-small);
    color: var(--text-secondary);
    text-transform: uppercase;
    letter-spacing: 0.5px;
    margin: 0 0 6px;
    font-weight: 600;
  }

  .role-row {
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 4px 0;
    flex-wrap: wrap;
  }

  .role-name {
    min-width: 130px;
    font-size: var(--font-small);
    color: var(--text-primary);
  }

  .provider-select,
  .model-select {
    font-size: var(--font-small);
    padding: 4px 8px;
    flex: 1;
    min-width: 120px;
  }

  .modal-actions {
    display: flex;
    gap: 8px;
    margin-top: 16px;
    justify-content: flex-end;
  }

  .modal-actions .btn {
    padding: 8px 20px;
  }
</style>
