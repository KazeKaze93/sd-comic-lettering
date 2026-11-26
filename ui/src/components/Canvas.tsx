import { useEffect, useRef, useState, type DragEvent } from 'react'
import { api } from '../api'
import { useStore } from '../store'
import type { SceneItem, Slot } from '../types'

/** The largest size with the image's proportions that fits the element. */
function useFit(width: number, height: number) {
  const ref = useRef<HTMLDivElement>(null)
  const [size, setSize] = useState({ width: 0, height: 0 })
  useEffect(() => {
    const element = ref.current
    if (!element) return
    const measure = () => {
      const scale = Math.min(element.clientWidth / width, element.clientHeight / height)
      setSize({ width: Math.floor(width * scale), height: Math.floor(height * scale) })
    }
    measure()
    const observer = new ResizeObserver(measure)
    observer.observe(element)
    return () => observer.disconnect()
  }, [width, height])
  return { ref, size }
}

function boxOf(item: SceneItem, slot: Slot): [number, number, number, number] | null {
  if (item.kind === 'bubble') return item.bubble === undefined ? null : (slot.bubbles[item.bubble] ?? null)
  if (item.kind === 'sfx') {
    if (item.x === undefined || item.y === undefined || !item.nominal) return null
    return [item.x, item.y, item.x + item.nominal[0], item.y + item.nominal[1]]
  }
  return item.box ?? null
}

const NAMES: Record<SceneItem['kind'], string> = {
  bubble: 'bubble',
  caption: 'caption',
  balloon: 'drawn bubble',
  sfx: 'effect',
}

/** Frames over the image: every bubble found, and everything that was drawn. */
function Frames({ slot, scale }: { slot: Slot; scale: number }) {
  const filled = new Set(slot.items.filter((item) => item.kind === 'bubble').map((item) => item.bubble))
  // Labels keep one size on screen whatever the size of the image.
  const label = 12 / Math.max(scale, 0.01)
  return (
    <svg
      viewBox={`0 0 ${slot.width} ${slot.height}`}
      className="pointer-events-none absolute inset-0 h-full w-full"
      aria-hidden="true"
    >
      {slot.bubbles.map((box, index) => (
        <g key={`found-${index}`}>
          <rect
            x={box[0]}
            y={box[1]}
            width={box[2] - box[0]}
            height={box[3] - box[1]}
            fill="none"
            stroke={filled.has(index) ? 'rgb(var(--cl-accent))' : 'rgb(var(--cl-warning))'}
            strokeDasharray={filled.has(index) ? undefined : '6 4'}
            vectorEffect="non-scaling-stroke"
            strokeWidth={1.5}
          />
          <text x={box[0] + 3} y={box[1] - 4} fontSize={label} fill="rgb(var(--cl-accent))" stroke="black" strokeWidth={label / 6} paintOrder="stroke">
            {index + 1}
          </text>
        </g>
      ))}
      {slot.items
        .filter((item) => item.kind !== 'bubble')
        .map((item, index) => {
          const box = boxOf(item, slot)
          if (!box) return null
          return (
            <g key={`item-${index}`}>
              <rect
                x={box[0]}
                y={box[1]}
                width={box[2] - box[0]}
                height={box[3] - box[1]}
                fill="none"
                stroke="rgb(var(--cl-accent))"
                strokeDasharray="2 3"
                vectorEffect="non-scaling-stroke"
                strokeWidth={1.5}
              />
              <text x={box[0] + 3} y={box[1] - 4} fontSize={label} fill="rgb(var(--cl-accent))" stroke="black" strokeWidth={label / 6} paintOrder="stroke">
                {NAMES[item.kind]}
              </text>
            </g>
          )
        })}
    </svg>
  )
}

function Picture({ slot }: { slot: Slot }) {
  const showOriginal = useStore((state) => state.showOriginal)
  const showFrames = useStore((state) => state.showFrames)
  const { ref, size } = useFit(slot.width, slot.height)
  const which = showOriginal || slot.empty ? 'original' : 'result'
  return (
    <div ref={ref} className="flex min-h-0 flex-1 items-center justify-center">
      {size.width > 0 && (
        <div className="relative" style={{ width: size.width, height: size.height }}>
          <img
            src={api.imageUrl(slot.session, which, which === 'original' ? 0 : slot.version)}
            alt={which === 'original' ? 'The original image' : 'The lettered image'}
            className="h-full w-full select-none"
            draggable={false}
          />
          {showFrames && !showOriginal && <Frames slot={slot} scale={size.width / slot.width} />}
        </div>
      )}
    </div>
  )
}

/** Where an image is chosen: a click opens the file picker, a drop takes the file. */
function DropZone() {
  const loadFile = useStore((state) => state.loadFile)
  const input = useRef<HTMLInputElement>(null)
  const [over, setOver] = useState(false)
  const take = (file: File | undefined) => {
    if (file && file.type.startsWith('image/')) void loadFile(file, file.name)
  }
  const drop = (event: DragEvent) => {
    event.preventDefault()
    setOver(false)
    take(event.dataTransfer.files[0])
  }
  return (
    <button
      type="button"
      onClick={() => input.current?.click()}
      onDragOver={(event) => {
        event.preventDefault()
        setOver(true)
      }}
      onDragLeave={() => setOver(false)}
      onDrop={drop}
      className={`flex min-h-0 flex-1 flex-col items-center justify-center gap-2 rounded border border-dashed text-sm ${
        over ? 'border-cl-accent text-cl-text' : 'border-cl-border text-cl-muted hover:border-cl-muted'
      }`}
    >
      <span>Drop an image here, or click to choose one</span>
      <span className="text-xs">PNG, JPEG or WebP. It stays on this machine.</span>
      <input
        ref={input}
        type="file"
        accept="image/*"
        className="hidden"
        onChange={(event) => {
          take(event.target.files?.[0])
          event.target.value = ''
        }}
      />
    </button>
  )
}

export function Canvas() {
  const source = useStore((state) => state.source)
  const slot = useStore((state) => state.slots[state.source])
  const hostImage = useStore((state) => state.hostImage)
  const loadFile = useStore((state) => state.loadFile)

  let body
  if (slot) body = <Picture slot={slot} />
  else if (source === 'own') body = <DropZone />
  else
    body = (
      <div className="flex min-h-0 flex-1 items-center justify-center text-sm text-cl-muted">
        {hostImage ? 'The gallery is empty: generate an image first.' : 'Waiting for the image…'}
      </div>
    )

  return (
    <div
      className="flex min-h-0 min-w-0 flex-1 flex-col bg-cl-bg p-3"
      onDragOver={(event) => {
        if (source === 'own') event.preventDefault()
      }}
      onDrop={(event) => {
        if (source !== 'own') return
        event.preventDefault()
        const file = event.dataTransfer.files[0]
        if (file && file.type.startsWith('image/')) void loadFile(file, file.name)
      }}
    >
      {body}
    </div>
  )
}
