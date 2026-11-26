import { useEffect, useRef, useState, type DragEvent, type PointerEvent as ReactPointerEvent } from 'react'
import { api } from '../api'
import { boxOf, bubbleShapes, placeHandles, turned, type Box, type CornerSide, type KnobSide } from '../geometry'
import { useStore } from '../store'
import type { Pin, Region, SceneItem, Shape, Slot } from '../types'
import { Button } from './controls'

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
  // The room the element itself has: the picture stands in its middle.
  const [room, setRoom] = useState({ width: 0, height: 0 })
  useEffect(() => {
    const element = ref.current
    if (!element) return
    const measure = () => {
      const scale = Math.min(element.clientWidth / width, element.clientHeight / height)
      setSize({ width: Math.floor(width * scale), height: Math.floor(height * scale) })
      setRoom({ width: element.clientWidth, height: element.clientHeight })
    }
    measure()
    const observer = new ResizeObserver(measure)
    observer.observe(element)
    return () => observer.disconnect()
  }, [width, height])
  return { ref, size, room }
}

/** The part of the canvas that can be seen, in screen pixels counted from the picture's corner. */
interface View {
  left: number
  top: number
  right: number
  bottom: number
}

/** A frame on the picture that a handle must not sit on: whose it is, and its box in screen pixels. */
interface Frame {
  id: string | null
  box: Box
}

/** Colors by where a thing comes from: found or placed by the script, placed or drawn by hand, kept clear. */
type Tone = 'auto' | 'hand' | 'keepout'
const TONES: Record<Tone, { border: string; soft: string; faint: string; wash: string; fill: string; text: string }> = {
  auto: {
    border: 'border-cl-accent',
    soft: 'border-cl-accent/80',
    faint: 'border-cl-accent/50 hover:border-cl-accent',
    wash: 'bg-cl-accent/10',
    fill: 'bg-cl-accent',
    text: 'text-cl-accent',
  },
  hand: {
    border: 'border-cl-hand',
    soft: 'border-cl-hand/80',
    faint: 'border-cl-hand/50 hover:border-cl-hand',
    wash: 'bg-cl-hand/10',
    fill: 'bg-cl-hand',
    text: 'text-cl-hand',
  },
  keepout: {
    border: 'border-cl-danger',
    soft: 'border-cl-danger/80',
    faint: 'border-cl-danger/50 hover:border-cl-danger',
    wash: 'bg-cl-danger/10',
    fill: 'bg-cl-danger',
    text: 'text-cl-danger',
  },
}

/** Where the turn knob and its stem stand, by side. An item's knob is 42 pixels out, an area's 34. */
const KNOBS: Record<'item' | 'area', { reach: number; knob: Record<KnobSide, string>; stem: Record<KnobSide, string> }> = {
  item: {
    reach: 42,
    knob: {
      top: '-top-[52px] left-1/2 -translate-x-1/2',
      bottom: '-bottom-[52px] left-1/2 -translate-x-1/2',
      right: '-right-[52px] top-1/2 -translate-y-1/2',
      left: '-left-[52px] top-1/2 -translate-y-1/2',
    },
    stem: {
      top: '-top-9 left-1/2 h-9 w-px -translate-x-1/2',
      bottom: '-bottom-9 left-1/2 h-9 w-px -translate-x-1/2',
      right: '-right-9 top-1/2 h-px w-9 -translate-y-1/2',
      left: '-left-9 top-1/2 h-px w-9 -translate-y-1/2',
    },
  },
  area: {
    reach: 34,
    knob: {
      top: '-top-[44px] left-1/2 -translate-x-1/2',
      bottom: '-bottom-[44px] left-1/2 -translate-x-1/2',
      right: '-right-[44px] top-1/2 -translate-y-1/2',
      left: '-left-[44px] top-1/2 -translate-y-1/2',
    },
    stem: {
      top: '-top-7 left-1/2 h-7 w-px -translate-x-1/2',
      bottom: '-bottom-7 left-1/2 h-7 w-px -translate-x-1/2',
      right: '-right-7 top-1/2 h-px w-7 -translate-y-1/2',
      left: '-left-7 top-1/2 h-px w-7 -translate-y-1/2',
    },
  },
}

const CORNERS: Record<CornerSide, string> = {
  br: '-bottom-1.5 -right-1.5 cursor-nwse-resize',
  bl: '-bottom-1.5 -left-1.5 cursor-nesw-resize',
  tr: '-top-1.5 -right-1.5 cursor-nesw-resize',
  tl: '-top-1.5 -left-1.5 cursor-nwse-resize',
}

/** A small round number: on a found bubble, and before a step of what to do first. */
function Pill({ children }: { children: number }) {
  return (
    <span className="inline-block h-[18px] min-w-[18px] shrink-0 rounded-full bg-cl-accent px-1 text-center text-[11px] font-bold leading-[18px] text-cl-on-accent ring-2 ring-cl-bg">
      {children}
    </span>
  )
}

/** The arrow going round, on a turn knob. */
function TurnIcon() {
  return (
    <svg viewBox="0 0 16 16" width="12" height="12" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="M13 8a5 5 0 1 1-1.6-3.7" />
      <path d="M13.2 2.6v2.8h-2.8" />
    </svg>
  )
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

// What the hand drew is in the color of the hand; an area to keep clear warns.
const TINTS: Record<Region['kind'], string> = {
  text: 'rgb(var(--cl-hand))',
  sfx: 'rgb(var(--cl-hand))',
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

/** How an area's tint follows a drag before anything is redrawn: moved, and resized or turned about its middle. */
function nudged(region: Region, nudge: { dx: number; dy: number; factor?: number; turn?: number }) {
  const box = boxOf(region.shapes)
  const cx = box ? (box[0] + box[2]) / 2 : 0
  const cy = box ? (box[1] + box[3]) / 2 : 0
  return `translate(${nudge.dx} ${nudge.dy}) rotate(${nudge.turn ?? 0} ${cx} ${cy}) translate(${cx} ${cy}) scale(${nudge.factor ?? 1}) translate(${-cx} ${-cy})`
}

/** The areas drawn by hand, tinted by what they are for; the one being drawn into stands out. */
function Areas({ slot, drawing }: { slot: Slot; drawing: Shape | null }) {
  const picked = useStore((state) => state.region)
  const nudge = useStore((state) => state.nudge)
  const hover = useStore((state) => state.hover)
  const tool = useStore((state) => state.tool)
  // An area that has its text gets out of the way: its tint shows only while it is being
  // worked on. One still waiting for a text stays, or it could not be found again.
  const shown = (region: Region) =>
    region.id === picked ||
    region.id === hover ||
    (nudge !== null && nudge.id === region.id) ||
    tool === 'eraser' ||
    (region.kind === 'keepout' ? tool !== 'off' : !region.text.trim())
  const rubbing = drawing && drawing.type === 'erase' ? drawing : null
  return (
    <svg viewBox={`0 0 ${slot.width} ${slot.height}`} className="pointer-events-none absolute inset-0 h-full w-full" aria-hidden="true">
      {slot.regions.filter(shown).map((region) => (
        // What the area covers is its shapes in the order they were drawn: paint, then rub out.
        <g key={region.id} transform={nudge && nudge.id === region.id ? nudged(region, nudge) : undefined}>
          <mask id={`area-${region.id}`} maskUnits="userSpaceOnUse" x={0} y={0} width={slot.width} height={slot.height}>
            {region.shapes.map((shape, index) => (
              <ShapePath key={index} shape={shape} color={shape.type === 'erase' ? 'black' : 'white'} />
            ))}
            {/* The eraser shows what it takes away while it moves. */}
            {rubbing && <ShapePath shape={rubbing} color="black" />}
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
      {drawing && !rubbing && (
        <g opacity={0.45}>
          <ShapePath shape={drawing} color="rgb(var(--cl-text))" />
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
  const ring = useRef<HTMLDivElement>(null)
  const width = Math.max(4, Math.round(brush * Math.min(slot.width, slot.height)))
  const round = tool === 'brush' || tool === 'eraser'

  /** The ring that shows how wide the brush or the eraser is, where the pointer is. */
  const follow = (event: ReactPointerEvent | null) => {
    const element = ring.current
    if (!element) return
    if (!event) {
      element.style.display = 'none'
      return
    }
    const rect = event.currentTarget.getBoundingClientRect()
    element.style.display = 'block'
    element.style.left = `${event.clientX - rect.left}px`
    element.style.top = `${event.clientY - rect.top}px`
  }

  const at = (event: ReactPointerEvent): [number, number] => {
    const rect = event.currentTarget.getBoundingClientRect()
    const x = Math.min(slot.width, Math.max(0, (event.clientX - rect.left) / scale))
    const y = Math.min(slot.height, Math.max(0, (event.clientY - rect.top) / scale))
    return [Math.round(x * 10) / 10, Math.round(y * 10) / 10]
  }
  const stamp = useStore((state) => state.stamp)
  /** The box a bubble is dragged out to; a click alone gives one of a handy size around the point. */
  const boxOfDrag = (list: [number, number][]): Box => {
    const [ax, ay] = list[0]
    const [bx, by] = list[list.length - 1]
    if (Math.hypot(bx - ax, by - ay) * scale < 12) {
      const half = [0.13 * slot.width, 0.09 * slot.height]
      return [ax - half[0], ay - half[1], ax + half[0], ay + half[1]]
    }
    return [Math.min(ax, bx), Math.min(ay, by), Math.max(ax, bx), Math.max(ay, by)]
  }
  const shapeOf = (list: [number, number][]): Shape =>
    tool === 'brush'
      ? { type: 'stroke', points: list, width }
      : tool === 'eraser'
        ? { type: 'erase', points: list, width }
        : bubbleShapes({ shape: stamp.shape, tail: 'none', box: boxOfDrag(list) })[0]

  return (
    <div
      className="absolute inset-0 touch-none overflow-hidden"
      style={{ cursor: round ? 'none' : 'crosshair' }}
      onPointerLeave={() => follow(null)}
      onPointerDown={(event) => {
        if (event.button !== 0) return
        event.stopPropagation()
        capture(event)
        points.current = [at(event)]
        onDraw(shapeOf(points.current))
      }}
      onPointerMove={(event) => {
        if (round) follow(event)
        const list = points.current
        if (!list) return
        const next = at(event)
        const last = list[list.length - 1]
        // A point every few screen pixels is plenty.
        if (Math.hypot(next[0] - last[0], next[1] - last[1]) * scale < 3) return
        if (tool === 'bubble') list.splice(1, list.length - 1, next)  // a bubble is its two corners
        else list.push(next)
        onDraw(shapeOf([...list]))
      }}
      onPointerUp={(event) => {
        const list = points.current
        points.current = null
        onDraw(null)
        if (event.currentTarget.hasPointerCapture(event.pointerId)) event.currentTarget.releasePointerCapture(event.pointerId)
        if (!list) return
        if (tool === 'bubble') {
          useStore.getState().addBubble(boxOfDrag(list))
          return
        }
        useStore.getState().addShape(shapeOf(list))
      }}
      onPointerCancel={() => {
        points.current = null
        onDraw(null)
      }}
    >
      {round && (
        <div
          ref={ring}
          className="pointer-events-none absolute hidden rounded-full border border-white mix-blend-difference"
          style={{ width: width * scale, height: width * scale, transform: 'translate(-50%, -50%)' }}
        />
      )}
    </div>
  )
}

/** Frames of the bubbles found in the art: numbered in reading order, dashed if left empty. */
function FoundBubbles({ slot, scale }: { slot: Slot; scale: number }) {
  const filled = new Set(slot.items.filter((item) => item.kind === 'bubble').map((item) => item.bubble))
  const wide = slot.width * scale
  const tall = slot.height * scale
  return (
    <>
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
        </g>
      ))}
    </svg>
    {/* The numbers stand on the bubbles' corners, one size on screen whatever the size of the image. */}
    <div className="pointer-events-none absolute inset-0" aria-hidden="true">
      {slot.bubbles.map((box, index) => (
        <span
          key={index}
          className="absolute flex"
          style={{
            left: Math.max(0, Math.min(wide - 18, box[0] * scale - 9)),
            top: Math.max(0, Math.min(tall - 18, box[1] * scale - 9)),
          }}
        >
          <Pill>{index + 1}</Pill>
        </span>
      ))}
    </div>
    </>
  )
}

/** What is shown at once while something is dragged, before the server has drawn it again:
 * the art without lettering where the thing was, and the piece of the lettered image that
 * held it, moved, resized and turned the way the drag says. Rough at the edges, and gone
 * as soon as the real picture arrives. */
function Ghost({
  slot,
  scale,
  box,
  dx = 0,
  dy = 0,
  factor = 1,
  turn = 0,
}: {
  slot: Slot
  scale: number
  box: Box
  dx?: number
  dy?: number
  factor?: number
  turn?: number
}) {
  const left = Math.max(0, box[0]) * scale
  const top = Math.max(0, box[1]) * scale
  const width = (Math.min(slot.width, box[2]) - Math.max(0, box[0])) * scale
  const height = (Math.min(slot.height, box[3]) - Math.max(0, box[1])) * scale
  if (width <= 0 || height <= 0) return null
  const piece = (which: 'original' | 'result') => ({
    left,
    top,
    width,
    height,
    backgroundImage: `url(${api.imageUrl(slot.session, which, which === 'original' ? 0 : slot.version)})`,
    backgroundSize: `${slot.width * scale}px ${slot.height * scale}px`,
    backgroundPosition: `${-left}px ${-top}px`,
  })
  return (
    <>
      <div className="pointer-events-none absolute" style={piece('original')} />
      <div
        className="pointer-events-none absolute"
        style={{ ...piece('result'), transform: `translate(${dx * scale}px, ${dy * scale}px) rotate(${-turn}deg) scale(${factor})` }}
      />
    </>
  )
}

/** The box a tilted frame takes up on the image, with a little room around for outlines. */
function reach(place: Place): Box {
  const angle = (place.rotation * Math.PI) / 180
  const wide = (Math.abs(place.width * Math.cos(angle)) + Math.abs(place.height * Math.sin(angle))) * 1.12
  const tall = (Math.abs(place.width * Math.sin(angle)) + Math.abs(place.height * Math.cos(angle))) * 1.12
  return [place.cx - wide / 2, place.cy - tall / 2, place.cx + wide / 2, place.cy + tall / 2]
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
function Handle({ item, slot, scale, view, frames }: { item: SceneItem; slot: Slot; scale: number; view: View; frames: Frame[] }) {
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

  // Placed by the script or by hand: the frame says which by its color.
  const tone = TONES[pinned ? 'hand' : 'auto']
  const border = selected ? tone.border : pinned ? tone.soft : tone.faint
  // The handles go where they can be reached. Worked out from where the item stands, not
  // from the drag under way: a handle that changed sides under the pointer would be lost.
  const home: [number, number] = [place.cx * scale, place.cy * scale]
  const spots = placeHandles({
    center: home,
    size: [place.width * scale, place.height * scale],
    angle: -place.rotation,
    knobReach: canTurn ? KNOBS.item.reach : 0,
    viewport: view,
    obstacles: frames.filter((frame) => frame.id !== id).map((frame) => frame.box),
    margin: 6,
  })
  // "Place automatically" goes under the frame; above it when there is no room under, and
  // never on the side the knob took.
  const under = turned([[home[0], home[1] + (place.height * scale) / 2 + 18]], home[0], home[1], -place.rotation, 1)[0]
  let buttonAt: 'top' | 'bottom' = under[1] + 12 > view.bottom ? 'top' : 'bottom'
  if (spots.knob === buttonAt) buttonAt = buttonAt === 'top' ? 'bottom' : 'top'
  return (
    <>
    {pending && <Ghost slot={slot} scale={scale} box={reach(place)} dx={pending.dx} dy={pending.dy} factor={pending.factor} turn={pending.turn} />}
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
          selected ? tone.wash : ''
        } outline-none`}
      />
      <span className={`pointer-events-none absolute -top-5 left-0 whitespace-nowrap rounded bg-cl-bg/80 px-1 text-[11px] leading-4 ${tone.text}`}>
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
            className={`absolute ${CORNERS[spots.corner]} h-3 w-3 touch-none rounded-sm border border-cl-bg ${tone.fill}`}
          />
          {spots.knob && (
            <>
              {/* The knob stands clear of the frame, on a stem, so it is seen at once. */}
              <div className={`pointer-events-none absolute ${KNOBS.item.stem[spots.knob]} ${tone.fill}`} />
              <div
                title="Drag to turn"
                aria-label="Drag to turn"
                onPointerDown={begin('turn')}
                onPointerMove={drag}
                onPointerUp={end}
                onPointerCancel={end}
                className={`absolute ${KNOBS.item.knob[spots.knob]} z-10 flex h-5 w-5 cursor-grab touch-none items-center justify-center rounded-full border border-cl-bg ${tone.fill} text-cl-on-accent`}
              >
                <TurnIcon />
              </div>
            </>
          )}
          {pinned && (
            <button
              type="button"
              onPointerDown={(event) => event.stopPropagation()}
              onClick={() => clearPins(id)}
              className={`absolute ${buttonAt === 'bottom' ? '-bottom-7' : '-top-[46px]'} left-0 whitespace-nowrap rounded border border-cl-border bg-cl-raised px-1.5 text-[11px] leading-5 text-cl-text hover:border-cl-muted`}
            >
              Place automatically
            </button>
          )}
        </>
      )}
    </div>
    </>
  )
}

/** With the arrow: a click on an area picks it and brings up its text; a drag moves the area. */
function AreaGrip({ region, slot, scale, view, frames }: { region: Region; slot: Slot; scale: number; view: View; frames: Frame[] }) {
  const start = useRef<{ x: number; y: number; moved: boolean } | null>(null)
  const picked = useStore((state) => state.region === region.id)
  // What the drag showed, kept until the server has drawn the area where it now is.
  const [ghost, setGhost] = useState<{ box: Box; dx: number; dy: number; factor: number; turn: number } | null>(null)
  const reshaping = useRef<{ kind: 'size' | 'turn'; x: number; y: number } | null>(null)
  const grip = useRef<HTMLDivElement>(null)
  useEffect(() => setGhost(null), [slot.version])
  const box = boxOf(region.shapes)
  if (!box) return null
  const shown = ghost ? ghost.box : box

  // The corner resizes the area about its middle and the knob turns it; the text goes along.
  const middle = () => {
    const rect = grip.current?.getBoundingClientRect()
    return rect ? { x: rect.left + rect.width / 2, y: rect.top + rect.height / 2 } : { x: 0, y: 0 }
  }
  const beginReshape = (kind: 'size' | 'turn') => (event: ReactPointerEvent) => {
    if (event.button !== 0) return
    event.stopPropagation()
    event.preventDefault()
    capture(event)
    reshaping.current = { kind, x: event.clientX, y: event.clientY }
  }
  const reshape = (event: ReactPointerEvent) => {
    const from = reshaping.current
    if (!from) return
    const center = middle()
    let factor = 1
    let turn = 0
    if (from.kind === 'size') {
      const before = Math.hypot(from.x - center.x, from.y - center.y)
      factor = Math.min(6, Math.max(0.2, Math.hypot(event.clientX - center.x, event.clientY - center.y) / Math.max(before, 1)))
    } else {
      const before = Math.atan2(from.y - center.y, from.x - center.x)
      turn = ((Math.atan2(event.clientY - center.y, event.clientX - center.x) - before) * 180) / Math.PI
    }
    setGhost({ box, dx: 0, dy: 0, factor, turn })
    useStore.getState().setNudge({ id: region.id, dx: 0, dy: 0, factor, turn })
  }
  const endReshape = (event: ReactPointerEvent) => {
    const from = reshaping.current
    reshaping.current = null
    if (event.currentTarget.hasPointerCapture(event.pointerId)) event.currentTarget.releasePointerCapture(event.pointerId)
    if (!from || !ghost) return
    useStore.getState().transformRegion(region.id, ghost.factor, Math.round(ghost.turn * 2) / 2)
  }
  // The handles stay while they are dragged: taking one away under the pointer would end the drag unfinished.
  const handles = picked
  const tone = TONES[region.kind === 'keepout' ? 'keepout' : 'hand']
  // Where the area stands, not where a drag under way shows it: see Handle.
  const spots = placeHandles({
    center: [((box[0] + box[2]) / 2) * scale, ((box[1] + box[3]) / 2) * scale],
    size: [(box[2] - box[0]) * scale, (box[3] - box[1]) * scale],
    angle: 0,
    knobReach: KNOBS.area.reach,
    viewport: view,
    obstacles: frames.filter((frame) => frame.id !== `area:${region.id}`).map((frame) => frame.box),
    margin: 6,
  })
  const knob = spots.knob ?? 'top'
  return (
    <>
      {ghost && <Ghost slot={slot} scale={scale} box={ghost.box} dx={ghost.dx} dy={ghost.dy} factor={ghost.factor} turn={-ghost.turn} />}
      <div
        ref={grip}
        title="Click to edit this area, drag to move it"
        className={`absolute cursor-move touch-none ${picked ? `rounded-sm border ${tone.border} ${tone.wash}` : ''}`}
        onPointerEnter={() => useStore.getState().setHover(region.id)}
        onPointerLeave={() => useStore.getState().setHover(null)}
        style={{
          left: (shown[0] + (ghost ? ghost.dx : 0)) * scale,
          top: (shown[1] + (ghost ? ghost.dy : 0)) * scale,
          width: (shown[2] - shown[0]) * scale,
          height: (shown[3] - shown[1]) * scale,
        }}
        onPointerDown={(event) => {
          if (event.button !== 0) return
          event.stopPropagation()
          capture(event)
          start.current = { x: event.clientX, y: event.clientY, moved: false }
        }}
        onPointerMove={(event) => {
          const from = start.current
          if (!from) return
          const dx = (event.clientX - from.x) / scale
          const dy = (event.clientY - from.y) / scale
          if (!from.moved && Math.hypot(dx, dy) * scale < 3) return
          from.moved = true
          setGhost({ box, dx, dy, factor: 1, turn: 0 })
          useStore.getState().setNudge({ id: region.id, dx, dy })
        }}
        onPointerUp={(event) => {
          const from = start.current
          start.current = null
          if (event.currentTarget.hasPointerCapture(event.pointerId)) event.currentTarget.releasePointerCapture(event.pointerId)
          if (!from) return
          if (!from.moved || !ghost) {
            useStore.getState().pickRegion(region.id)
            return
          }
          useStore.getState().moveRegion(region.id, ghost.dx, ghost.dy)
        }}
        onPointerCancel={() => {
          start.current = null
          setGhost(null)
          useStore.getState().setNudge(null)
        }}
      >
        {handles && (
          <>
            <div
              title="Drag to resize"
              onPointerDown={beginReshape('size')}
              onPointerMove={reshape}
              onPointerUp={endReshape}
              onPointerCancel={endReshape}
              className={`absolute ${CORNERS[spots.corner]} h-3 w-3 touch-none rounded-sm border border-cl-bg ${tone.fill}`}
            />
            <div className={`pointer-events-none absolute ${KNOBS.area.stem[knob]} ${tone.fill}`} />
            <div
              title="Drag to turn"
              aria-label="Drag to turn"
              onPointerDown={beginReshape('turn')}
              onPointerMove={reshape}
              onPointerUp={endReshape}
              onPointerCancel={endReshape}
              className={`absolute ${KNOBS.area.knob[knob]} z-10 flex h-5 w-5 cursor-grab touch-none items-center justify-center rounded-full border border-cl-bg ${tone.fill} text-cl-on-accent`}
            >
              <TurnIcon />
            </div>
          </>
        )}
      </div>
    </>
  )
}

/** The text of the picked area, typed right where the area is. */
function AreaField({ region, slot, scale }: { region: Region; slot: Slot; scale: number }) {
  const { changeRegion, removeRegion, pickRegion, render } = useStore.getState()
  const box = boxOf(region.shapes)
  if (!box) return null
  const wide = 232
  const tall = region.kind === 'keepout' ? 40 : 96
  const left = Math.max(0, Math.min(box[0] * scale, slot.width * scale - wide))
  // Under the area, clear of its corner handle; above it when there is no room under, and
  // then above the turn knob too, which stands on a stem over the area.
  const under = box[3] * scale + 14
  const top = under + tall <= slot.height * scale ? under : Math.max(0, box[1] * scale - tall - 60)
  const done = () => {
    void render()
    pickRegion(null)
  }
  return (
    <div
      className="absolute z-10 flex flex-col gap-1 rounded border border-cl-accent bg-cl-surface p-1.5 shadow-lg"
      style={{ left, top, width: wide }}
      onPointerDown={(event) => event.stopPropagation()}
    >
      {region.kind !== 'keepout' && (
        <textarea
          autoFocus
          value={region.text}
          rows={2}
          spellCheck={false}
          placeholder={region.kind === 'sfx' ? 'One effect: BOOM, THUD x3' : 'Text for this area'}
          onChange={(event) => changeRegion(region.id, { text: event.target.value }, false)}
          onBlur={() => void render()}
          onKeyDown={(event) => {
            event.stopPropagation()
            if (event.key === 'Enter' && (event.ctrlKey || event.metaKey)) done()
            if (event.key === 'Escape') done()
          }}
          className="w-full resize-none rounded border border-cl-border bg-cl-raised px-2 py-1 text-sm text-cl-text placeholder:text-cl-muted"
        />
      )}
      <div className="flex items-center justify-between gap-2 text-[11px] text-cl-muted">
        <span>{region.kind === 'keepout' ? 'Kept clear' : 'Ctrl+Enter when done'}</span>
        <span className="flex items-center gap-2">
          <button type="button" className="hover:text-cl-danger" onClick={() => removeRegion(region.id)}>
            Delete
          </button>
          <button type="button" className="rounded bg-cl-accent/20 px-2 py-0.5 text-cl-accent-text hover:bg-cl-accent/30" onClick={done}>
            Done
          </button>
        </span>
      </div>
    </div>
  )
}

function Picture({ slot }: { slot: Slot }) {
  const showOriginal = useStore((state) => state.showOriginal)
  const showFrames = useStore((state) => state.showFrames)
  const tool = useStore((state) => state.tool)
  const pickedId = useStore((state) => state.region)
  const [drawing, setDrawing] = useState<Shape | null>(null)
  const picked = slot.regions.find((region) => region.id === pickedId)
  const { ref, size, room } = useFit(slot.width, slot.height)
  const which = showOriginal || slot.empty ? 'original' : 'result'
  const scale = size.width / slot.width
  // What can be seen of the canvas around the picture, and the frames standing on it: the
  // handles of a picked frame keep inside the one and off the others.
  const sideways = (room.width - size.width) / 2
  const upright = (room.height - size.height) / 2
  const view: View = { left: -sideways, top: -upright, right: size.width + sideways, bottom: size.height + upright }
  const onScreen = (box: Box): Box => [box[0] * scale, box[1] * scale, box[2] * scale, box[3] * scale]
  const handled = slot.items.filter((item) => item.id && item.kind !== 'region' && item.kind !== 'path' && item.region === undefined)
  const frames: Frame[] = slot.bubbles.map((box) => ({ id: null, box: onScreen(box) }))
  for (const item of handled) {
    const place = placeOf(item)
    if (place) frames.push({ id: item.id as string, box: onScreen(reach(place)) })
  }
  const areaFrames: Frame[] = [...frames]
  for (const region of slot.regions) {
    const box = boxOf(region.shapes)
    if (box) areaFrames.push({ id: `area:${region.id}`, box: onScreen(box) })
  }
  return (
    <div
      ref={ref}
      className="flex min-h-0 flex-1 items-center justify-center"
      onPointerDown={() => {
        useStore.getState().select(null)
        if (tool === 'off') useStore.getState().pickRegion(null)
      }}
    >
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
                slot.regions.map((region) => (
                  <AreaGrip key={region.id} region={region} slot={slot} scale={scale} view={view} frames={areaFrames} />
                ))}
              {tool === 'off' &&
                handled.map((item) => <Handle key={item.id} item={item} slot={slot} scale={scale} view={view} frames={frames} />)}
            </>
          )}
          {tool !== 'off' && !showOriginal && <DrawLayer slot={slot} scale={scale} onDraw={setDrawing} />}
          {picked && showFrames && !showOriginal && !drawing && (
            <AreaField key={picked.id} region={picked} slot={slot} scale={scale} />
          )}
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
      <span className="text-xs">Then type one line per bubble in Bubbles.</span>
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

/** What to do first, when there is no image to letter yet: three steps and a way on without them. */
function FirstSteps({ title, steps }: { title: string; steps: [string, string, string] }) {
  return (
    <div className="flex min-h-0 flex-1 items-center justify-center">
      <div className="flex max-w-[320px] flex-col gap-3">
        <div className="text-sm font-medium text-cl-text">{title}</div>
        <ol className="flex flex-col gap-2">
          {steps.map((step, index) => (
            <li key={index} className="flex items-start gap-2 text-xs text-cl-muted">
              <Pill>{index + 1}</Pill>
              <span className="pt-px">{step}</span>
            </li>
          ))}
        </ol>
        <div>
          <Button onClick={() => useStore.getState().setSource('own')}>Letter your own image</Button>
        </div>
      </div>
    </div>
  )
}

export function Canvas() {
  const source = useStore((state) => state.source)
  const slot = useStore((state) => state.slots[state.source])
  const hostImage = useStore((state) => state.hostImage)
  const comfy = useStore((state) => state.comfy)
  const loadFile = useStore((state) => state.loadFile)

  let body
  if (slot) body = <Picture slot={slot} />
  else if (source === 'own') body = <DropZone />
  else if (comfy)
    body = (
      <FirstSteps
        title="The node has no image yet"
        steps={['Run the workflow once.', 'Open this editor again from the node.', 'Type one line per bubble in Bubbles; the node keeps everything.']}
      />
    )
  else if (hostImage)
    body = (
      <FirstSteps
        title="Nothing to letter yet"
        steps={[
          'Generate an image in txt2img or img2img.',
          'Type one line per bubble in Bubbles on the right.',
          'Press To gallery to put the lettered image back, or Save.',
        ]}
      />
    )
  else body = <div className="flex min-h-0 flex-1 items-center justify-center text-sm text-cl-muted">Waiting for the image…</div>

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
