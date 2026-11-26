import { useEffect } from 'react'
import { onHostMessage, tellHost } from './bridge'
import { Canvas } from './components/Canvas'
import { SidePanel } from './components/SidePanel'
import { ToolRail } from './components/ToolRail'
import { Button, Icon, IconButton, Select } from './components/controls'
import { useStore } from './store'
import type { Source, Tool } from './types'

const SOURCES: { value: Source; label: string }[] = [
  { value: 'generation', label: 'From generation' },
  { value: 'own', label: 'Own image' },
]

/** The keys that pick a tool, by their place on the keyboard: they work in any layout. */
const TOOL_KEYS: Record<string, Tool> = { KeyV: 'off', KeyB: 'bubble', KeyP: 'brush', KeyE: 'eraser' }

// Text entry keeps Escape for itself: the first Esc leaves the field (its onBlur applies the text), the next one closes the editor.
const TEXT_INPUT_TYPES = new Set(['text', 'number', 'search', ''])
function isTextEntry(target: EventTarget | null): target is HTMLElement {
  if (!(target instanceof HTMLElement)) return false
  if (target.isContentEditable || target instanceof HTMLTextAreaElement) return true
  return target instanceof HTMLInputElement && TEXT_INPUT_TYPES.has(target.type)
}

/** Says whether new images are lettered by themselves, and leads to the setting. */
function AutoChip() {
  const auto = useStore((state) => state.auto)
  return (
    <button
      type="button"
      aria-label={`Automatic mode: ${auto ? 'on' : 'off'}. Show the setting`}
      title={`Automatic mode: ${auto ? 'on' : 'off'}. Show the setting`}
      onClick={() => {
        // The setting is in a part of the panel that may be folded: unfold it, then go there.
        useStore.getState().setOpen('auto', true)
        requestAnimationFrame(() => {
          const toggle = document.getElementById('cl-auto-toggle')
          toggle?.scrollIntoView({ block: 'center' })
          toggle?.focus()
        })
      }}
      className={`inline-flex h-6 shrink-0 items-center gap-1 rounded-full border px-2 text-[11px] ${
        auto ? 'border-cl-accent bg-cl-accent/20 text-cl-accent-text' : 'border-cl-border text-cl-muted hover:text-cl-text'
      }`}
    >
      <Icon size={12}>
        <path d="M9 1.5L3.5 9H8l-1 5.5L12.5 7H8z" />
      </Icon>
      {auto ? 'Auto on' : 'Auto off'}
    </button>
  )
}

function TopBar() {
  const embedded = useStore((state) => state.embedded)
  const comfy = useStore((state) => state.comfy)
  const source = useStore((state) => state.source)
  const slot = useStore((state) => state.slots[state.source])
  const showOriginal = useStore((state) => state.showOriginal)
  const showFrames = useStore((state) => state.showFrames)
  const canUndo = useStore((state) => state.canUndo)
  const canRedo = useStore((state) => state.canRedo)
  const { setSource, setShowOriginal, setShowFrames, save, undo, redo } = useStore.getState()
  const sourceLabel = SOURCES.find((entry) => entry.value === source)?.label ?? ''
  return (
    <header className="flex shrink-0 items-center gap-2 border-b border-cl-border bg-cl-surface px-3 py-2">
      <span className="text-sm font-medium">Comic Lettering</span>
      {embedded && (
        <div className="ml-2 w-40">
          <Select
            ariaLabel="Image source"
            value={sourceLabel}
            options={SOURCES.map((entry) => entry.label)}
            onChange={(label) => {
              const picked = SOURCES.find((entry) => entry.label === label)
              if (picked) setSource(picked.value)
            }}
          />
        </div>
      )}
      <IconButton label="Undo (Ctrl+Z)" disabled={!canUndo} onClick={undo}>
        <Icon>
          <path d="M5 3L2 6l3 3M2 6h7.5a3.5 3.5 0 010 7H7" />
        </Icon>
      </IconButton>
      <IconButton label="Redo (Ctrl+Shift+Z)" disabled={!canRedo} onClick={redo}>
        <Icon>
          <path d="M11 3l3 3-3 3M14 6H6.5a3.5 3.5 0 000 7H9" />
        </Icon>
      </IconButton>
      <span className="flex-1" />
      <IconButton label="Frames and areas (F)" active={showFrames} onClick={() => setShowFrames(!showFrames)}>
        <Icon>
          <path d="M2 5V2h3M11 2h3v3M14 11v3h-3M5 14H2v-3" />
          <rect x="5" y="5" width="6" height="6" />
        </Icon>
      </IconButton>
      <Button
        variant="quiet"
        active={showOriginal}
        disabled={!slot}
        onHold={setShowOriginal}
        title="Hold to compare (C): shows the image without the lettering while it is held"
      >
        <Icon>
          <path d="M1.5 8s2.5-4.5 6.5-4.5S14.5 8 14.5 8 12 12.5 8 12.5 1.5 8 1.5 8z" />
          <circle cx="8" cy="8" r="2" />
        </Icon>
        Hold to compare
      </Button>
      {embedded && !comfy && <AutoChip />}
      <Button
        variant={comfy ? 'primary' : 'plain'}
        disabled={!slot}
        onClick={() => void save()}
        title="Save the way the host saves its own images: same folder, file names and format"
      >
        Save
      </Button>
      {embedded && !comfy && (
        <Button
          variant="primary"
          disabled={!slot}
          onClick={() => slot && tellHost({ type: 'SDCL_TO_GALLERY', session: slot.session })}
          title="Show this image in the gallery it came from"
        >
          To gallery
        </Button>
      )}
      {embedded && (
        <Button onClick={() => tellHost({ type: 'SDCL_CLOSE' })} title="Close (Esc)">
          Close
        </Button>
      )}
    </header>
  )
}

function StatusLine() {
  const busy = useStore((state) => state.busy)
  const status = useStore((state) => state.status)
  const warning = useStore((state) => state.warning)
  const error = useStore((state) => state.error)
  const pinned = useStore((state) => {
    const slot = state.slots[state.source]
    return slot ? Object.keys(slot.pins).length : 0
  })
  const tone = error ? 'bg-cl-danger' : warning ? 'bg-cl-warning' : 'bg-cl-accent'
  const text = error ?? (busy ? 'Working…' : status)
  return (
    <footer className="flex h-8 shrink-0 items-center gap-2 border-t border-cl-border bg-cl-surface px-3 text-xs" aria-live="polite">
      {text && <span className={`h-2 w-2 shrink-0 rounded-full ${tone} ${busy && !error ? 'animate-pulse' : ''}`} />}
      <span className={`min-w-0 truncate ${error ? 'text-cl-danger' : 'text-cl-muted'}`}>{text}</span>
      {pinned > 0 && (
        <span className="ml-auto shrink-0 whitespace-nowrap text-cl-muted">
          {pinned} placed by hand ·{' '}
          <button
            type="button"
            title="Hand everything placed by hand back to the automatic placement"
            onClick={() => useStore.getState().clearPins()}
            className="text-cl-accent-text hover:underline"
          >
            Place all automatically
          </button>
        </span>
      )}
    </footer>
  )
}

export default function App() {
  // Store actions come from getState(): this effect runs once.
  useEffect(() => {
    const embedded = window.parent !== window
    const stop = onHostMessage((message) => {
      if (message.type === 'SDCL_INIT') {
        document.documentElement.dataset.theme = message.theme
        void useStore.getState().hostOpened(message.image, message.node)
        // The keys reach this page without a click on it first.
        window.focus()
      }
    })
    void useStore
      .getState()
      .start(embedded)
      .then(() => tellHost({ type: 'SDCL_READY' }))
    const key = (event: KeyboardEvent) => {
      // Undo and redo, by the key's place so that any keyboard layout works; a text field keeps its own.
      const mod = event.ctrlKey || event.metaKey
      if (mod && !isTextEntry(event.target)) {
        if (event.code === 'KeyZ' && !event.shiftKey) {
          event.preventDefault()
          useStore.getState().undo()
          return
        }
        if ((event.code === 'KeyZ' && event.shiftKey) || event.code === 'KeyY') {
          event.preventDefault()
          useStore.getState().redo()
          return
        }
      }
      // One-letter keys for the tools and the view: only where no text is being typed.
      if (!mod && !event.altKey && !isTextEntry(event.target)) {
        const state = useStore.getState()
        const hasImage = state.slots[state.source] !== null
        if (event.code in TOOL_KEYS) {
          if (!hasImage) return
          event.preventDefault()
          state.setTool(TOOL_KEYS[event.code])
          return
        }
        if (event.code === 'KeyN') {
          if (!state.region) return
          event.preventDefault()
          state.pickRegion(null)
          return
        }
        if (event.code === 'KeyF') {
          event.preventDefault()
          state.setShowFrames(!state.showFrames)
          return
        }
        if (event.code === 'KeyC') {
          if (!hasImage) return
          event.preventDefault()
          // Held down, the key repeats: the first press is enough.
          if (!event.repeat) state.setShowOriginal(true)
          return
        }
      }
      if (event.key !== 'Escape' || event.defaultPrevented) return
      if (isTextEntry(event.target)) {
        event.preventDefault()
        event.target.blur()
        return
      }
      tellHost({ type: 'SDCL_CLOSE' })
    }
    const keyUp = (event: KeyboardEvent) => {
      if (event.code === 'KeyC') useStore.getState().setShowOriginal(false)
    }
    // A key or a button let go outside this page is never heard of: stop comparing when the page loses the keyboard.
    const away = () => useStore.getState().setShowOriginal(false)
    window.addEventListener('keydown', key)
    window.addEventListener('keyup', keyUp)
    window.addEventListener('blur', away)
    return () => {
      stop()
      window.removeEventListener('keydown', key)
      window.removeEventListener('keyup', keyUp)
      window.removeEventListener('blur', away)
    }
  }, [])

  return (
    <div className="flex h-screen flex-col bg-cl-bg text-cl-text">
      <TopBar />
      <div className="flex min-h-0 flex-1">
        <ToolRail />
        <div className="flex min-w-0 flex-1 flex-col">
          <Canvas />
          <StatusLine />
        </div>
        <SidePanel />
      </div>
    </div>
  )
}
