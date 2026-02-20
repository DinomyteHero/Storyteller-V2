<script lang="ts">
  interface Props {
    onFileSelected: (file: File) => void;
    accept?: string;
    disabled?: boolean;
  }
  let { onFileSelected, accept = '.pdf,.epub,.txt', disabled = false }: Props = $props();

  let dragging = $state(false);
  let fileInput: HTMLInputElement | undefined = $state();

  function handleDrop(e: DragEvent) {
    e.preventDefault();
    dragging = false;
    if (disabled) return;
    const file = e.dataTransfer?.files?.[0];
    if (file) onFileSelected(file);
  }

  function handleDragOver(e: DragEvent) {
    e.preventDefault();
    if (!disabled) dragging = true;
  }

  function handleDragLeave() {
    dragging = false;
  }

  function handleInputChange(e: Event) {
    const input = e.target as HTMLInputElement;
    const file = input.files?.[0];
    if (file) onFileSelected(file);
    // Reset input so the same file can be re-selected
    input.value = '';
  }

  function handleClick() {
    if (!disabled) fileInput?.click();
  }
</script>

<div
  class="upload-zone"
  class:dragging
  class:disabled
  role="button"
  tabindex="0"
  ondrop={handleDrop}
  ondragover={handleDragOver}
  ondragleave={handleDragLeave}
  onclick={handleClick}
  onkeydown={(e) => e.key === 'Enter' && handleClick()}
>
  <input
    bind:this={fileInput}
    type="file"
    {accept}
    onchange={handleInputChange}
    class="hidden-input"
    {disabled}
  />
  <div class="upload-content">
    <span class="upload-icon">+</span>
    <span class="upload-label">Drop a file here or click to browse</span>
    <span class="upload-hint">PDF, EPUB, or TXT</span>
  </div>
</div>

<style>
  .upload-zone {
    display: flex;
    align-items: center;
    justify-content: center;
    padding: 1.5rem;
    border: 2px dashed var(--border-panel, rgba(255, 255, 255, 0.15));
    border-radius: var(--panel-radius, 8px);
    background: var(--bg-panel, rgba(255, 255, 255, 0.02));
    cursor: pointer;
    transition: border-color 0.15s, background 0.15s;
  }
  .upload-zone:hover,
  .upload-zone.dragging {
    border-color: var(--accent-primary, #e8c56a);
    background: rgba(232, 197, 106, 0.04);
  }
  .upload-zone.disabled {
    opacity: 0.5;
    cursor: not-allowed;
  }
  .hidden-input {
    display: none;
  }
  .upload-content {
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 0.3rem;
  }
  .upload-icon {
    font-size: 1.8rem;
    line-height: 1;
    color: var(--text-muted, #888);
  }
  .upload-label {
    font-size: 0.85rem;
    color: var(--text-secondary, #aaa);
  }
  .upload-hint {
    font-size: 0.7rem;
    color: var(--text-muted, #666);
  }
</style>
