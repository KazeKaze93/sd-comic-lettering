import type { HostImage, Pin, Region, Settings } from './types'

/** What a ComfyUI node holds: its texts, its look, and what was placed and drawn by hand.
 * In ComfyUI the node is where everything is kept; the page reads it on opening and writes back. */
export interface NodeState {
  texts: { text: string; caption: string; sfx: string }
  settings: Settings
  layout: { pins: Record<string, Pin>; regions: Region[] }
}

/** Messages from the host page to this page: javascript/comic_lettering.js in the A1111 family,
 * comfy_web/comic_lettering.js in ComfyUI, which also sends the node's state. */
export type HostMessage = { type: 'SDCL_INIT'; image: HostImage; theme: 'dark' | 'light'; node?: NodeState }

/** Messages from this page to the host page. */
export type FrameMessage =
  | { type: 'SDCL_READY' }
  | { type: 'SDCL_CLOSE' }
  | { type: 'SDCL_TO_GALLERY'; session: string }
  | { type: 'SDCL_STATE'; state: NodeState }

// The page is served by the host itself: both sides have the same origin.
export function tellHost(message: FrameMessage) {
  if (window.parent !== window) window.parent.postMessage(message, window.location.origin)
}

export function onHostMessage(handler: (message: HostMessage) => void) {
  const listener = (event: MessageEvent) => {
    if (event.origin !== window.location.origin || event.source !== window.parent) return
    const data = event.data as { type?: unknown } | null
    if (data && data.type === 'SDCL_INIT') handler(event.data as HostMessage)
  }
  window.addEventListener('message', listener)
  return () => window.removeEventListener('message', listener)
}
