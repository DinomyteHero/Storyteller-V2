/**
 * Streaming state store — SSE turn streaming.
 *
 * Tracks whether we're currently streaming, the accumulated text,
 * post-stream processing state, and any error state. Memory only.
 */
import { writable, derived } from 'svelte/store';

/** Whether an SSE stream is currently in progress. */
export const isStreaming = writable(false);

/** Accumulated narrative text from token events during streaming. */
export const streamedText = writable('');

/** Error message if streaming failed. */
export const streamError = writable<string | null>(null);

/** Whether streaming completed successfully (done event received). */
export const streamDone = writable(false);

/** Whether post-stream processing is in progress (choice crafting, commit). */
export const isProcessingChoices = writable(false);

/** Derived: whether we should show the streaming cursor. */
export const showCursor = derived(
  [isStreaming, streamDone],
  ([$isStreaming, $streamDone]) => $isStreaming && !$streamDone
);

/** Reset streaming state for a new turn. */
export function resetStreaming(): void {
  isStreaming.set(false);
  streamedText.set('');
  streamError.set(null);
  streamDone.set(false);
  isProcessingChoices.set(false);
}

/** Start a new streaming session. */
export function startStreaming(): void {
  streamedText.set('');
  streamError.set(null);
  streamDone.set(false);
  isProcessingChoices.set(false);
  isStreaming.set(true);
}

/** Append a token to the accumulated text. */
export function appendToken(text: string): void {
  streamedText.update((current) => current + text);
}

/** Mark narrator streaming as complete; begin post-stream processing. */
export function finishStreaming(): void {
  streamDone.set(true);
  isStreaming.set(false);
  isProcessingChoices.set(true);
}

/** Mark post-stream processing (choices + commit) as complete. */
export function finishProcessing(): void {
  isProcessingChoices.set(false);
}

/** Mark streaming as failed. */
export function failStreaming(error: string): void {
  streamError.set(error);
  isStreaming.set(false);
  isProcessingChoices.set(false);
}
