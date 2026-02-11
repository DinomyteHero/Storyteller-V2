/**
 * Typewriter effect — character-by-character reveal using requestAnimationFrame.
 *
 * Takes a full text string and calls a callback with progressively longer
 * substrings at a configurable speed. Uses rAF for smooth 60fps rendering.
 */

export interface TypewriterOptions {
  /** Characters revealed per frame (~60fps). Default: 2 */
  charsPerFrame?: number;
  /** Pause duration (ms) at sentence boundaries. Default: 80 */
  sentencePause?: number;
  /** Pause duration (ms) at paragraph boundaries. Default: 200 */
  paragraphPause?: number;
  /** Callback fired on each frame with current visible text length */
  onProgress?: (visibleLength: number) => void;
  /** Callback when the full text is revealed */
  onComplete?: () => void;
}

const SENTENCE_ENDS = new Set(['.', '!', '?']);
const PARAGRAPH_CHAR = '\n';

export function startTypewriter(
  fullText: string,
  options: TypewriterOptions = {}
): { cancel: () => void } {
  const {
    charsPerFrame = 2,
    sentencePause = 80,
    paragraphPause = 200,
    onProgress,
    onComplete,
  } = options;

  let currentIndex = 0;
  let cancelled = false;
  let pauseUntil = 0;

  function tick(timestamp: number) {
    if (cancelled) return;

    // Handle pauses at punctuation boundaries
    if (timestamp < pauseUntil) {
      requestAnimationFrame(tick);
      return;
    }

    // Advance characters
    const nextIndex = Math.min(currentIndex + charsPerFrame, fullText.length);

    // Check for pause triggers in the newly revealed characters
    for (let i = currentIndex; i < nextIndex; i++) {
      const char = fullText[i];
      const nextChar = i + 1 < fullText.length ? fullText[i + 1] : '';

      if (char === PARAGRAPH_CHAR && nextChar === PARAGRAPH_CHAR) {
        // Paragraph break: pause longer
        pauseUntil = timestamp + paragraphPause;
      } else if (SENTENCE_ENDS.has(char) && (nextChar === ' ' || nextChar === PARAGRAPH_CHAR || nextChar === '')) {
        // Sentence end: brief pause
        pauseUntil = timestamp + sentencePause;
      }
    }

    currentIndex = nextIndex;
    onProgress?.(currentIndex);

    if (currentIndex >= fullText.length) {
      onComplete?.();
      return;
    }

    requestAnimationFrame(tick);
  }

  requestAnimationFrame(tick);

  return {
    cancel() {
      cancelled = true;
    },
  };
}
