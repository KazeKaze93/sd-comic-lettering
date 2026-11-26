import { useEffect, useRef, useState, type ReactNode } from 'react'

export function Label({ children }: { children: ReactNode }) {
  return <span className="text-xs text-cl-muted">{children}</span>
}

export function Button({
  children,
  onClick,
  active,
  title,
  disabled,
  variant = 'plain',
}: {
  children: ReactNode
  onClick?: () => void
  active?: boolean
  title?: string
  disabled?: boolean
  variant?: 'plain' | 'quiet'
}) {
  const look =
    variant === 'quiet'
      ? 'text-cl-muted hover:text-cl-text'
      : `border border-cl-border ${active ? 'bg-cl-accent/20 text-cl-accent-text' : 'bg-cl-raised hover:border-cl-muted'}`
  return (
    <button
      type="button"
      title={title}
      disabled={disabled}
      onClick={onClick}
      className={`inline-flex h-7 items-center gap-1.5 rounded px-2 text-xs disabled:opacity-40 ${look}`}
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
}: {
  checked: boolean
  onChange: (value: boolean) => void
  label: string
}) {
  return (
    <label className="flex cursor-pointer items-center gap-2 text-xs text-cl-text">
      <input
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
}: {
  label: string
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
      <Label>{label}</Label>
      <button
        type="button"
        aria-haspopup="listbox"
        aria-expanded={open}
        onClick={() => setOpen(!open)}
        className="mt-0.5 flex h-7 w-full items-center justify-between gap-1 rounded border border-cl-border bg-cl-raised px-2 text-left text-xs hover:border-cl-muted"
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
