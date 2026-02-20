<script lang="ts">
  import type { BookEntry } from '$lib/api/library';

  interface Props {
    book: BookEntry;
  }
  let { book }: Props = $props();

  let statusColor = $derived(
    book.status === 'complete' ? '#4caf50'
    : book.status === 'failed' ? '#ff5040'
    : book.status === 'running' ? '#e8c56a'
    : '#888'
  );

  let statusLabel = $derived(
    book.status === 'complete' ? 'Complete'
    : book.status === 'failed' ? 'Failed'
    : book.status === 'running' ? 'Processing...'
    : 'Pending'
  );
</script>

<div class="book-card">
  <div class="book-header">
    <span class="book-filename">{book.filename}</span>
    <span class="status-dot" style:background={statusColor} title={statusLabel}></span>
  </div>
  <div class="book-meta">
    {#if book.setting_id}
      <span class="meta-tag">{book.setting_id}</span>
    {/if}
    {#if book.period_id}
      <span class="meta-tag">{book.period_id}</span>
    {/if}
    {#if book.status === 'complete' && book.chunk_count > 0}
      <span class="meta-tag">{book.chunk_count} chunks</span>
    {/if}
  </div>
  {#if book.status === 'failed' && book.error_message}
    <p class="error-text">{book.error_message}</p>
  {/if}
  {#if book.created_at}
    <p class="book-date">{new Date(book.created_at).toLocaleDateString()}</p>
  {/if}
</div>

<style>
  .book-card {
    display: flex;
    flex-direction: column;
    gap: 0.3rem;
    padding: 0.75rem 1rem;
    border: 1px solid var(--border-panel, rgba(255, 255, 255, 0.12));
    border-radius: var(--panel-radius, 8px);
    background: var(--bg-panel, rgba(255, 255, 255, 0.03));
  }
  .book-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    gap: 0.5rem;
  }
  .book-filename {
    font-size: 0.9rem;
    font-weight: 500;
    color: var(--text-primary, #eee);
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  .status-dot {
    width: 8px;
    height: 8px;
    border-radius: 50%;
    flex-shrink: 0;
  }
  .book-meta {
    display: flex;
    flex-wrap: wrap;
    gap: 0.3rem;
  }
  .meta-tag {
    font-size: 0.65rem;
    padding: 1px 6px;
    border-radius: 3px;
    background: rgba(255, 255, 255, 0.06);
    color: var(--text-muted, #888);
  }
  .error-text {
    font-size: 0.72rem;
    color: var(--accent-danger, #ff5040);
    margin: 0;
    line-height: 1.3;
  }
  .book-date {
    font-size: 0.65rem;
    color: var(--text-muted, #666);
    margin: 0;
  }
</style>
