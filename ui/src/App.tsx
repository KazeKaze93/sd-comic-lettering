import { useEffect } from 'react'
import { onHostMessage, tellHost } from './bridge'
import { Canvas } from './components/Canvas'
import { SidePanel } from './components/SidePanel'
import { Button, Segmented, Toggle } from './components/controls'
import { useStore } from './store'
import type { Source } from './types'

const SOURCES: { value: Source; label: string }[] = [
  { value: 'generation', label: 'From generation' },
  { value: 'own', label: 'Own image' },
]

// Text entry keeps Escape for itself: the first Esc leaves the field (its onBlur applies the text), the next one closes the editor.
const TEXT_INPUT_TYPES = new Set(['text', 'number', 'search', ''])
function isTextEntry(target: EventTarget | null): target is HTMLElement {
  if (!(target instanceof HTMLElement)) return false
  if (target.isContentEditable || target instanceof HTMLTextAreaElement) return true
  return target instanceof HTMLInputElement && TEXT_INPUT_TYPES.has(target.type)
}

function TopBar() {
  const embedded = useStore((state) => state.embedded)
  const comfy = useStore((state) => state.comfy)
  const source = useStore((state) => state.source)
  const slot = useStore((state) => state.slots[state.source])
  const showOriginal = useStore((state) => state.showOriginal)
  const showFrames = useStore((state) => state.showFrames)
  const pinned = slot ? Object.keys(slot.pins).length : 0
  const { setSource, setShowOriginal, setShowFrames, save, clearPins } = useStore.getState()
  return (
    <header className="flex shrink-0 items-center gap-2 border-b border-cl-border bg-cl-surface px-3 py-2">
      <span className="text-sm font-medium">Comic Lettering</span>
      {embedded && (
        <div className="ml-2 w-64">
          <Segmented value={source} options={SOURCES} onChange={setSource} />
        </div>
      )}
      <span className="flex-1" />
      {pinned > 0 && (
        <Button onClick={() => clearPins()} title="Hand everything placed by hand back to the automatic placement">
          Place all automatically
        </Button>
      )}
      <Toggle checked={showFrames} onChange={setShowFrames} label="Frames and areas" />
      <Button active={showOriginal} disabled={!slot} onClick={() => setShowOriginal(!showOriginal)}>
        Original
      </Button>
      <Button disabled={!slot} onClick={() => void save()} title="Save the way the host saves its own images: same folder, file names and format">
        Save
      </Button>
      {embedded && !comfy && (
        <Button
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
  const tone = error ? 'bg-cl-danger' : warning ? 'bg-cl-warning' : 'bg-cl-accent'
  const text = error ?? (busy ? 'Working…' : status)
  return (
    <footer className="flex h-8 shrink-0 items-center gap-2 border-t border-cl-border bg-cl-surface px-3 text-xs" aria-live="polite">
      {text && <span className={`h-2 w-2 shrink-0 rounded-full ${tone} ${busy && !error ? 'animate-pulse' : ''}`} />}
      <span className={`truncate ${error ? 'text-cl-danger' : 'text-cl-muted'}`}>{text}</span>
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
      }
    })
    void useStore
      .getState()
      .start(embedded)
      .then(() => tellHost({ type: 'SDCL_READY' }))
    const key = (event: KeyboardEvent) => {
      if (event.key !== 'Escape' || event.defaultPrevented) return
      if (isTextEntry(event.target)) {
        event.preventDefault()
        event.target.blur()
        return
      }
      tellHost({ type: 'SDCL_CLOSE' })
    }
    window.addEventListener('keydown', key)
    return () => {
      stop()
      window.removeEventListener('keydown', key)
    }
  }, [])

  return (
    <div className="flex h-screen flex-col bg-cl-bg text-cl-text">
      <TopBar />
      <div className="flex min-h-0 flex-1">
        <div className="flex min-w-0 flex-1 flex-col">
          <Canvas />
          <StatusLine />
        </div>
        <SidePanel />
      </div>
    </div>
  )
}
