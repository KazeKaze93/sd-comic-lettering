import type { BubbleShape, BubbleTail, BubbleTemplate, Shape } from './types'

export type Box = [number, number, number, number]

/** The box around what shapes paint, in image pixels: [x0, y0, x1, y1]; null if they paint nothing. */
export function boxOf(shapes: Shape[]): Box | null {
  let box: Box | null = null
  for (const shape of shapes) {
    if (shape.type === 'erase') continue
    const pad = shape.type === 'stroke' ? shape.width / 2 : 0
    for (const [x, y] of shape.points) {
      box = box
        ? [Math.min(box[0], x - pad), Math.min(box[1], y - pad), Math.max(box[2], x + pad), Math.max(box[3], y + pad)]
        : [x - pad, y - pad, x + pad, y + pad]
    }
  }
  return box
}

const TAIL_ANGLES: Record<Exclude<BubbleTail, 'none'>, number> = {
  right: 0,
  'down-right': 45,
  down: 90,
  'down-left': 135,
  left: 180,
  'up-left': 225,
  up: 270,
  'up-right': 315,
}

/** How far the outline of a shape stands from the middle, at an angle, as a share of the oval. */
function radius(shape: BubbleShape, angle: number, step: number) {
  if (shape === 'cloud' || shape === 'thought') return 0.9 + 0.1 * Math.abs(Math.sin(4.5 * angle))
  if (shape === 'burst') return step % 2 === 0 ? 1 : 0.74
  return 1
}

/** The outline of a bubble template in its box: the body, and its tail as shapes of their own
 * (the server joins everything an area is made of into one outline). */
export function bubbleShapes(template: BubbleTemplate): Shape[] {
  const [x0, y0, x1, y1] = template.box
  const cx = (x0 + x1) / 2
  const cy = (y0 + y1) / 2
  const rx = Math.max(4, (x1 - x0) / 2)
  const ry = Math.max(4, (y1 - y0) / 2)
  const point = (x: number, y: number): [number, number] => [Math.round(x * 10) / 10, Math.round(y * 10) / 10]
  let body: [number, number][]
  if (template.shape === 'box') {
    // A box with rounded corners.
    const r = 0.22 * Math.min(rx, ry)
    body = []
    const corners: [number, number, number][] = [
      [x1 - r, y0 + r, -90],
      [x1 - r, y1 - r, 0],
      [x0 + r, y1 - r, 90],
      [x0 + r, y0 + r, 180],
    ]
    for (const [px, py, from] of corners) {
      for (let step = 0; step <= 6; step += 1) {
        const angle = ((from + (90 * step) / 6) * Math.PI) / 180
        body.push(point(px + r * Math.cos(angle), py + r * Math.sin(angle)))
      }
    }
  } else {
    const steps = template.shape === 'burst' ? 28 : 72
    body = []
    for (let step = 0; step < steps; step += 1) {
      const angle = (2 * Math.PI * step) / steps
      const far = radius(template.shape, angle, step)
      body.push(point(cx + rx * far * Math.cos(angle), cy + ry * far * Math.sin(angle)))
    }
  }
  const shapes: Shape[] = [{ type: 'polygon', points: body }]
  if (template.tail !== 'none') {
    const angle = (TAIL_ANGLES[template.tail] * Math.PI) / 180
    const at = (far: number, turn: number) => point(cx + rx * far * Math.cos(angle + turn), cy + ry * far * Math.sin(angle + turn))
    if (template.shape === 'thought') {
      // A thought trails off in small bubbles instead of pointing.
      for (const [far, size] of [
        [1.22, 0.16],
        [1.5, 0.1],
      ]) {
        const [px, py] = at(far, 0)
        const r = size * Math.min(rx, ry)
        const dots: [number, number][] = []
        for (let step = 0; step < 16; step += 1) {
          dots.push(point(px + r * Math.cos((Math.PI * step) / 8), py + r * Math.sin((Math.PI * step) / 8)))
        }
        shapes.push({ type: 'polygon', points: dots })
      }
    } else {
      shapes.push({ type: 'polygon', points: [at(0.8, -0.24), at(1.5, 0.08), at(0.8, 0.24)] })
    }
  }
  const angle = template.angle ?? 0
  return angle ? shapes.map((shape) => ({ ...shape, points: turned(shape.points, cx, cy, angle, 1) })) : shapes
}

/** Points turned clockwise by an angle in degrees about a middle, and moved away from it by a factor. */
export function turned(points: [number, number][], cx: number, cy: number, angle: number, factor: number): [number, number][] {
  const cos = Math.cos((angle * Math.PI) / 180) * factor
  const sin = Math.sin((angle * Math.PI) / 180) * factor
  return points.map(([x, y]) => [
    Math.round((cx + (x - cx) * cos - (y - cy) * sin) * 10) / 10,
    Math.round((cy + (x - cx) * sin + (y - cy) * cos) * 10) / 10,
  ])
}

export type KnobSide = 'top' | 'bottom' | 'right' | 'left'
export type CornerSide = 'br' | 'bl' | 'tr' | 'tl'

/** Where a frame's turn knob and resize corner go, so that both can always be reached.
 *
 * Why: a handle at a fixed place fails in two ways. A frame near an edge of the canvas pushes
 * its knob out of sight (over the top bar), and a frame beside another one puts its corner on
 * the neighbour's frame, where a press takes hold of the wrong thing. Turning and resizing are
 * worked out from the frame's middle, so a handle does the same job from any side: it only
 * needs a side where it is seen and stands on nothing else.
 *
 * Everything is in screen pixels relative to the picture. `angle` is the frame's rotation as
 * CSS draws it (degrees, clockwise). `knobReach` is how far the knob's middle stands from the
 * frame's edge; 0 or less means the frame has no knob. `viewport` is the part of the canvas
 * that can be seen; `obstacles` are the boxes of the other frames and of the bubbles found. */
export function placeHandles(args: {
  center: [number, number]
  size: [number, number]
  angle: number
  knobReach: number
  viewport: { left: number; top: number; right: number; bottom: number }
  obstacles: Array<[number, number, number, number]>
  margin: number
}): { knob: KnobSide | null; corner: CornerSide } {
  const { center, size, angle, knobReach, viewport, obstacles, margin } = args
  const halfWide = size[0] / 2
  const halfTall = size[1] / 2
  // A place given in the frame's own directions, as it lands on the picture once the frame is turned.
  const at = (x: number, y: number) => turned([[center[0] + x, center[1] + y]], center[0], center[1], angle, 1)[0]
  const inside = (box: Box) => box[0] >= viewport.left && box[1] >= viewport.top && box[2] <= viewport.right && box[3] <= viewport.bottom
  const clear = (box: Box) =>
    !obstacles.some((other) => box[0] < other[2] + margin && other[0] - margin < box[2] && box[1] < other[3] + margin && other[1] - margin < box[3])
  const choose = <T extends string>(candidates: [T, Box][], fallback: T): T =>
    (candidates.find(([, box]) => inside(box) && clear(box)) ?? candidates.find(([, box]) => inside(box)))?.[0] ?? fallback

  let knob: KnobSide | null = null
  if (knobReach > 0) {
    // The knob with its stem: from the frame's edge out to the knob, which is 20 pixels across.
    const reach = (edge: [number, number], middle: [number, number]): Box => [
      Math.min(edge[0], middle[0]) - 10,
      Math.min(edge[1], middle[1]) - 10,
      Math.max(edge[0], middle[0]) + 10,
      Math.max(edge[1], middle[1]) + 10,
    ]
    knob = choose<KnobSide>(
      [
        ['top', reach(at(0, -halfTall), at(0, -halfTall - knobReach))],
        ['bottom', reach(at(0, halfTall), at(0, halfTall + knobReach))],
        ['right', reach(at(halfWide, 0), at(halfWide + knobReach, 0))],
        ['left', reach(at(-halfWide, 0), at(-halfWide - knobReach, 0))],
      ],
      'top',
    )
  }
  // The corner is 12 pixels across.
  const around = ([x, y]: [number, number]): Box => [x - 6, y - 6, x + 6, y + 6]
  const corner = choose<CornerSide>(
    [
      ['br', around(at(halfWide, halfTall))],
      ['bl', around(at(-halfWide, halfTall))],
      ['tr', around(at(halfWide, -halfTall))],
      ['tl', around(at(-halfWide, -halfTall))],
    ],
    'br',
  )
  return { knob, corner }
}

export const BUBBLE_SHAPES: BubbleShape[] = ['oval', 'box', 'cloud', 'burst', 'thought']
export const BUBBLE_TAILS: BubbleTail[] = ['none', 'down-left', 'down', 'down-right', 'left', 'right', 'up-left', 'up', 'up-right']
