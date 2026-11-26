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

export const BUBBLE_SHAPES: BubbleShape[] = ['oval', 'box', 'cloud', 'burst', 'thought']
export const BUBBLE_TAILS: BubbleTail[] = ['none', 'down-left', 'down', 'down-right', 'left', 'right', 'up-left', 'up', 'up-right']
