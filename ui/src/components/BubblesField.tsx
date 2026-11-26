import { useEffect, useId, useLayoutEffect, useRef, useState } from 'react'
import type { LineFate } from '../lines'

const MARK = 18 // a marker's height, in pixels
const PILL = 'flex h-[18px] min-w-[18px] items-center justify-center rounded-full px-1 text-[10px] font-bold leading-none'

/** What stands in the gutter beside a line. */
function Marker({ fate }: { fate: LineFate }) {
  if (fate.kind === 'bubble') return <span className={`${PILL} bg-cl-accent text-cl-on-accent`}>{fate.number}</span>
  // The bubble is left empty on purpose: its number, hollow.
  if (fate.kind === 'skip') return <span className={`${PILL} border border-dashed border-cl-accent text-cl-accent-text`}>{fate.number}</span>
  if (fate.kind === 'pending') return <span className={`${PILL} border border-dashed border-cl-border text-cl-muted`}>{fate.number}</span>
  if (fate.kind === 'caption') return <span className="flex h-[18px] items-center text-[10px] text-cl-muted">cap</span>
  return <span className="flex h-[18px] items-center px-1 text-[10px] text-cl-warning">—</span>
}

/** The same, said in words for someone who cannot see the gutter. */
function spoken(fate: LineFate, line: number) {
  if (fate.kind === 'bubble') return `Line ${line}: bubble ${fate.number}.`
  if (fate.kind === 'skip') return `Line ${line}: empty, leaves bubble ${fate.number} empty.`
  if (fate.kind === 'caption') return `Line ${line}: caption.`
  if (fate.kind === 'pending') return `Line ${line}: not drawn yet.`
  return `Line ${line}: fits no bubble.`
}

/** The Bubbles text field, with a gutter that says for each line where it went.
 *
 * The field is a plain textarea that wraps its lines, so a line of text may take several rows.
 * To know where each line starts, the same text is laid out in a hidden copy of the field: same
 * font, padding and width, one block per line. The top of a block is the top of its line. */
export function BubblesField({
  value,
  fates,
  onChange,
  onBlurCommit,
  onCtrlEnter,
  onFocus,
  placeholder,
  rows = 3,
  textareaRef,
}: {
  value: string
  /** One entry per line of the text; lines past the end of it get no marker. */
  fates: LineFate[]
  onChange: (value: string) => void
  onBlurCommit: () => void
  onCtrlEnter: () => void
  onFocus: () => void
  placeholder: string
  rows?: number
  textareaRef: (element: HTMLTextAreaElement | null) => void
}) {
  const field = useRef<HTMLTextAreaElement | null>(null)
  const mirror = useRef<HTMLDivElement>(null)
  const gutter = useRef<HTMLDivElement>(null)
  const [tops, setTops] = useState<number[]>([])
  // Raised whenever the field changes size, to measure again.
  const [resized, setResized] = useState(0)
  const summaryId = useId()

  useEffect(() => {
    const element = field.current
    if (!element) return
    const observer = new ResizeObserver(() => setResized((count) => count + 1))
    observer.observe(element)
    return () => observer.disconnect()
  }, [])

  // Lay the copy out as the field is, then read where each line starts.
  useLayoutEffect(() => {
    const element = field.current
    const copy = mirror.current
    if (!element || !copy) return
    const style = window.getComputedStyle(element)
    const side = (name: string) => parseFloat(style.getPropertyValue(name)) || 0
    copy.style.fontFamily = style.fontFamily
    copy.style.fontSize = style.fontSize
    copy.style.fontWeight = style.fontWeight
    copy.style.fontStyle = style.fontStyle
    copy.style.lineHeight = style.lineHeight
    copy.style.letterSpacing = style.letterSpacing
    copy.style.wordSpacing = style.wordSpacing
    copy.style.tabSize = style.tabSize
    copy.style.textTransform = style.textTransform
    copy.style.paddingTop = style.paddingTop
    copy.style.paddingBottom = style.paddingBottom
    copy.style.paddingLeft = style.paddingLeft
    copy.style.paddingRight = style.paddingRight
    // As wide as the text has room in the field: without its frame and without its scroll bar.
    copy.style.width = `${element.clientWidth - side('padding-left') - side('padding-right')}px`
    const frame = side('border-top-width')
    const row = parseFloat(style.lineHeight) || MARK
    const next = Array.from(copy.children).map((child) => (child as HTMLElement).offsetTop + frame + (row - MARK) / 2)
    setTops((current) => (current.length === next.length && current.every((top, index) => top === next[index]) ? current : next))
    if (gutter.current) gutter.current.style.transform = `translateY(${-element.scrollTop}px)`
  }, [value, resized])

  const lines = value.replace(/\r/g, '').split('\n')
  const explain = fates.some((fate) => fate.kind === 'caption' || fate.kind === 'none')
  return (
    <div>
      <div className="relative">
        <textarea
          ref={(element) => {
            field.current = element
            textareaRef(element)
          }}
          value={value}
          rows={rows}
          placeholder={placeholder}
          spellCheck={false}
          aria-describedby={summaryId}
          onFocus={onFocus}
          onChange={(event) => onChange(event.target.value)}
          onBlur={onBlurCommit}
          onScroll={(event) => {
            if (gutter.current) gutter.current.style.transform = `translateY(${-event.currentTarget.scrollTop}px)`
          }}
          onKeyDown={(event) => {
            if (event.key === 'Enter' && (event.ctrlKey || event.metaKey)) onCtrlEnter()
          }}
          className="block w-full resize-y rounded border border-cl-border bg-cl-raised py-1.5 pl-9 pr-2 text-sm placeholder:text-cl-muted"
        />
        {/* The gutter stands in the field's left padding and moves with its text. */}
        <div className="pointer-events-none absolute inset-y-0 left-0 w-9 overflow-hidden" aria-hidden="true">
          <div ref={gutter}>
            {fates.map((fate, index) =>
              tops[index] === undefined ? null : (
                <span key={index} className="absolute left-1.5 flex w-6 justify-center" style={{ top: tops[index] }}>
                  <Marker fate={fate} />
                </span>
              ),
            )}
          </div>
        </div>
        <div
          ref={mirror}
          aria-hidden="true"
          className="pointer-events-none invisible absolute left-0 top-0 box-content whitespace-pre-wrap break-words"
          style={{ overflowWrap: 'break-word' }}
        >
          {lines.map((line, index) => (
            // An empty line still takes a row: a letter of no width keeps it.
            <div key={index}>{line || '​'}</div>
          ))}
        </div>
      </div>
      {explain && <p className="mt-1 text-[11px] leading-snug text-cl-muted">cap: went to the caption · —: did not fit any bubble</p>}
      <span id={summaryId} className="sr-only" aria-live="polite">
        {fates.map((fate, index) => spoken(fate, index + 1)).join(' ')}
      </span>
    </div>
  )
}
