import { useEffect, useRef, useState, type ReactNode } from 'react'

export function Label({ children }: { children: ReactNode }) {
  return <span className="text-xs text-cl-muted">{children}</span>
}

/** An icon drawn with lines on a 16 by 16 grid, in the color of the text around it. */
export function Icon({ children, size = 16 }: { children: ReactNode; size?: number }) {
  return (
    <svg viewBox="0 0 16 16" width={size} height={size} fill="none" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      {children}
    </svg>
  )
}

/** A part of the panel that folds away under its title. Folded, it says in a line what it holds. */
export function Section({
  id,
  title,
  summary,
  open,
  onToggle,
  actions,
  children,
}: {
  id: string
  title: string
  /** Shown beside the title while the section is folded. */
  summary?: string
  open: boolean
  onToggle: (open: boolean) => void
  /** Buttons at the right of the title, while the section is open. */
  actions?: ReactNode
  children: ReactNode
}) {
  return (
    <section className="flex flex-col gap-2 border-t border-cl-border pt-3 first:border-t-0 first:pt-0">
      <div className="flex items-center gap-2">
        <button
          type="button"
          aria-expanded={open}
          aria-controls={`${id}-body`}
          onClick={() => onToggle(!open)}
          className="flex h-7 min-w-0 flex-1 items-center gap-1.5 text-left text-cl-text"
        >
          <span className="shrink-0 text-cl-muted">
            <Icon size={12}>{open ? <path d="M3.5 6l4.500 4.500L12.500 6" /> : <path d="M6 3.500l4.500 4.500L6 12.500" />}</Icon>
          </span>
          <span className="shrink-0 text-xs font-semibold">{title}</span>
          {!open && summary && <span className="min-w-0 flex-1 truncate text-right text-[11px] text-cl-muted">{summary}</span>}
        </button>
        {open && actions && <span className="flex shrink-0 items-center gap-1">{actions}</span>}
      </div>
      {open && (
        <div id={`${id}-body`} className="flex flex-col gap-2">
          {children}
        </div>
      )}
    </section>
  )
}

type ButtonVariant = 'plain' | 'quiet' | 'primary'

export function Button({
  children,
  onClick,
  active,
  title,
  disabled,
  variant = 'plain',
  onHold,
}: {
  children: ReactNode
  onClick?: () => void
  active?: boolean
  title?: string
  disabled?: boolean
  variant?: ButtonVariant
  /** For a button that acts while it is held down: told true on press and false on release. */
  onHold?: (held: boolean) => void
}) {
  return (
    <button
      type="button"
      title={title}
      disabled={disabled}
      onClick={onClick}
      onPointerDown={onHold && (() => onHold(true))}
      onPointerUp={onHold && (() => onHold(false))}
      onPointerLeave={onHold && (() => onHold(false))}
      onPointerCancel={onHold && (() => onHold(false))}
      className={`inline-flex h-7 items-center gap-1.5 rounded px-2 text-xs disabled:opacity-40 ${buttonLook(variant, active)}`}
    >
      {children}
    </button>
  )
}

/** How a button is painted: with a frame, quiet until pointed at, or as the one to press; an active one stands out. */
function buttonLook(variant: ButtonVariant, active?: boolean) {
  if (variant === 'primary') return 'border border-cl-accent bg-cl-accent font-semibold text-cl-on-accent hover:bg-cl-accent/85'
  // A quiet button keeps an unseen frame, so that turning active does not move its neighbours.
  if (variant === 'quiet' && !active) return 'border border-transparent text-cl-muted hover:text-cl-text'
  return `border border-cl-border ${active ? 'bg-cl-accent/20 text-cl-accent-text' : 'bg-cl-raised hover:border-cl-muted'}`
}

/** A square button that shows only an icon; `label` is what it is called and its tooltip. */
export function IconButton({
  label,
  onClick,
  disabled,
  active,
  children,
}: {
  label: string
  onClick?: () => void
  disabled?: boolean
  active?: boolean
  children: ReactNode
}) {
  return (
    <button
      type="button"
      aria-label={label}
      title={label}
      disabled={disabled}
      onClick={onClick}
      className={`inline-flex h-7 w-7 shrink-0 items-center justify-center rounded disabled:opacity-40 ${buttonLook('quiet', active)}`}
    >
      {children}
    </button>
  )
}

export function Segmented<T extends string>({
  value,
  options,
  onChange,
}: {
  value: T
  options: { value: T; label: string }[]
  onChange: (value: T) => void
}) {
  return (
    <div className="flex overflow-hidden rounded border border-cl-border text-xs" role="tablist">
      {options.map((option) => (
        <button
          key={option.value}
          type="button"
          role="tab"
          aria-selected={option.value === value}
          onClick={() => onChange(option.value)}
          className={`flex-1 px-2 py-1 ${
            option.value === value ? 'bg-cl-accent/20 text-cl-accent-text' : 'text-cl-muted hover:text-cl-text'
          }`}
        >
          {option.label}
        </button>
      ))}
    </div>
  )
}

export function Toggle({
  checked,
  onChange,
  label,
  id,
}: {
  checked: boolean
  onChange: (value: boolean) => void
  label: string
  id?: string
}) {
  return (
    <label className="flex cursor-pointer items-center gap-2 text-xs text-cl-text">
      <input
        id={id}
        type="checkbox"
        checked={checked}
        onChange={(event) => onChange(event.target.checked)}
        className="h-3.5 w-3.5 accent-[rgb(var(--cl-accent))]"
      />
      {label}
    </label>
  )
}

/** A list that can draw each entry in its own font. Closes on a second click, Escape or a click outside. */
export function Select({
  label,
  value,
  options,
  onChange,
  fontOf,
  ariaLabel,
}: {
  /** Shown above the list. Without it nothing is shown, and `ariaLabel` names the list instead. */
  label?: string
  ariaLabel?: string
  value: string
  options: string[]
  onChange: (value: string) => void
  fontOf?: (option: string) => string | undefined
}) {
  const [open, setOpen] = useState(false)
  const root = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!open) return
    const close = (event: MouseEvent) => {
      if (!root.current?.contains(event.target as Node)) setOpen(false)
    }
    const key = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        event.stopPropagation()
        setOpen(false)
      }
    }
    document.addEventListener('mousedown', close)
    document.addEventListener('keydown', key, true)
    return () => {
      document.removeEventListener('mousedown', close)
      document.removeEventListener('keydown', key, true)
    }
  }, [open])

  return (
    <div ref={root} className="relative min-w-0">
      {label !== undefined && <Label>{label}</Label>}
      <button
        type="button"
        aria-haspopup="listbox"
        aria-expanded={open}
        aria-label={label === undefined ? ariaLabel : undefined}
        onClick={() => setOpen(!open)}
        className={`${label === undefined ? '' : 'mt-0.5 '}flex h-7 w-full items-center justify-between gap-1 rounded border border-cl-border bg-cl-raised px-2 text-left text-xs hover:border-cl-muted`}
      >
        <span className="truncate" style={{ fontFamily: fontOf?.(value) }}>
          {value}
        </span>
        <span className="text-cl-muted" aria-hidden="true">
          ▾
        </span>
      </button>
      {open && (
        <ul
          role="listbox"
          className="absolute left-0 right-0 z-20 mt-1 max-h-64 overflow-auto rounded border border-cl-border bg-cl-raised py-1 shadow-lg"
        >
          {options.map((option) => (
            <li
              key={option}
              role="option"
              aria-selected={option === value}
              onClick={() => {
                setOpen(false)
                if (option !== value) onChange(option)
              }}
              style={{ fontFamily: fontOf?.(option) }}
              className={`cursor-pointer truncate px-2 py-1 ${fontOf ? 'text-base' : 'text-xs'} ${
                option === value ? 'bg-cl-accent/20 text-cl-accent-text' : 'hover:bg-cl-border/60'
              }`}
            >
              {option}
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}

/** A slider with its number. The value is reported while dragging; `onCommit` fires when it is let go. */
export function Slider({
  label,
  value,
  min,
  max,
  step,
  onChange,
  onCommit,
}: {
  label: string
  value: number
  min: number
  max: number
  step: number
  onChange: (value: number) => void
  onCommit: () => void
}) {
  const clamp = (raw: number) => Math.min(max, Math.max(min, raw))
  return (
    <label className="block min-w-0">
      <span className="flex items-baseline justify-between gap-2">
        <Label>{label}</Label>
        <input
          type="number"
          value={value}
          min={min}
          max={max}
          step={step}
          onChange={(event) => {
            const parsed = Number(event.target.value)
            if (!Number.isNaN(parsed)) onChange(clamp(parsed))
          }}
          onBlur={onCommit}
          onKeyDown={(event) => {
            if (event.key === 'Enter') onCommit()
          }}
          className="h-5 w-14 rounded border border-cl-border bg-cl-raised px-1 text-right text-xs"
        />
      </span>
      <input
        type="range"
        value={value}
        min={min}
        max={max}
        step={step}
        onChange={(event) => onChange(Number(event.target.value))}
        onPointerUp={onCommit}
        onKeyUp={onCommit}
        className="mt-1 w-full accent-[rgb(var(--cl-accent))]"
      />
    </label>
  )
}

export function TextInput({
  label,
  value,
  onChange,
  onCommit,
}: {
  label: string
  value: string
  onChange: (value: string) => void
  onCommit: () => void
}) {
  return (
    <label className="block min-w-0">
      <Label>{label}</Label>
      <input
        type="text"
        value={value}
        onChange={(event) => onChange(event.target.value)}
        onBlur={onCommit}
        onKeyDown={(event) => {
          if (event.key === 'Enter') onCommit()
        }}
        className="mt-0.5 h-7 w-full rounded border border-cl-border bg-cl-raised px-2 text-xs"
      />
    </label>
  )
}
