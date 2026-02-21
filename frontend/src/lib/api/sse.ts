/**
 * SSE streaming for POST endpoints.
 *
 * The backend's turn_stream uses POST (not GET), so the browser's
 * native EventSource API won't work. We use fetch + ReadableStream
 * to parse the `data: {...}\n\n` SSE format manually.
 */
import { BASE_URL } from './client';
import type { SSEEvent, StructuredIntent } from './types';

export async function* streamTurn(
  campaignId: string,
  playerId: string,
  userInput: string,
  structuredIntent?: StructuredIntent | null,
  externalSignal?: AbortSignal,
): AsyncGenerator<SSEEvent> {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 300_000); // 5-minute timeout

  // Wire external signal to internal controller
  if (externalSignal) {
    if (externalSignal.aborted) {
      clearTimeout(timeout);
      controller.abort();
      return;
    }
    externalSignal.addEventListener('abort', () => controller.abort(), { once: true });
  }

  const bodyPayload: Record<string, unknown> = { user_input: userInput };
  if (structuredIntent) {
    bodyPayload.structured_intent = structuredIntent;
  }

  let response: Response;
  try {
    response = await fetch(
      `${BASE_URL}/v2/campaigns/${campaignId}/turn_stream?player_id=${encodeURIComponent(playerId)}`,
      {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(bodyPayload),
        signal: controller.signal,
      }
    );
  } catch (err: unknown) {
    clearTimeout(timeout);
    if (err instanceof DOMException && err.name === 'AbortError') {
      return; // Clean cancellation
    }
    throw new Error(`Stream connection failed: ${err instanceof Error ? err.message : String(err)}`);
  }

  if (!response.ok) {
    clearTimeout(timeout);
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
  } catch (err: unknown) {
    if (err instanceof DOMException && err.name === 'AbortError') {
      return; // Clean cancellation
    }
    throw err;
  } finally {
    clearTimeout(timeout);
    reader.cancel().catch(() => {});
    reader.releaseLock();
  }
}
