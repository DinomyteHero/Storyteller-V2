<!--
  NpcSpeech.svelte — Renders NPC utterance above narrative prose.
  Creates the KOTOR conversational flow: NPC speaks → you read context → you respond.
  Hidden when speaker_id is "narrator" or text is empty.
-->
<script lang="ts">
  import type { NPCUtterance } from '$lib/api/types';

  interface Props {
    utterance: NPCUtterance | null;
  }

  let { utterance }: Props = $props();

  let visible = $derived(
    utterance != null &&
    utterance.text.trim() !== '' &&
    utterance.speaker_id !== 'narrator'
  );
</script>

{#if visible && utterance}
  <div class="npc-speech fade-in" role="region" aria-label="NPC dialogue from {utterance.speaker_name}">
    <div class="npc-speaker-name">{utterance.speaker_name}</div>
    <blockquote class="npc-dialogue">
      "{utterance.text}"
    </blockquote>
  </div>
{/if}

<style>
  .npc-speech {
    padding: 12px 16px;
    border-left: 3px solid var(--accent-primary);
    background: linear-gradient(90deg, var(--accent-glow) 0%, transparent 40%);
    border-radius: 0 var(--panel-radius) var(--panel-radius) 0;
    margin-bottom: 12px;
  }

  .npc-speaker-name {
    font-size: var(--font-caption);
    font-weight: 700;
    color: var(--text-heading);
    text-transform: uppercase;
    letter-spacing: 1px;
    margin-bottom: 6px;
  }

  .npc-dialogue {
    margin: 0;
    padding: 0;
    font-family: var(--font-narrative-family, 'Noto Serif', Georgia, serif);
    font-size: var(--font-narrative);
    line-height: var(--line-height-narrative);
    color: var(--text-primary);
    font-style: italic;
  }
</style>
