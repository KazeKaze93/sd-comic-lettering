import { create } from 'zustand'
import { api, type NewSession } from './api'
import type { HostImage, LookOf, Options, Pin, Region, Settings, Shape, Slot, Source, Tool } from './types'

const FONT_KEYS = ['font', 'caption_font', 'sfx_font']

interface State {
  options: Options | null
  /** Whether the page runs inside the host's overlay (a host gallery exists). */
  embedded: boolean
  source: Source
  slots: Record<Source, Slot | null>
  hostImage: HostImage | null
  text: string
  caption: string
  sfx: string
  numbers: boolean
  settings: Settings
  auto: boolean
  lookOf: LookOf
  showOriginal: boolean
  showFrames: boolean
  /** The id of the item picked on the image, if any. */
  selected: string | null
  /** The drawing tool, its brush width as a share of the image's shorter side, and the area drawn into. */
  tool: Tool
  brush: number
  region: string | null
  busy: boolean
  status: string
  warning: boolean
  error: string | null

  start: (embedded: boolean) => Promise<void>
  setSource: (source: Source) => void
  hostOpened: (image: HostImage) => Promise<void>
  loadFile: (file: Blob, name: string) => Promise<void>
  setField: (field: 'text' | 'caption' | 'sfx', value: string) => void
  setNumbers: (value: boolean) => void
  setSetting: (key: string, value: string | number | boolean, render?: boolean) => void
  setAuto: (value: boolean) => void
  setLookOf: (value: LookOf) => void
  setShowOriginal: (value: boolean) => void
  setShowFrames: (value: boolean) => void
  moveEffects: () => void
  select: (id: string | null) => void
  /** Set an item's place, size or tilt by hand and draw again. */
  setPin: (id: string, pin: Pin) => void
  /** Hand one item, or all of them, back to the automatic placement. */
  clearPins: (id?: string) => void
  setTool: (tool: Tool) => void
  setBrush: (brush: number) => void
  pickRegion: (id: string | null) => void
  /** Add what was just drawn to the picked area, or start a new area with it. */
  addShape: (shape: Shape) => void
  /** Change an area; `render` false while its text is being typed. */
  changeRegion: (id: string, change: Partial<Region>, render?: boolean) => void
  removeRegion: (id: string) => void
  resetLook: (keepFonts: boolean) => void
  render: () => Promise<void>
  save: () => Promise<void>
}

let saveTimer: ReturnType<typeof setTimeout> | undefined
let rendering = false
let renderAgain = false

function slotOf(created: NewSession): Slot {
  return {
    session: created.session,
    width: created.width,
    height: created.height,
    version: 0,
    empty: true,
    items: [],
    bubbles: [],
    applied: '',
    status: '',
    warning: false,
    pins: {},
    regions: [],
  }
}

let regionCount = 0

export const useStore = create<State>((set, get) => {
  /** Remember the look and what is lettered onto new images, a moment after the last change. */
  const persist = () => {
    clearTimeout(saveTimer)
    saveTimer = setTimeout(() => {
      const { settings, auto, text, caption, sfx } = get()
      api.saveSettings(settings, { enabled: auto, text, caption, sfx }).catch(() => undefined)
    }, 400)
  }

  const fail = (error: unknown) => set({ busy: false, error: error instanceof Error ? error.message : String(error) })

  return {
    options: null,
    embedded: false,
    source: 'own',
    slots: { generation: null, own: null },
    hostImage: null,
    text: '',
    caption: '',
    sfx: '',
    numbers: false,
    settings: {},
    auto: false,
    lookOf: 'bubble',
    showOriginal: false,
    showFrames: true,
    selected: null,
    tool: 'off',
    brush: 0.12,
    region: null,
    busy: false,
    status: '',
    warning: false,
    error: null,

    start: async (embedded) => {
      try {
        const options = await api.options()
        set({
          options,
          embedded,
          source: embedded ? 'generation' : 'own',
          settings: options.settings,
          auto: options.auto.enabled,
          // The texts come back only while they are being lettered onto new images:
          // then the fields must show what the host is using.
          text: options.auto.enabled ? options.auto.text : '',
          caption: options.auto.enabled ? options.auto.caption : '',
          sfx: options.auto.enabled ? options.auto.sfx : '',
        })
      } catch (error) {
        fail(error)
      }
    },

    setSource: (source) => {
      const slot = get().slots[source]
      set({ source, error: null, status: slot?.status ?? '', warning: slot?.warning ?? false })
      void get().render()
    },

    hostOpened: async (image) => {
      set({ hostImage: image, error: null })
      if (!image.url) {
        set((state) => ({ slots: { ...state.slots, generation: null } }))
        return
      }
      set({ busy: true })
      try {
        let created: NewSession
        const held = get().slots.generation
        try {
          // The host keeps the images of the last generation as they were before any lettering.
          const answer = await api.lastGeneration(image.tab, image.index, image.count, held?.origin, held?.session)
          if ('same' in answer) {
            // The image that is already open: what was placed and drawn on it stays.
            set({ busy: false })
            await get().render()
            return
          }
          created = answer
        } catch {
          // Not from the last generation (or the host was restarted): take what the gallery shows.
          const blob = await fetch(image.url).then((response) => {
            if (!response.ok) throw new Error('Could not read the image from the gallery.')
            return response.blob()
          })
          created = await api.upload(blob, 'generation')
        }
        set((state) => ({
          busy: false,
          region: null,
          selected: null,
          slots: { ...state.slots, generation: { ...slotOf(created), origin: created.origin } },
        }))
        await get().render()
      } catch (error) {
        fail(error)
      }
    },

    loadFile: async (file, name) => {
      set({ busy: true, error: null })
      try {
        const created = await api.upload(file, name)
        set((state) => ({ busy: false, slots: { ...state.slots, own: slotOf(created) } }))
        await get().render()
      } catch (error) {
        fail(error)
      }
    },

    setField: (field, value) => {
      set({ [field]: value } as Pick<State, 'text' | 'caption' | 'sfx'>)
      persist()
    },

    setNumbers: (value) => {
      set({ numbers: value })
      void get().render()
    },

    setSetting: (key, value, render = true) => {
      set((state) => ({ settings: { ...state.settings, [key]: value } }))
      persist()
      if (render) void get().render()
    },

    setAuto: (value) => {
      set({ auto: value })
      persist()
    },

    setLookOf: (value) => set({ lookOf: value }),
    setShowOriginal: (value) => set({ showOriginal: value }),
    setShowFrames: (value) => set({ showFrames: value }),

    moveEffects: () => {
      const current = Number(get().settings.sfx_seed) || 0
      get().setSetting('sfx_seed', current + 1)
    },

    select: (id) => set({ selected: id }),

    setPin: (id, pin) => {
      set((state) => {
        const slot = state.slots[state.source]
        if (!slot) return {}
        return { slots: { ...state.slots, [state.source]: { ...slot, pins: { ...slot.pins, [id]: pin } } } }
      })
      void get().render()
    },

    clearPins: (id) => {
      set((state) => {
        const slot = state.slots[state.source]
        if (!slot) return {}
        const pins = { ...slot.pins }
        if (id) delete pins[id]
        return { slots: { ...state.slots, [state.source]: { ...slot, pins: id ? pins : {} } } }
      })
      void get().render()
    },

    setTool: (tool) => set({ tool, selected: null }),
    setBrush: (brush) => set({ brush }),
    pickRegion: (id) => set({ region: id }),

    addShape: (shape) => {
      const state = get()
      const slot = state.slots[state.source]
      if (!slot) return
      const picked = slot.regions.find((region) => region.id === state.region)
      let regions: Region[]
      let id = state.region
      if (picked) {
        regions = slot.regions.map((region) => (region === picked ? { ...region, shapes: [...region.shapes, shape] } : region))
      } else {
        regionCount += 1
        id = `a${Date.now().toString(36)}${regionCount}`
        regions = [...slot.regions, { id, kind: 'text', shapes: [shape], text: '', fill: 'none' }]
      }
      set({ region: id, slots: { ...state.slots, [state.source]: { ...slot, regions } } })
      void get().render()
    },

    changeRegion: (id, change, render = true) => {
      set((state) => {
        const slot = state.slots[state.source]
        if (!slot) return {}
        const regions = slot.regions.map((region) => (region.id === id ? { ...region, ...change } : region))
        return { slots: { ...state.slots, [state.source]: { ...slot, regions } } }
      })
      if (render) void get().render()
    },

    removeRegion: (id) => {
      set((state) => {
        const slot = state.slots[state.source]
        if (!slot) return {}
        return {
          region: state.region === id ? null : state.region,
          slots: { ...state.slots, [state.source]: { ...slot, regions: slot.regions.filter((region) => region.id !== id) } },
        }
      })
      void get().render()
    },

    resetLook: (keepFonts) => {
      const { options, settings } = get()
      if (!options) return
      const next: Settings = { ...options.defaults }
      if (keepFonts) for (const key of FONT_KEYS) next[key] = settings[key]
      set({ settings: next })
      persist()
      void get().render()
    },

    render: async () => {
      const state = get()
      const slot = state.slots[state.source]
      if (!slot) return
      if (rendering) {
        renderAgain = true
        return
      }
      const { text, caption, sfx, numbers, settings, source } = state
      const signature = JSON.stringify([text, caption, sfx, numbers, settings, slot.pins, slot.regions])
      if (signature === slot.applied) return
      rendering = true
      set({ busy: true, error: null })
      try {
        const result = await api.render(slot.session, text, caption, sfx, numbers, settings, slot.pins, slot.regions)
        set((now) => {
          const held = now.slots[source]
          if (!held || held.session !== slot.session) return { busy: false }
          return {
            busy: false,
            status: result.status,
            warning: result.warning,
            slots: {
              ...now.slots,
              [source]: {
                ...held,
                version: result.version,
                empty: result.empty,
                items: result.items,
                bubbles: result.bubbles,
                applied: signature,
                status: result.status,
                warning: result.warning,
              },
            },
          }
        })
      } catch (error) {
        fail(error)
      } finally {
        rendering = false
        if (renderAgain) {
          renderAgain = false
          void get().render()
        }
      }
    },

    save: async () => {
      const slot = get().slots[get().source]
      if (!slot) return
      try {
        const saved = await api.save(slot.session)
        set({ status: `Saved to ${saved.path}`, warning: false, error: null })
      } catch (error) {
        fail(error)
      }
    },
  }
})
