/**
 * Narrative text processing — ported from ui/components.py.
 *
 * Converts raw narrator prose into structured paragraph data
 * with dialogue detection.
 */

export interface NarrativeParagraph {
  text: string;
  isDialogue: boolean;
}

/**
 * Strip any residual markdown/structural formatting from narrative text.
 * Last line of defense before rendering.
 */
export function stripMarkdownArtifacts(text: string): string {
  let result = text;
  // Strip markdown bold/italic wrappers: **text**, *text*
  result = result.replace(/\*{1,2}(.+?)\*{1,2}/g, '$1');
  result = result.replace(/_{1,2}(.+?)_{1,2}/g, '$1');
  // Strip markdown headers: ## Something, # Something
  result = result.replace(/^#{1,3}\s+/gm, '');
  // Strip fenced code block markers
  result = result.replace(/^```\w*\s*$/gm, '');
  // Strip section labels at line start
  result = result.replace(
    /^(?:Scene|Narrative|Next Turn|Opening|Summary|Description|Dialogue|Action|Response|Output|Result|Setting|Atmosphere|Continue|Continuation)\s*:\s*/gim,
    ''
  );
  // Strip NPC_LINE separators and SPEAKER lines that leaked from LLM
  result = result.replace(/---?\s*NPC[_\s-]?LINE\s*---?/gi, '');
  result = result.replace(/^\s*SPEAKER:\s*.+$/gm, '');
  // Collapse multiple blank lines
  result = result.replace(/\n{3,}/g, '\n\n');
  return result.trim();
}

/**
 * Parse raw narrator prose into structured paragraphs with dialogue detection.
 */
export function parseNarrative(rawText: string): NarrativeParagraph[] {
  const cleaned = stripMarkdownArtifacts(rawText);
  const rawParagraphs = cleaned.split(/\n\n+/).filter((p) => p.trim());

  return rawParagraphs
    .map((para) => {
      const trimmed = para.trim();
      if (!trimmed) return null;
      // Skip structural junk (e.g., just "---" or "{}")
      if (/^[-=]{3,}$/.test(trimmed) || /^\{.*\}$/s.test(trimmed)) return null;

      // Detect dialogue: starts with a quote mark or contains speech attribution
      const isDialogue =
        /^["\u201c]/.test(trimmed) ||
        /^.{0,30}\s+(?:said|says|asked|replied|whispered|growled|muttered)/i.test(trimmed);

      return { text: trimmed, isDialogue };
    })
    .filter((p): p is NarrativeParagraph => p !== null);
}

/**
 * Split a narrative text word-by-word for streaming display.
 */
export function splitWords(text: string): string[] {
  return text.split(/(\s+)/).filter((w) => w.length > 0);
}
