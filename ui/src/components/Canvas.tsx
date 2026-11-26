import { useEffect, useRef, useState, type DragEvent, type PointerEvent as ReactPointerEvent } from 'react'
import { api } from '../api'
import { useStore } from '../store'
import type { Pin, Region, SceneItem, Shape, Slot } from '../types'

/** Keep receiving the pointer while it is down, where the browser allows it. */
function capture(event: ReactPointerEvent) {
  try {
    event.currentTarget.setPointerCapture(event.pointerId)
  } catch {
    // A pointer the browser does not know (a scripted one): the drag still works inside the element.
  }
}

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

/** Where an item stands, in image pixels: its middle, its size and its tilt. */
interface Place {
  cx: number
  cy: number
  width: number
  height: number
  rotation: number
}

function placeOf(item: SceneItem): Place | null {
  if (item.kind === 'sfx') {
    if (item.x === undefined || item.y === undefined || !item.nominal) return null
    return {
      cx: item.x + item.nominal[0] / 2,
      cy: item.y + item.nominal[1] / 2,
      width: item.nominal[0],
      height: item.nominal[1],
      rotation: item.rotation ?? 0,
    }
  }
  if (!item.box) return null
  const [x0, y0, x1, y1] = item.box
  return {
    cx: item.kind === 'caption' && item.cx !== undefined ? item.cx : (x0 + x1) / 2,
    cy: item.kind === 'caption' && item.cy !== undefined ? item.cy : (y0 + y1) / 2,
    width: x1 - x0,
    height: y1 - y0,
    rotation: item.kind === 'caption' ? (item.rotation ?? 0) : 0,
  }
}

const NAMES: Record<SceneItem['kind'], string> = {
  bubble: 'bubble',
  caption: 'caption',
  balloon: 'drawn bubble',
  sfx: 'effect',
  region: 'area',
  path: 'area',
}

const TINTS: Record<Region['kind'], string> = {
  text: 'rgb(var(--cl-accent))',
  sfx: 'rgb(var(--cl-warning))',
  keepout: 'rgb(var(--cl-danger))',
}

function pathOf(points: [number, number][], closed: boolean) {
  return points.map(([x, y], index) => `${index ? 'L' : 'M'}${x.toFixed(1)} ${y.toFixed(1)}`).join(' ') + (closed ? ' Z' : '')
}

/** A shape in one flat color: white paints and black rubs out when it is used inside a mask. */
function ShapePath({ shape, color }: { shape: Shape; color: string }) {
  if (shape.type === 'polygon') return <path d={pathOf(shape.points, true)} fill={color} />
  return (
    <path
      d={pathOf(shape.points.length > 1 ? shape.points : [shape.points[0], shape.points[0]], false)}
      fill="none"
      stroke={color}
      strokeWidth={shape.width}
      strokeLinecap="round"
      strokeLinejoin="round"
    />
  )
}

/** The areas drawn by hand, tinted by what they are for; the one being drawn into stands out. */
function Areas({ slot, drawing }: { slot: Slot; drawing: Shape | null }) {
  const picked = useStore((state) => state.region)
  return (
    <svg viewBox={`0 0 ${slot.width} ${slot.height}`} className="pointer-events-none absolute inset-0 h-full w-full" aria-hidden="true">
      {slot.regions.map((region) => (
        // What the area covers is its shapes in the order they were drawn: paint, then rub out.
        <g key={region.id}>
          <mask id={`area-${region.id}`} maskUnits="userSpaceOnUse" x={0} y={0} width={slot.width} height={slot.height}>
            {region.shapes.map((shape, index) => (
              <ShapePath key={index} shape={shape} color={shape.type === 'erase' ? 'black' : 'white'} />
            ))}
          </mask>
          <rect
            width={slot.width}
            height={slot.height}
            fill={TINTS[region.kind]}
            fillOpacity={region.id === picked ? 0.4 : 0.22}
            mask={`url(#area-${region.id})`}
          />
        </g>
      ))}
      {drawing && (
        <g opacity={0.45}>
          <ShapePath shape={drawing} color={drawing.type === 'erase' ? 'rgb(var(--cl-bg))' : 'rgb(var(--cl-text))'} />
        </g>
      )}
    </svg>
  )
}

/** Catches the pointer while a drawing tool is on and turns each drag into a shape. */
function DrawLayer({ slot, scale, onDraw }: { slot: Slot; scale: number; onDraw: (shape: Shape | null) => void }) {
  const tool = useStore((state) => state.tool)
  const brush = useStore((state) => state.brush)
  const points = useRef<[number, number][] | null>(null)
  const width = Math.max(4, Math.round(brush * Math.min(slot.width, slot.height)))

  const at = (event: ReactPointerEvent): [number, number] => {
    const rect = event.currentTarget.getBoundingClientRect()
    const x = Math.min(slot.width, Math.max(0, (event.clientX - rect.left) / scale))
    const y = Math.min(slot.height, Math.max(0, (event.clientY - rect.top) / scale))
    return [Math.round(x * 10) / 10, Math.round(y * 10) / 10]
  }
  const shapeOf = (list: [number, number][]): Shape =>
    tool === 'brush'
      ? { type: 'stroke', points: list, width }
      : tool === 'eraser'
        ? { type: 'erase', points: list, width }
        : { type: 'polygon', points: list }

  return (
    <div
      className="absolute inset-0 touch-none"
      style={{ cursor: 'crosshair' }}
      onPointerDown={(event) => {
        if (event.button !== 0) return
        event.stopPropagation()
        capture(event)
        points.current = [at(event)]
        onDraw(shapeOf(points.current))
      }}
      onPointerMove={(event) => {
        const list = points.current
        if (!list) return
        const next = at(event)
        const last = list[list.length - 1]
        // A point every few screen pixels is plenty.
        if (Math.hypot(next[0] - last[0], next[1] - last[1]) * scale < 3) return
        list.push(next)
        onDraw(shapeOf([...list]))
      }}
      onPointerUp={(event) => {
        const list = points.current
        points.current = null
        onDraw(null)
        if (event.currentTarget.hasPointerCapture(event.pointerId)) event.currentTarget.releasePointerCapture(event.pointerId)
        if (!list) return
        // An outline needs to enclose something; a dab of the brush is enough.
        if (tool === 'lasso' && list.length < 6) return
        useStore.getState().addShape(shapeOf(list))
      }}
      onPointerCancel={() => {
        points.current = null
        onDraw(null)
      }}
    />
  )
}

/** Frames of the bubbles found in the art: numbered in reading order, dashed if left empty. */
function FoundBubbles({ slot, scale }: { slot: Slot; scale: number }) {
  const filled = new Set(slot.items.filter((item) => item.kind === 'bubble').map((item) => item.bubble))
  const label = 12 / Math.max(scale, 0.01) // one size on screen whatever the size of the image
  return (
    <svg viewBox={`0 0 ${slot.width} ${slot.height}`} className="pointer-events-none absolute inset-0 h-full w-full" aria-hidden="true">
      {slot.bubbles.map((box, index) => (
        <g key={index}>
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
    </svg>
  )
}

type Gesture = 'move' | 'size' | 'turn'

/** What a drag has changed so far, before the server has drawn it. */
interface Pending {
  id: string
  dx: number
  dy: number
  factor: number
  turn: number
}

const STILL: Omit<Pending, 'id'> = { dx: 0, dy: 0, factor: 1, turn: 0 }

/** A frame that can be dragged, with a corner to resize it and a knob to turn it. */
function Handle({ item, slot, scale }: { item: SceneItem; slot: Slot; scale: number }) {
  const id = item.id as string
  const selected = useStore((state) => state.selected === id)
  const { select, setPin, clearPins } = useStore.getState()
  const [pending, setPending] = useState<Pending | null>(null)
  const gesture = useRef<{ kind: Gesture; x: number; y: number; moved: boolean } | null>(null)
  const frame = useRef<HTMLDivElement>(null)
  const place = placeOf(item)

  // The server's answer replaces what the drag showed meanwhile.
  useEffect(() => setPending(null), [slot.version])

  if (!place) return null
  const pinned = id in slot.pins
  const canTurn = item.kind !== 'balloon'
  const shown = pending ?? { id, ...STILL }
  const cx = (place.cx + shown.dx) * scale
  const cy = (place.cy + shown.dy) * scale
  const width = place.width * shown.factor * scale
  const height = place.height * shown.factor * scale
  // The image turns counter-clockwise for a positive tilt; CSS turns clockwise.
  const angle = -(place.rotation + shown.turn)

  /** Everything about the item as it stands, so that changing one thing moves nothing else. */
  const pinNow = (): Pin => ({
    cx: place.cx,
    cy: place.cy,
    size: item.size,
    rotation: canTurn ? place.rotation : undefined,
    reach: item.reach,
    tall: item.tall,
    ...slot.pins[id],
  })

  const middle = () => {
    const rect = frame.current?.parentElement?.getBoundingClientRect()
    return { x: (rect?.left ?? 0) + cx, y: (rect?.top ?? 0) + cy }
  }

  const begin = (kind: Gesture) => (event: ReactPointerEvent) => {
    if (event.button !== 0) return
    event.stopPropagation()
    event.preventDefault()
    capture(event)
    gesture.current = { kind, x: event.clientX, y: event.clientY, moved: false }
    select(id)
  }

  const drag = (event: ReactPointerEvent) => {
    const active = gesture.current
    if (!active) return
    const dx = event.clientX - active.x
    const dy = event.clientY - active.y
    if (!active.moved && Math.hypot(dx, dy) < 3) return
    active.moved = true
    if (active.kind === 'move') {
      setPending({ id, ...STILL, dx: dx / scale, dy: dy / scale })
      return
    }
    const center = middle()
    if (active.kind === 'size') {
      const before = Math.hypot(active.x - center.x, active.y - center.y)
      const now = Math.hypot(event.clientX - center.x, event.clientY - center.y)
      setPending({ id, ...STILL, factor: Math.min(6, Math.max(0.2, now / Math.max(before, 1))) })
      return
    }
    const before = Math.atan2(active.y - center.y, active.x - center.x)
    const now = Math.atan2(event.clientY - center.y, event.clientX - center.x)
    setPending({ id, ...STILL, turn: -((now - before) * 180) / Math.PI })
  }

  const end = (event: ReactPointerEvent) => {
    const active = gesture.current
    gesture.current = null
    if (event.currentTarget.hasPointerCapture(event.pointerId)) event.currentTarget.releasePointerCapture(event.pointerId)
    if (!active || !active.moved || !pending) return
    const pin = pinNow()
    if (active.kind === 'move') {
      pin.cx = Math.min(slot.width, Math.max(0, place.cx + pending.dx))
      pin.cy = Math.min(slot.height, Math.max(0, place.cy + pending.dy))
    } else if (active.kind === 'size') {
      pin.size = Math.round(Math.min(slot.height * 0.6, Math.max(8, item.size * pending.factor)))
    } else {
      let turned = place.rotation + pending.turn
      while (turned > 180) turned -= 360
      while (turned < -180) turned += 360
      pin.rotation = Math.round(turned * 2) / 2
    }
    setPin(id, pin)
  }

  const border = selected ? 'border-cl-accent' : pinned ? 'border-cl-accent/80' : 'border-cl-accent/50 hover:border-cl-accent'
  return (
    <div
      ref={frame}
      className="absolute"
      style={{ left: cx, top: cy, width, height, transform: `translate(-50%, -50%) rotate(${angle}deg)` }}
    >
      <div
        role="button"
        tabIndex={0}
        aria-label={`${NAMES[item.kind]}: ${item.text}. Drag to move.`}
        onPointerDown={begin('move')}
        onPointerMove={drag}
        onPointerUp={end}
        onPointerCancel={end}
        onKeyDown={(event) => {
          // Arrow keys nudge the item; Delete hands it back to the automatic placement.
          const step = event.shiftKey ? 10 : 1
          const by: Record<string, [number, number]> = { ArrowLeft: [-step, 0], ArrowRight: [step, 0], ArrowUp: [0, -step], ArrowDown: [0, step] }
          if (event.key in by) {
            event.preventDefault()
            const pin = pinNow()
            setPin(id, { ...pin, cx: (pin.cx ?? place.cx) + by[event.key][0], cy: (pin.cy ?? place.cy) + by[event.key][1] })
          } else if ((event.key === 'Delete' || event.key === 'Backspace') && pinned) {
            event.preventDefault()
            clearPins(id)
          }
        }}
        onFocus={() => select(id)}
        className={`h-full w-full cursor-move touch-none rounded-sm border ${selected || pinned ? 'border-solid' : 'border-dashed'} ${border} ${
          selected ? 'bg-cl-accent/10' : ''
        } outline-none`}
      />
      <span className="pointer-events-none absolute -top-5 left-0 whitespace-nowrap rounded bg-black/60 px-1 text-[11px] leading-4 text-cl-accent-text">
        {NAMES[item.kind]}
        {pinned ? ' · placed by hand' : ''}
      </span>
      {selected && (
        <>
          <div
            title="Drag to resize"
            onPointerDown={begin('size')}
            onPointerMove={drag}
            onPointerUp={end}
            onPointerCancel={end}
            className="absolute -bottom-1.5 -right-1.5 h-3 w-3 cursor-nwse-resize touch-none rounded-sm border border-black/60 bg-cl-accent"
          />
          {canTurn && (
            <div
              title="Drag to turn"
              onPointerDown={begin('turn')}
              onPointerMove={drag}
              onPointerUp={end}
              onPointerCancel={end}
              className="absolute -top-6 left-1/2 h-3 w-3 -translate-x-1/2 cursor-grab touch-none rounded-full border border-black/60 bg-cl-accent"
            />
          )}
          {pinned && (
            <button
              type="button"
              onPointerDown={(event) => event.stopPropagation()}
              onClick={() => clearPins(id)}
              className="absolute -bottom-7 left-0 whitespace-nowrap rounded border border-cl-border bg-cl-raised px-1.5 text-[11px] leading-5 text-cl-text hover:border-cl-muted"
            >
              Place automatically
            </button>
          )}
        </>
      )}
    </div>
  )
}

function Picture({ slot }: { slot: Slot }) {
  const showOriginal = useStore((state) => state.showOriginal)
  const showFrames = useStore((state) => state.showFrames)
  const tool = useStore((state) => state.tool)
  const [drawing, setDrawing] = useState<Shape | null>(null)
  const { ref, size } = useFit(slot.width, slot.height)
  const which = showOriginal || slot.empty ? 'original' : 'result'
  const scale = size.width / slot.width
  return (
    <div ref={ref} className="flex min-h-0 flex-1 items-center justify-center" onPointerDown={() => useStore.getState().select(null)}>
      {size.width > 0 && (
        <div className="relative" style={{ width: size.width, height: size.height }}>
          <img
            src={api.imageUrl(slot.session, which, which === 'original' ? 0 : slot.version)}
            alt={which === 'original' ? 'The original image' : 'The lettered image'}
            className="h-full w-full select-none"
            draggable={false}
          />
          {showFrames && !showOriginal && (
            <>
              <FoundBubbles slot={slot} scale={scale} />
              <Areas slot={slot} drawing={drawing} />
              {tool === 'off' &&
                slot.items
                  .filter((item) => item.id && item.kind !== 'region' && item.kind !== 'path' && item.region === undefined)
                  .map((item) => <Handle key={item.id} item={item} slot={slot} scale={scale} />)}
            </>
          )}
          {tool !== 'off' && !showOriginal && <DrawLayer slot={slot} scale={scale} onDraw={setDrawing} />}
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
