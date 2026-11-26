import type { Options, Pin, Region, RenderResult, Settings } from './types'

const BASE = '/comic_lettering'

async function unwrap<T>(response: Response): Promise<T> {
  let body: unknown = null
  try {
    body = await response.json()
  } catch {
    // not JSON: fall through to the status text
  }
  if (!response.ok) {
    const message = body && typeof body === 'object' && 'error' in body ? String((body as { error: unknown }).error) : ''
    throw new Error(message || `${response.status} ${response.statusText}`)
  }
  return body as T
}

function post<T>(path: string, body: unknown): Promise<T> {
  return fetch(BASE + path, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  }).then((response) => unwrap<T>(response))
}

export interface NewSession {
  session: string
  width: number
  height: number
  origin?: string
}

export const api = {
  options: () => fetch(`${BASE}/options`).then((response) => unwrap<Options>(response)),

  /** Hand an image file to the server to letter. */
  upload: (file: Blob, name: string) =>
    fetch(`${BASE}/session?name=${encodeURIComponent(name)}`, { method: 'POST', body: file }).then((response) =>
      unwrap<NewSession>(response),
    ),

  /** The clean copy of an image of the last generation, by its place in the host gallery. */
  lastGeneration: (tab: string, index: number, count: number, known?: string, session?: string) =>
    post<NewSession | { same: true }>('/session/last', { tab, index, count, known, session }),

  render: (
    session: string,
    text: string,
    caption: string,
    sfx: string,
    numbers: boolean,
    settings: Settings,
    pins: Record<string, Pin>,
    regions: Region[],
  ) => post<RenderResult>('/render', { session, text, caption, sfx, numbers, settings, pins, regions }),

  saveSettings: (settings: Settings, auto: Options['auto']) => post<{ ok: boolean }>('/settings', { settings, auto }),

  save: (session: string) => post<{ path: string }>('/save', { session }),

  imageUrl: (session: string, which: 'original' | 'result', version: number) =>
    `${BASE}/image/${session}/${which}?v=${version}`,

  fontUrl: (name: string) => `${BASE}/font?name=${encodeURIComponent(name)}`,
}
