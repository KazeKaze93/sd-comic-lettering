import type { HostImage } from './types'

/** Messages from the host page (javascript/comic_lettering.js) to this page. */
export type HostMessage = { type: 'SDCL_INIT'; image: HostImage; theme: 'dark' | 'light' }

/** Messages from this page to the host page. */
export type FrameMessage =
  | { type: 'SDCL_READY' }
  | { type: 'SDCL_CLOSE' }
  | { type: 'SDCL_TO_GALLERY'; session: string }

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
