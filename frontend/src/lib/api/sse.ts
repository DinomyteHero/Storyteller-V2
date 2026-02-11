/**
 * SSE streaming for POST endpoints.
 *
 * The backend's turn_stream uses POST (not GET), so the browser's
 * native EventSource API won't work. We use fetch + ReadableStream
 * to parse the `data: {...}\n\n` SSE format manually.
 */
import { BASE_URL } from './client';
import type { Intent, SSEEvent } from './types';

export async function* streamTurn(
  campaignId: string,
  playerId: string,
  userInput: string,
  intent?: Intent
): AsyncGenerator<SSEEvent> {
  const response = await fetch(
    `${BASE_URL}/v2/campaigns/${campaignId}/turn_stream?player_id=${encodeURIComponent(playerId)}`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ user_input: userInput, intent }),
    }
  );

  if (!response.ok) {
    throw new Error(`Stream request failed: ${response.status} ${response.statusText}`);
  }

  const reader = response.body!.getReader();
  const decoder = new TextDecoder();
  let buffer = '';

  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split('\n');
      buffer = lines.pop() || '';

      for (const line of lines) {
        const trimmed = line.trim();
        if (trimmed.startsWith('data: ')) {
          try {
            const event: SSEEvent = JSON.parse(trimmed.slice(6));
            yield event;
          } catch {
            // Skip malformed JSON lines
          }
        }
      }
    }

    // Process any remaining data in buffer
    if (buffer.trim().startsWith('data: ')) {
      try {
        yield JSON.parse(buffer.trim().slice(6));
      } catch {
        // Ignore
      }
    }
  } finally {
    reader.releaseLock();
  }
}
