import type { SceneItem } from './types'

/** Where a line of the Bubbles field went. */
export type LineFate =
  | { kind: 'bubble'; number: number } // into the bubble with this number (1-based, as on the image)
  | { kind: 'skip'; number: number } // an empty line: it left this bubble empty
  | { kind: 'caption' } // it fitted no bubble and went to the caption
  | { kind: 'none' } // it went nowhere: no bubble took it and nothing spills, or an empty line with no bubble left
  | { kind: 'pending'; number: number } // the text has changed since the image was drawn: a guess, line by line

/** The lines of the Bubbles field as the core reads them (comic_lettering/core.py, arrange()):
 * split at line breaks, each one trimmed, the empty ones at the end dropped. What a line asks
 * for its own bubble ("|" for a break inside it, "[6]" for its size) stays in the line: the
 * core reads it, and the scene gives the line back whole as the item's text. */
export function bubbleLines(text: string): string[] {
  const lines = text
    .replace(/\r/g, '')
    .split('\n')
    .map((line) => line.trim())
  while (lines.length && !lines[lines.length - 1]) lines.pop()
  return lines
}

/** Where each line of the Bubbles field went, one entry per line of bubbleLines(text).
 *
 * The core decides this (core.py, _assign(), lines 704-736) and is the only truth; it does not
 * say it line by line, only which bubbles got which text. So this walks the lines the way the
 * core does and takes the scene for an oracle: a line went into a bubble if the scene has that
 * text in a bubble. What the core does that this repeats:
 * - a line tries the free bubbles in order and takes the first it fits; the bubbles it passed
 *   over on the way stay used up;
 * - an empty line uses up the first free bubble;
 * - a line that fits none uses up none, and goes to the caption when spilling is on.
 *
 * applied: the inputs of the last finished render (Slot.applied), whose first entry is the text.
 * While the text differs from it the scene is of another text, and every line is "pending". */
export function lineFates(text: string, applied: string | null, items: SceneItem[], bubbleCount: number, spill: boolean): LineFate[] {
  const lines = bubbleLines(text)
  let drawn: unknown = null
  try {
    drawn = applied ? (JSON.parse(applied) as unknown[])[0] : null
  } catch {
    drawn = null
  }
  if (drawn !== text) return lines.map((_, index) => ({ kind: 'pending', number: index + 1 }))

  const taken: boolean[] = new Array<boolean>(bubbleCount).fill(false)
  const placed = items.filter((item) => item.kind === 'bubble' && typeof item.bubble === 'number')
  const used = new Set<SceneItem>()
  return lines.map((line): LineFate => {
    if (!line) {
      const free = taken.indexOf(false)
      if (free < 0) return { kind: 'none' }
      taken[free] = true
      return { kind: 'skip', number: free + 1 }
    }
    const item = placed.find((candidate) => !used.has(candidate) && candidate.text === line)
    if (!item) return spill ? { kind: 'caption' } : { kind: 'none' }
    used.add(item)
    const index = item.bubble as number
    // The bubbles it tried before this one are used up too.
    for (let passed = 0; passed <= index && passed < bubbleCount; passed += 1) taken[passed] = true
    return { kind: 'bubble', number: index + 1 }
  })
}
