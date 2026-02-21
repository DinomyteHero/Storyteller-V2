<script lang="ts">
  import { page } from '$app/stores';
  import { goto } from '$app/navigation';
</script>

<div class="error-page">
  <div class="error-content">
    <div class="error-code">{$page.status}</div>
    <h1 class="error-title">
      {#if $page.status === 404}
        Page Not Found
      {:else}
        Something Went Wrong
      {/if}
    </h1>
    <p class="error-message">
      {$page.error?.message || 'An unexpected error occurred.'}
    </p>
    <div class="error-actions">
      <button class="btn btn-primary" onclick={() => goto('/')}>
        Return Home
      </button>
      <button class="btn btn-ghost" onclick={() => window.location.reload()}>
        Reload Page
      </button>
    </div>
  </div>
</div>

<style>
  .error-page {
    min-height: 100vh;
    display: flex;
    align-items: center;
    justify-content: center;
    padding: 2rem;
  }

  .error-content {
    text-align: center;
    max-width: 480px;
  }

  .error-code {
    font-size: 4rem;
    font-weight: 700;
    color: var(--accent-glow, rgba(232, 197, 106, 0.3));
    line-height: 1;
    margin-bottom: 0.5rem;
    font-family: 'Rajdhani', sans-serif;
  }

  .error-title {
    font-size: 1.5rem;
    color: var(--text-heading);
    margin: 0 0 1rem;
  }

  .error-message {
    color: var(--text-muted);
    font-size: 0.95rem;
    line-height: 1.6;
    margin-bottom: 2rem;
  }

  .error-actions {
    display: flex;
    gap: 1rem;
    justify-content: center;
  }

  .btn-ghost {
    padding: 0.6rem 1.4rem;
    border-radius: var(--panel-radius);
    border: 1px solid var(--border-subtle);
    cursor: pointer;
    font-size: var(--font-body);
    transition: all 0.15s;
    background: transparent;
    color: var(--text-muted);
    font-family: 'Rajdhani', 'Inter', sans-serif;
    font-weight: 600;
  }

  .btn-ghost:hover {
    color: var(--text-secondary);
    border-color: var(--border-panel);
  }
</style>
