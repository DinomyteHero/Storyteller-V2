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
    background: var(--color-bg, #0a0a0f);
    padding: 2rem;
  }

  .error-content {
    text-align: center;
    max-width: 480px;
  }

  .error-code {
    font-size: 4rem;
    font-weight: 700;
    color: rgba(232, 197, 106, 0.3);
    line-height: 1;
    margin-bottom: 0.5rem;
    font-family: 'Rajdhani', sans-serif;
  }

  .error-title {
    font-size: 1.5rem;
    color: rgba(240, 230, 200, 0.9);
    margin: 0 0 1rem;
  }

  .error-message {
    color: rgba(240, 230, 200, 0.5);
    font-size: 0.95rem;
    line-height: 1.6;
    margin-bottom: 2rem;
  }

  .error-actions {
    display: flex;
    gap: 1rem;
    justify-content: center;
  }

  .btn {
    padding: 0.6rem 1.4rem;
    border-radius: 6px;
    border: 1px solid rgba(255, 255, 255, 0.15);
    cursor: pointer;
    font-size: 0.95rem;
    transition: all 0.15s;
    background: transparent;
    color: rgba(240, 230, 200, 0.85);
  }

  .btn-primary {
    background: #e8c56a;
    border-color: #e8c56a;
    color: #1a1208;
    font-weight: 600;
  }

  .btn-primary:hover {
    background: #f0d07a;
  }

  .btn-ghost {
    border-color: rgba(255, 255, 255, 0.1);
    color: rgba(240, 230, 200, 0.45);
  }

  .btn-ghost:hover {
    color: rgba(240, 230, 200, 0.7);
    border-color: rgba(255, 255, 255, 0.2);
  }
</style>
