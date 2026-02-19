import { beforeEach, describe, expect, it } from 'vitest';
import { get } from 'svelte/store';
import {
  appendToken,
  failStreaming,
  finishStreaming,
  isStreaming,
  resetStreaming,
  showCursor,
  startStreaming,
  streamDone,
  streamError,
  streamedText,
} from '$lib/stores/streaming';

describe('streaming store', () => {
  beforeEach(() => {
    resetStreaming();
  });

  it('startStreaming initializes an active clean stream state', () => {
    startStreaming();
    expect(get(isStreaming)).toBe(true);
    expect(get(streamedText)).toBe('');
    expect(get(streamError)).toBeNull();
    expect(get(streamDone)).toBe(false);
  });

  it('appendToken accumulates streamed text', () => {
    startStreaming();
    appendToken('Hello');
    appendToken(' world');
    expect(get(streamedText)).toBe('Hello world');
  });

  it('finishStreaming marks stream complete and hides cursor', () => {
    startStreaming();
    finishStreaming();
    expect(get(isStreaming)).toBe(false);
    expect(get(streamDone)).toBe(true);
    expect(get(showCursor)).toBe(false);
  });

  it('failStreaming stores error and ends stream', () => {
    startStreaming();
    failStreaming('network lost');
    expect(get(isStreaming)).toBe(false);
    expect(get(streamError)).toBe('network lost');
    expect(get(streamDone)).toBe(false);
  });
});
