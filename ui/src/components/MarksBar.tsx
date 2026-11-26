import { useEffect, useRef, useState, type MouseEvent, type ReactNode } from 'react'
import { flushSync } from 'react-dom'
import { useStore } from '../store'
import { Icon } from './controls'

/** A mark as the renderer draws it, in the color of the text around; the plain character when
 * the server sent no shape for it. */
export function MarkGlyph({ symbol }: { symbol: string }) {
  const index = useStore((state) => state.options?.marks?.findIndex((mark) => mark.symbol === symbol) ?? -1)
  if (index < 0) return <span className="cl-mark-char">{symbol}</span>
  return <span aria-hidden="true" className={`cl-mark cl-mark-${index}`} />
}

/** A mark's name as words: "heart_line" is "heart line". Without a name, the character itself. */
function readable(symbol: string, name?: string) {
  return name ? name.replace(/_/g, ' ') : symbol
}

// A press on a button of the bar must not take the keyboard away from the text field: the
// field would apply itself as if left, and forget where its caret was.
const keepFocus = (event: MouseEvent) => event.preventDefault()

const TOOL = 'flex shrink-0 items-center justify-center rounded hover:bg-cl-raised'
// A word on the bar is quiet until pointed at; a mark is in the color of the text it will stand in.
const WORD = 'text-cl-muted hover:text-cl-text'

/** Is this a letter of a word? Anything but a blank and the star that marks emphasis. */
const inWord = (char: string | undefined) => char !== undefined && !/[\s*]/.test(char)

/** The bar over a text field: make a word bigger, put in one of the marks used last, pick any
 * other mark, empty the field.
 *
 * It changes the text and nothing else: the field applies itself as always, when it is left or
 * on Ctrl+Enter. */
export function MarksBar({
  target,
  value,
  onChange,
  onClear,
  label,
}: {
  /** The text field the bar belongs to. */
  target: () => HTMLTextAreaElement | null
  value: string
  onChange: (next: string) => void
  /** Empties the field; without it the bar has no Clear. */
  onClear?: () => void
  /** What the field is called, for a screen reader: "Bubbles". */
  label: string
}) {
  const marks = useStore((state) => state.options?.marks)
  const symbols = useStore((state) => state.options?.symbols)
  const recent = useStore((state) => state.recentMarks)
  const [open, setOpen] = useState(false)
  const root = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!open) return
    const away = (event: globalThis.MouseEvent) => {
      if (!root.current?.contains(event.target as Node)) setOpen(false)
    }
    // Before the field and the editor hear of it: Escape closes the picker and nothing more.
    const key = (event: KeyboardEvent) => {
      if (event.key !== 'Escape') return
      event.stopPropagation()
      event.preventDefault()
      setOpen(false)
      target()?.focus()
    }
    document.addEventListener('mousedown', away)
    document.addEventListener('keydown', key, true)
    return () => {
      document.removeEventListener('mousedown', away)
      document.removeEventListener('keydown', key, true)
    }
    // `target` is a new function on every render of the panel; the field it gives is the same.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open])

  /** Put a new text into the field and leave its caret (or what is picked out) where it belongs. */
  const write = (next: string, from: number, to: number) => {
    // The field has to hold the new text before a place in it can be picked.
    flushSync(() => onChange(next))
    const field = target()
    if (!field) return
    field.focus()
    field.setSelectionRange(from, to)
  }

  const place = () => {
    const field = target()
    const start = field?.selectionStart ?? value.length
    const end = field?.selectionEnd ?? start
    return { start: Math.min(start, value.length), end: Math.min(end, value.length) }
  }

  const insert = (symbol: string) => {
    const { start, end } = place()
    const before = value.slice(0, start)
    const lead = before && !/\s$/.test(before) ? ' ' : ''
    const caret = before.length + lead.length + symbol.length
    write(before + lead + symbol + value.slice(end), caret, caret)
    useStore.getState().useMark(symbol)
  }

  /** Stars round a word make it bigger. */
  const emphasise = () => {
    let { start, end } = place()
    if (start === end) {
      // No letters picked out: the word the caret is in or beside.
      while (start > 0 && inWord(value[start - 1])) start -= 1
      while (end < value.length && inWord(value[end])) end += 1
      if (start === end) {
        // No word here: the two stars, ready for one to be typed between them.
        write(`${value.slice(0, start)}**${value.slice(end)}`, start + 1, start + 1)
        return
      }
    }
    const picked = value.slice(start, end)
    const starred = (picked.length >= 2 && picked.startsWith('*') && picked.endsWith('*')) || (value[start - 1] === '*' && value[end] === '*')
    if (starred) {
      // Bigger already: nothing to add, only keep it picked out.
      write(value, start, end)
      return
    }
    write(`${value.slice(0, start)}*${picked}*${value.slice(end)}`, start + 1, end + 1)
  }

  const nameOf = (symbol: string) => readable(symbol, marks?.find((mark) => mark.symbol === symbol)?.name)
  const markButton = (symbol: string, size: string) => (
    <button
      key={symbol}
      type="button"
      title={`Insert ${nameOf(symbol)}`}
      aria-label={`Insert ${nameOf(symbol)}`}
      onMouseDown={keepFocus}
      onClick={() => {
        setOpen(false)
        insert(symbol)
      }}
      className={`${TOOL} text-cl-text ${size}`}
    >
      <MarkGlyph symbol={symbol} />
    </button>
  )

  // The marks by group, in the order the server gives them; one group of all when it gives none.
  const groups: [string, string[]][] = []
  if (marks?.length) {
    for (const mark of marks) {
      const last = groups[groups.length - 1]
      if (last && last[0] === mark.group) last[1].push(mark.symbol)
      else groups.push([mark.group, [mark.symbol]])
    }
  } else if (symbols?.length) groups.push(['Marks', symbols])

  let picker: ReactNode = null
  if (open) {
    picker = (
      <div
        role="dialog"
        aria-label="All marks"
        className="absolute left-0 top-full z-20 mt-1 flex w-[264px] max-w-[calc(100vw-16px)] flex-col gap-2 rounded border border-cl-border bg-cl-surface p-2 shadow-lg"
      >
        {groups.map(([group, list]) => (
          <div key={group} className="flex flex-col gap-1">
            <div className="text-[11px] text-cl-muted">{group}</div>
            <div className="flex flex-wrap gap-0.5 text-[16px] text-cl-text">{list.map((symbol) => markButton(symbol, 'h-[26px] w-[26px]'))}</div>
          </div>
        ))}
      </div>
    )
  }

  return (
    <div
      ref={root}
      role="toolbar"
      aria-label={`${label}: marks and emphasis`}
      className="relative flex h-7 items-center gap-0.5 rounded-t border border-b-0 border-cl-border bg-cl-surface px-1"
    >
      <button
        type="button"
        title="Make the word bigger (*word*)"
        aria-label="Make the word bigger (*word*)"
        onMouseDown={keepFocus}
        onClick={emphasise}
        className={`${TOOL} ${WORD} h-6 px-1.5 text-xs font-bold`}
      >
        A+
      </button>
      <span className="mx-0.5 h-4 w-px shrink-0 bg-cl-border" aria-hidden="true" />
      <span className="flex items-center gap-0.5 text-[14px] text-cl-text">{recent.map((symbol) => markButton(symbol, 'h-6 w-6'))}</span>
      <button
        type="button"
        title="All marks"
        aria-haspopup="dialog"
        aria-expanded={open}
        onMouseDown={keepFocus}
        onClick={() => setOpen(!open)}
        className={`${TOOL} ${WORD} h-6 gap-0.5 px-1.5 text-xs`}
      >
        More
        <Icon size={10}>
          <path d="M3.5 6l4.500 4.500L12.500 6" />
        </Icon>
      </button>
      <span className="flex-1" />
      {onClear && (
        <button type="button" onMouseDown={keepFocus} onClick={onClear} className={`${TOOL} ${WORD} h-6 px-1.5 text-xs`}>
          Clear
        </button>
      )}
      {picker}
    </div>
  )
}
