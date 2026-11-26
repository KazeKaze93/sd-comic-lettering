import type { Shape } from './types'

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
