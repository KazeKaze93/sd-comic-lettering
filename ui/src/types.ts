/** Values of the look, as the server keeps them in user_settings.json. */
export type Settings = Record<string, string | number | boolean>

export interface Options {
  fonts: string[]
  sameFont: string
  palettes: string[]
  moods: string[]
  extras: string[]
  shapes: string[]
  themes: string[]
  tails: string[]
  placements: string[]
  symbols: string[]
  defaults: Settings
  settings: Settings
  auto: { enabled: boolean; text: string; caption: string; sfx: string }
}

/** One thing the server drew, with its place in image pixels. */
export interface SceneItem {
  kind: 'bubble' | 'caption' | 'balloon' | 'sfx' | 'region' | 'path'
  text: string
  size: number
  bubble?: number
  box?: [number, number, number, number]
  x?: number
  y?: number
  nominal?: [number, number]
  /** Present on what can be moved by hand: "caption", "sfx:0", ... */
  id?: string
  cx?: number
  cy?: number
  /** Tilt in degrees, counter-clockwise. */
  rotation?: number
  reach?: number
  tall?: boolean
  /** On a sound effect that belongs to an area: the area's id. Its place is the area's. */
  region?: string | number
}

/** One stroke of the hand: an outline that is closed and filled, or a brush stroke. Points are image pixels. */
export type Shape =
  | { type: 'polygon'; points: [number, number][] }
  | { type: 'stroke'; points: [number, number][]; width: number }
  /** Rubs out what the shapes before it painted. */
  | { type: 'erase'; points: [number, number][]; width: number }

export type RegionKind = 'text' | 'sfx' | 'keepout'

/** An area drawn on the image: text or an effect is fitted into it, or everything keeps out of it. */
export interface Region {
  id: string
  kind: RegionKind
  shapes: Shape[]
  text: string
  fill: 'none' | 'light' | 'dark'
  /** Tilt in degrees, counter-clockwise; an effect is tilted at random while this is not set. */
  rotation?: number
  /** How large the text or effect is against what the area would give it; 1 when not set. */
  scale?: number
  /** The text runs along the brush stroke and bends with it. */
  follow?: boolean
  /** Along the stroke the other way round. */
  flip?: boolean
}

export type Tool = 'off' | 'lasso' | 'brush' | 'eraser'

/** What was set by hand for one item; the server decides whatever is left out. */
export interface Pin {
  cx?: number
  cy?: number
  size?: number
  rotation?: number
  reach?: number
  tall?: boolean
}

export interface RenderResult {
  version: number
  status: string
  warning: boolean
  empty: boolean
  items: SceneItem[]
  bubbles: [number, number, number, number][]
}

export type Source = 'generation' | 'own'
export type LookOf = 'bubble' | 'caption' | 'sfx'

/** An image being lettered and what the server last made of it. */
export interface Slot {
  session: string
  width: number
  height: number
  version: number
  empty: boolean
  items: SceneItem[]
  bubbles: [number, number, number, number][]
  /** The inputs of the last finished render, to skip a render that would change nothing. */
  applied: string
  /** What the server said about that render. */
  status: string
  warning: boolean
  /** Places, sizes and tilts set by hand, by item id. */
  pins: Record<string, Pin>
  /** Areas drawn by hand. */
  regions: Region[]
  /** Which image of which generation this is, when the host knows; an image opened again keeps its slot. */
  origin?: string
}

/** What the host page tells the editor about the image in its gallery. */
export interface HostImage {
  tab: string
  url: string | null
  index: number
  count: number
}
