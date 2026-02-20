<script lang="ts">
  import { onMount } from 'svelte';
  import { goto } from '$app/navigation';
  import { getContentCatalog, type ContentCatalogEntry } from '$lib/api/content';
  import { getBooks, uploadBook, getJobStatus, type BookEntry } from '$lib/api/library';
  import { listSources, createSource, deleteSource, type LoreSourceEntry } from '$lib/api/sources';
  import { getHealthDetail, type HealthDetailResponse } from '$lib/api/client';
  import WorldCard from '$lib/components/library/WorldCard.svelte';
  import BookCard from '$lib/components/library/BookCard.svelte';
  import FileUpload from '$lib/components/library/FileUpload.svelte';
  import EraForgeWizard from '$lib/components/library/EraForgeWizard.svelte';

  // Tab state
  let activeTab = $state<'worlds' | 'books' | 'sources' | 'status'>('worlds');

  // Worlds tab
  let worlds = $state<ContentCatalogEntry[]>([]);
  let worldsLoading = $state(false);
  let worldsError = $state('');
  let showWizard = $state(false);

  // Books tab
  let books = $state<BookEntry[]>([]);
  let booksLoading = $state(false);
  let booksError = $state('');
  let uploadSettingId = $state('');
  let uploadPeriodId = $state('');
  let uploading = $state(false);
  let uploadStatus = $state('');

  // Sources tab (V11.0)
  let sources = $state<LoreSourceEntry[]>([]);
  let sourcesLoading = $state(false);
  let sourcesError = $state('');
  let newSourceName = $state('');
  let newSourceSettingId = $state('');
  let newSourcePeriodId = $state('');
  let creatingSource = $state(false);
  let deletingSourceId = $state<string | null>(null);

  // Status tab
  let healthData = $state<HealthDetailResponse | null>(null);
  let statusLoading = $state(false);

  onMount(() => {
    loadWorlds();
  });

  async function loadWorlds() {
    worldsLoading = true;
    worldsError = '';
    try {
      const res = await getContentCatalog();
      worlds = res.items ?? [];
    } catch (e) {
      worldsError = e instanceof Error ? e.message : 'Failed to load worlds.';
    } finally {
      worldsLoading = false;
    }
  }

  async function loadBooks() {
    booksLoading = true;
    booksError = '';
    try {
      const res = await getBooks();
      books = res.items ?? [];
    } catch (e) {
      booksError = e instanceof Error ? e.message : 'Failed to load books.';
    } finally {
      booksLoading = false;
    }
  }

  async function loadStatus() {
    statusLoading = true;
    try {
      healthData = await getHealthDetail(10_000);
    } catch {
      healthData = null;
    } finally {
      statusLoading = false;
    }
  }

  async function loadSources() {
    sourcesLoading = true;
    sourcesError = '';
    try {
      const res = await listSources();
      sources = res.items ?? [];
    } catch (e) {
      sourcesError = e instanceof Error ? e.message : 'Failed to load sources.';
    } finally {
      sourcesLoading = false;
    }
  }

  async function handleCreateSource() {
    if (!newSourceName.trim()) return;
    creatingSource = true;
    sourcesError = '';
    try {
      await createSource(newSourceName.trim(), newSourceSettingId, newSourcePeriodId);
      newSourceName = '';
      newSourceSettingId = '';
      newSourcePeriodId = '';
      await loadSources();
    } catch (e) {
      sourcesError = e instanceof Error ? e.message : 'Failed to create source.';
    } finally {
      creatingSource = false;
    }
  }

  async function handleDeleteSource(sourceId: string) {
    deletingSourceId = sourceId;
    sourcesError = '';
    try {
      await deleteSource(sourceId);
      await loadSources();
    } catch (e) {
      sourcesError = e instanceof Error ? e.message : 'Failed to delete source.';
    } finally {
      deletingSourceId = null;
    }
  }

  function handleTabChange(tab: 'worlds' | 'books' | 'sources' | 'status') {
    activeTab = tab;
    if (tab === 'books' && books.length === 0) loadBooks();
    if (tab === 'sources' && sources.length === 0) loadSources();
    if (tab === 'status') loadStatus();
  }

  async function handleFileSelected(file: File) {
    uploading = true;
    uploadStatus = '';
    booksError = '';
    try {
      const job = await uploadBook(file, uploadSettingId, uploadPeriodId);
      uploadStatus = `Uploading ${file.name}...`;

      // Poll for completion
      let attempts = 0;
      const maxAttempts = 60;
      const poll = setInterval(async () => {
        attempts++;
        try {
          const status = await getJobStatus(job.job_id);
          if (status.status === 'complete') {
            clearInterval(poll);
            uploadStatus = `Done! ${status.chunk_count} chunks ingested.`;
            uploading = false;
            loadBooks();
          } else if (status.status === 'failed') {
            clearInterval(poll);
            uploadStatus = '';
            booksError = status.error_message ?? 'Ingestion failed.';
            uploading = false;
            loadBooks();
          } else {
            uploadStatus = `Processing ${file.name}...`;
          }
          if (attempts >= maxAttempts) {
            clearInterval(poll);
            uploadStatus = 'Ingestion is taking longer than expected. Check back later.';
            uploading = false;
          }
        } catch {
          clearInterval(poll);
          uploading = false;
          uploadStatus = '';
          booksError = 'Lost connection while polling ingestion status.';
        }
      }, 2000);
    } catch (e) {
      booksError = e instanceof Error ? e.message : 'Upload failed.';
      uploading = false;
    }
  }

  function handleWizardComplete() {
    showWizard = false;
    loadWorlds();
  }
</script>

<div class="library-page">
  <header class="library-header">
    <button class="back-btn" onclick={() => goto('/')} aria-label="Back to menu">&larr;</button>
    <h1>Library</h1>
  </header>

  <!-- Tab bar -->
  <nav class="tab-bar" role="tablist">
    <button
      class="tab-btn"
      class:active={activeTab === 'worlds'}
      role="tab"
      aria-selected={activeTab === 'worlds'}
      onclick={() => handleTabChange('worlds')}
    >Your Worlds</button>
    <button
      class="tab-btn"
      class:active={activeTab === 'books'}
      role="tab"
      aria-selected={activeTab === 'books'}
      onclick={() => handleTabChange('books')}
    >Your Books</button>
    <button
      class="tab-btn"
      class:active={activeTab === 'sources'}
      role="tab"
      aria-selected={activeTab === 'sources'}
      onclick={() => handleTabChange('sources')}
    >Sources</button>
    <button
      class="tab-btn"
      class:active={activeTab === 'status'}
      role="tab"
      aria-selected={activeTab === 'status'}
      onclick={() => handleTabChange('status')}
    >System Status</button>
  </nav>

  <!-- Tab content -->
  <div class="tab-content">
    <!-- Worlds Tab -->
    {#if activeTab === 'worlds'}
      {#if showWizard}
        <div class="wizard-wrapper">
          <EraForgeWizard
            onComplete={handleWizardComplete}
            onCancel={() => showWizard = false}
          />
        </div>
      {:else}
        <div class="tab-actions">
          <button class="btn btn-primary" onclick={() => showWizard = true}>
            Create New World
          </button>
        </div>

        {#if worldsError}
          <div class="error-banner" role="alert">{worldsError}</div>
        {/if}

        {#if worldsLoading}
          <p class="empty-state">Loading worlds...</p>
        {:else if worlds.length === 0}
          <p class="empty-state">No worlds available. Create one to get started.</p>
        {:else}
          <div class="card-grid">
            {#each worlds as world, i}
              <div class="stagger-enter" style="animation-delay: {i * 40}ms">
                <WorldCard {world} />
              </div>
            {/each}
          </div>
        {/if}
      {/if}

    <!-- Books Tab -->
    {:else if activeTab === 'books'}
      <div class="upload-section">
        <div class="upload-meta-row">
          <input
            class="meta-input"
            type="text"
            placeholder="Setting ID (optional)"
            bind:value={uploadSettingId}
            disabled={uploading}
          />
          <input
            class="meta-input"
            type="text"
            placeholder="Period ID (optional)"
            bind:value={uploadPeriodId}
            disabled={uploading}
          />
        </div>
        <FileUpload onFileSelected={handleFileSelected} disabled={uploading} />
        {#if uploadStatus}
          <p class="upload-status">{uploadStatus}</p>
        {/if}
      </div>

      {#if booksError}
        <div class="error-banner" role="alert">{booksError}</div>
      {/if}

      {#if booksLoading}
        <p class="empty-state">Loading books...</p>
      {:else if books.length === 0 && !booksLoading}
        <p class="empty-state">No books ingested yet. Upload a file above.</p>
      {:else}
        <div class="book-list">
          {#each books as book, i}
            <div class="stagger-enter" style="animation-delay: {i * 40}ms">
              <BookCard {book} />
            </div>
          {/each}
        </div>
      {/if}

    <!-- Sources Tab (V11.0) -->
    {:else if activeTab === 'sources'}
      <div class="source-create-section">
        <h3 class="source-section-title">Create Reference Collection</h3>
        <div class="source-create-form">
          <input
            class="meta-input"
            type="text"
            placeholder="Collection name (e.g. 'Dune novels')"
            bind:value={newSourceName}
            disabled={creatingSource}
          />
          <div class="upload-meta-row">
            <input
              class="meta-input"
              type="text"
              placeholder="Setting ID (optional)"
              bind:value={newSourceSettingId}
              disabled={creatingSource}
            />
            <input
              class="meta-input"
              type="text"
              placeholder="Period ID (optional)"
              bind:value={newSourcePeriodId}
              disabled={creatingSource}
            />
          </div>
          <button
            class="btn btn-primary"
            disabled={!newSourceName.trim() || creatingSource}
            onclick={handleCreateSource}
          >
            {creatingSource ? 'Creating...' : 'Create Collection'}
          </button>
        </div>
      </div>

      {#if sourcesError}
        <div class="error-banner" role="alert">{sourcesError}</div>
      {/if}

      {#if sourcesLoading}
        <p class="empty-state">Loading sources...</p>
      {:else if sources.length === 0}
        <p class="empty-state">No reference collections yet. Create one above to organize your lore.</p>
      {:else}
        <div class="source-list">
          {#each sources as src}
            <div class="source-entry card">
              <div class="source-info">
                <div class="source-name">{src.name}</div>
                <div class="source-meta">
                  {#if src.setting_id}<span class="source-tag">{src.setting_id}</span>{/if}
                  {#if src.period_id}<span class="source-tag">{src.period_id}</span>{/if}
                  <span>{src.chunk_count} chunks</span>
                  <span>{src.file_count} files</span>
                </div>
              </div>
              <button
                class="btn source-delete"
                disabled={deletingSourceId === src.id}
                onclick={() => handleDeleteSource(src.id)}
                title="Delete source and remove its chunks"
              >
                {deletingSourceId === src.id ? '...' : 'Delete'}
              </button>
            </div>
          {/each}
        </div>
      {/if}

    <!-- Status Tab -->
    {:else if activeTab === 'status'}
      {#if statusLoading}
        <p class="empty-state">Checking system status...</p>
      {:else if healthData}
        <div class="status-grid">
          <div class="status-card">
            <h3>System</h3>
            <div class="status-row">
              <span>Status</span>
              <span class="status-value" class:healthy={healthData.status === 'healthy'} class:degraded={healthData.status === 'degraded'}>
                {healthData.status}
              </span>
            </div>
          </div>

          {#if healthData.checks?.ollama}
            {@const ollama = healthData.checks.ollama}
            <div class="status-card">
              <h3>Ollama</h3>
              <div class="status-row">
                <span>Connection</span>
                <span class="status-value" class:healthy={ollama.ok} class:degraded={!ollama.ok}>
                  {ollama.ok ? 'Connected' : 'Down'}
                </span>
              </div>
              {#if ollama.models_loaded !== undefined}
                <div class="status-row">
                  <span>Models Loaded</span>
                  <span>{ollama.models_loaded}</span>
                </div>
              {/if}
              {#if ollama.url}
                <div class="status-row">
                  <span>URL</span>
                  <span class="mono">{ollama.url}</span>
                </div>
              {/if}
            </div>
          {/if}

          {#each Object.entries(healthData.checks ?? {}).filter(([k]) => k !== 'ollama') as [key, check]}
            <div class="status-card">
              <h3>{key}</h3>
              {#if typeof check === 'object' && check !== null}
                {#each Object.entries(check as Record<string, unknown>) as [field, value]}
                  <div class="status-row">
                    <span>{field}</span>
                    <span class="mono">{String(value)}</span>
                  </div>
                {/each}
              {/if}
            </div>
          {/each}
        </div>

        <div class="tab-actions" style="margin-top: 1rem;">
          <button class="btn" onclick={loadStatus}>Refresh</button>
        </div>
      {:else}
        <p class="empty-state">Unable to reach backend. Is the server running?</p>
      {/if}
    {/if}
  </div>
</div>

<style>
  .library-page {
    min-height: 100vh;
    display: flex;
    flex-direction: column;
    max-width: 800px;
    margin: 0 auto;
    padding: 1.5rem 1rem;
  }
  .library-header {
    display: flex;
    align-items: center;
    gap: 0.75rem;
    margin-bottom: 1.25rem;
  }
  .library-header h1 {
    font-family: var(--font-heading, 'Rajdhani', sans-serif);
    font-size: 1.5rem;
    font-weight: 700;
    color: var(--text-heading, #e8c56a);
    margin: 0;
  }
  .back-btn {
    background: none;
    border: 1px solid var(--border-panel, rgba(255, 255, 255, 0.15));
    border-radius: 6px;
    color: var(--text-secondary, #aaa);
    padding: 0.3rem 0.6rem;
    cursor: pointer;
    font-size: 1rem;
    transition: border-color 0.15s;
  }
  .back-btn:hover {
    border-color: var(--text-secondary, #aaa);
  }

  /* Tab bar */
  .tab-bar {
    display: flex;
    gap: 0;
    border-bottom: 1px solid var(--border-panel, rgba(255, 255, 255, 0.1));
    margin-bottom: 1.25rem;
  }
  .tab-btn {
    flex: 1;
    background: none;
    border: none;
    border-bottom: 2px solid transparent;
    color: var(--text-muted, #888);
    padding: 0.6rem 0.75rem;
    font-size: 0.82rem;
    font-weight: 500;
    text-transform: uppercase;
    letter-spacing: 0.04em;
    cursor: pointer;
    transition: color 0.15s, border-color 0.15s;
  }
  .tab-btn:hover {
    color: var(--text-secondary, #aaa);
  }
  .tab-btn.active {
    color: var(--accent-primary, #e8c56a);
    border-bottom-color: var(--accent-primary, #e8c56a);
  }

  /* Tab content */
  .tab-content {
    flex: 1;
  }
  .tab-actions {
    display: flex;
    justify-content: flex-end;
    margin-bottom: 1rem;
  }

  /* World grid */
  .card-grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(240px, 1fr));
    gap: 0.75rem;
  }

  /* Book list */
  .book-list {
    display: flex;
    flex-direction: column;
    gap: 0.5rem;
  }

  /* Upload section */
  .upload-section {
    display: flex;
    flex-direction: column;
    gap: 0.5rem;
    margin-bottom: 1.25rem;
  }
  .upload-meta-row {
    display: flex;
    gap: 0.5rem;
  }
  .meta-input {
    flex: 1;
    padding: 0.45rem 0.6rem;
    border: 1px solid var(--border-panel, rgba(255, 255, 255, 0.15));
    border-radius: 6px;
    background: rgba(0, 0, 0, 0.2);
    color: var(--text-primary, #eee);
    font-size: 0.8rem;
  }
  .meta-input:focus {
    outline: none;
    border-color: var(--accent-primary, #e8c56a);
  }
  .upload-status {
    font-size: 0.78rem;
    color: var(--accent-primary, #e8c56a);
    margin: 0;
    text-align: center;
  }

  /* Wizard wrapper */
  .wizard-wrapper {
    border: 1px solid var(--border-panel, rgba(255, 255, 255, 0.12));
    border-radius: var(--panel-radius, 8px);
    background: var(--bg-panel, rgba(255, 255, 255, 0.02));
    padding: 1.25rem;
  }

  /* Status grid */
  .status-grid {
    display: flex;
    flex-direction: column;
    gap: 0.75rem;
  }
  .status-card {
    border: 1px solid var(--border-panel, rgba(255, 255, 255, 0.12));
    border-radius: var(--panel-radius, 8px);
    background: var(--bg-panel, rgba(255, 255, 255, 0.03));
    padding: 0.75rem 1rem;
  }
  .status-card h3 {
    font-family: var(--font-heading, 'Rajdhani', sans-serif);
    font-size: 0.9rem;
    font-weight: 600;
    color: var(--text-heading, #e8c56a);
    margin: 0 0 0.5rem 0;
    text-transform: uppercase;
    letter-spacing: 0.04em;
  }
  .status-row {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 0.2rem 0;
    font-size: 0.78rem;
    color: var(--text-secondary, #aaa);
    border-bottom: 1px solid rgba(255, 255, 255, 0.04);
  }
  .status-row:last-child {
    border-bottom: none;
  }
  .status-value.healthy {
    color: #4caf50;
  }
  .status-value.degraded {
    color: #ff5040;
  }
  .mono {
    font-family: 'JetBrains Mono', monospace;
    font-size: 0.72rem;
  }

  /* Sources tab (V11.0) */
  .source-create-section {
    margin-bottom: 1.25rem;
  }
  .source-section-title {
    font-size: 0.85rem;
    color: var(--text-secondary, #aaa);
    text-transform: uppercase;
    letter-spacing: 0.04em;
    margin-bottom: 0.5rem;
  }
  .source-create-form {
    display: flex;
    flex-direction: column;
    gap: 0.5rem;
  }
  .source-list {
    display: flex;
    flex-direction: column;
    gap: 0.5rem;
  }
  .source-entry {
    display: flex;
    justify-content: space-between;
    align-items: center;
    gap: 12px;
  }
  .source-info {
    flex: 1;
    min-width: 0;
  }
  .source-name {
    font-weight: 600;
    color: var(--text-heading, #e8c56a);
    font-size: 0.95rem;
  }
  .source-meta {
    display: flex;
    gap: 8px;
    font-size: 0.72rem;
    color: var(--text-muted, #888);
    margin-top: 2px;
  }
  .source-tag {
    background: rgba(255, 255, 255, 0.06);
    padding: 1px 6px;
    border-radius: 4px;
    font-family: 'JetBrains Mono', monospace;
  }
  .source-delete {
    font-size: 0.75rem;
    padding: 4px 10px;
    color: var(--text-muted, #888);
    border: 1px solid var(--border-subtle, rgba(255, 255, 255, 0.1));
    background: transparent;
  }
  .source-delete:hover {
    color: var(--accent-danger, #ff5040);
    border-color: var(--accent-danger, #ff5040);
  }

  /* Shared */
  .error-banner {
    padding: 8px 12px;
    border-radius: 6px;
    background: rgba(255, 80, 60, 0.12);
    border: 1px solid var(--accent-danger, #ff5040);
    color: var(--accent-danger, #ff5040);
    font-size: 0.8rem;
    margin-bottom: 0.75rem;
  }
  .empty-state {
    color: var(--text-muted, #888);
    font-style: italic;
    padding: 2rem 0;
    text-align: center;
    font-size: 0.85rem;
  }

  @media (max-width: 768px) {
    .library-page {
      padding: 1rem 0.75rem;
    }
    .card-grid {
      grid-template-columns: 1fr;
    }
    .upload-meta-row {
      flex-direction: column;
    }
  }
</style>
