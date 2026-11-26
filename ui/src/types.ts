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
  kind: 'bubble' | 'caption' | 'balloon' | 'sfx'
  text: string
  size: number
  bubble?: number
  box?: [number, number, number, number]
  x?: number
  y?: number
  nominal?: [number, number]
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
}

/** What the host page tells the editor about the image in its gallery. */
export interface HostImage {
  tab: string
  url: string | null
  index: number
  count: number
}
