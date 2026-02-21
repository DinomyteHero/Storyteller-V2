<script lang="ts">
  /**
   * HudBar: Top-of-screen status bar showing location, HP, credits, stress,
   * and contextual pressure indicators (heat, alert).
   */
  interface HudData {
    location: string;
    yearLabel: string;
    hp: number;
    credits: number;
    stress: number;
  }

  interface ScenePressure {
    heat?: string;
    alert?: string;
  }

  interface Props {
    hudData: HudData | null;
    pressure?: ScenePressure | null;
    drawerOpen: boolean;
    unreadIntelCount: number;
    onToggleDrawer: () => void;
    onQuit: () => void;
  }

  let { hudData, pressure, drawerOpen, unreadIntelCount, onToggleDrawer, onQuit }: Props = $props();

  function stressLabel(level: number): string {
    if (level >= 8) return 'Critical';
    if (level >= 6) return 'High';
    if (level >= 4) return 'Moderate';
    return 'Low';
  }
</script>

<header class="hud-bar card scanline" aria-label="Game status bar">
  <div class="hud-left">
    <button
      class="hud-hamburger btn press-scale"
      onclick={onToggleDrawer}
      title="Toggle info panel (i)"
      aria-label="Toggle info panel"
      aria-expanded={drawerOpen}
    >
      ≡
      {#if !drawerOpen && unreadIntelCount > 0}
        <span class="hamburger-intel-dot" aria-label="{unreadIntelCount} unread intel"></span>
      {/if}
    </button>
    {#if hudData}
      <div class="pill" role="status" aria-label="Location: {hudData.location}">
        <span class="label">LOC</span>
        <span class="value">{hudData.location}</span>
      </div>
      <div class="pill" aria-label="Year: {hudData.yearLabel}">
        <span class="label">YEAR</span>
        <span class="value">{hudData.yearLabel}</span>
      </div>
    {/if}
  </div>
  <div class="hud-right">
    {#if hudData}
      <div class="pill" aria-label="Hit points: {hudData.hp}">
        <span class="label">HP</span>
        <span class="value">{hudData.hp}</span>
      </div>
      <div class="pill" aria-label="Credits: {hudData.credits}">
        <span class="label">CR</span>
        <span class="value">{hudData.credits}</span>
      </div>
      <div
        class="pill stress-pill"
        class:stress-high={hudData.stress >= 7}
        class:stress-mid={hudData.stress >= 4 && hudData.stress < 7}
        aria-label="Stress: {hudData.stress} out of 10, {stressLabel(hudData.stress)}"
      >
        <span class="label">S</span>
        <span class="value">{hudData.stress}</span>
      </div>
      {#if pressure?.heat && pressure.heat !== 'Low'}
        <div class="pill heat-pill heat-{pressure.heat.toLowerCase()}" aria-label="Heat: {pressure.heat}">
          <span class="label">🔥</span>
          <span class="value">{pressure.heat}</span>
        </div>
      {/if}
      {#if pressure?.alert && pressure.alert !== 'Quiet'}
        <div class="pill alert-pill alert-{pressure.alert.toLowerCase()}" aria-label="Alert: {pressure.alert}">
          <span class="label">⚠</span>
          <span class="value">{pressure.alert}</span>
        </div>
      {/if}
    {/if}
    <button
      class="btn hud-quit press-scale"
      onclick={onQuit}
      title="Quit to menu"
      aria-label="Quit to main menu"
    >✕</button>
  </div>
</header>

<style>
  .hud-bar {
    display: flex;
    justify-content: space-between;
    align-items: center;
    flex-wrap: wrap;
    gap: 8px;
    padding: 8px 16px;
    border-radius: 0;
    position: sticky;
    top: 0;
    z-index: 100;
  }
  .hud-left, .hud-right {
    display: flex;
    gap: 8px;
    align-items: center;
    flex-wrap: wrap;
  }
  .pill {
    display: flex;
    gap: 4px;
    align-items: center;
    padding: 2px 8px;
    border-radius: 4px;
    font-size: 0.78rem;
    background: var(--surface-2, rgba(255,255,255,0.06));
    white-space: nowrap;
  }
  .pill .label {
    opacity: 0.5;
    font-size: 0.68rem;
    text-transform: uppercase;
    letter-spacing: 0.5px;
  }
  .pill .value {
    font-weight: 600;
  }
  .stress-pill.stress-high {
    background: rgba(231, 76, 60, 0.25);
    color: #e74c3c;
  }
  .stress-pill.stress-mid {
    background: rgba(241, 196, 15, 0.2);
    color: #f1c40f;
  }
  .heat-pill.heat-medium { background: rgba(230, 126, 34, 0.2); color: #e67e22; }
  .heat-pill.heat-high { background: rgba(231, 76, 60, 0.25); color: #e74c3c; }
  .heat-pill.heat-critical { background: rgba(231, 76, 60, 0.4); color: #ff6b6b; }
  .alert-pill.alert-cautious { background: rgba(241, 196, 15, 0.15); color: #f1c40f; }
  .alert-pill.alert-alarmed { background: rgba(230, 126, 34, 0.2); color: #e67e22; }
  .alert-pill.alert-hostile { background: rgba(231, 76, 60, 0.3); color: #e74c3c; }
  .hud-hamburger {
    font-size: 1.4rem;
    padding: 2px 8px;
    background: none;
    border: none;
    cursor: pointer;
    position: relative;
  }
  .hamburger-intel-dot {
    position: absolute;
    top: 2px;
    right: 2px;
    width: 8px;
    height: 8px;
    border-radius: 50%;
    background: var(--accent-orange, #e67e22);
  }
  .hud-quit {
    font-size: 1.1rem;
    padding: 2px 8px;
    background: none;
    border: none;
    cursor: pointer;
    opacity: 0.5;
    transition: opacity 0.2s;
  }
  .hud-quit:hover { opacity: 1; }
</style>
