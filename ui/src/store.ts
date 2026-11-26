import { create } from 'zustand'
import { api, type NewSession } from './api'
import { boxOf, bubbleShapes } from './geometry'
import type { BubbleTemplate, HostImage, LookOf, Options, Pin, Region, Settings, Shape, Slot, Source, Tool } from './types'

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
  /** The template the bubble tool puts down next, and how its bubble is painted. */
  stamp: { shape: BubbleTemplate['shape']; tail: BubbleTemplate['tail']; fill: 'light' | 'dark' }
  /** An area being dragged, and how far, in image pixels: its tint follows before anything is redrawn. */
  nudge: { id: string; dx: number; dy: number } | null
  /** The area under the pointer, with the arrow: its tint shows while the pointer is on it. */
  hover: string | null
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
  setNudge: (nudge: State['nudge']) => void
  setHover: (id: string | null) => void
  setStamp: (change: Partial<State['stamp']>) => void
  /** Put a bubble from the template into a box on the image and open the field for its text. */
  addBubble: (box: BubbleTemplate['box']) => void
  /** Give a template bubble another shape or tail. */
  reshape: (id: string, change: Partial<Pick<BubbleTemplate, 'shape' | 'tail'>>) => void
  /** Move an area, with everything painted in it, and draw again. */
  moveRegion: (id: string, dx: number, dy: number) => void
  /** Add what was just drawn to the picked area, or start a new area with it. */
  addShape: (shape: Shape) => void
  /** Change an area; `render` false while its text is being typed. */
  changeRegion: (id: string, change: Partial<Region>, render?: boolean) => void
  removeRegion: (id: string) => void
  /** Take back the last thing drawn in an area; an area left with nothing painted goes. */
  undoShape: (id: string) => void
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

/** Is this one sweep of the brush along a line, not a scribble that fills a patch? A sweep is
 * not much longer than the box around it is across; a scribble goes back and forth inside it. */
function isLine(shape: Shape) {
  if (shape.type !== 'stroke' || shape.points.length < 2) return false
  let length = 0
  for (let index = 1; index < shape.points.length; index += 1) {
    length += Math.hypot(shape.points[index][0] - shape.points[index - 1][0], shape.points[index][1] - shape.points[index - 1][1])
  }
  const box = boxOf([{ ...shape, width: 0 }])
  if (!box) return false
  return length <= 1.8 * Math.hypot(box[2] - box[0], box[3] - box[1])
}

/** Does a new shape touch what a region already paints? Judged by their boxes. */
function touches(region: Region, shape: Shape) {
  const a = boxOf(region.shapes)
  const b = boxOf([shape])
  return !!a && !!b && a[0] <= b[2] && b[0] <= a[2] && a[1] <= b[3] && b[1] <= a[3]
}

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
    nudge: null,
    hover: null,
    stamp: { shape: 'oval', tail: 'down-left', fill: 'light' },
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
    setNudge: (nudge) => set({ nudge }),
    setHover: (id) => set({ hover: id }),
    setStamp: (change) => set((state) => ({ stamp: { ...state.stamp, ...change } })),

    addBubble: (box) => {
      const state = get()
      const slot = state.slots[state.source]
      if (!slot) return
      regionCount += 1
      const id = `a${Date.now().toString(36)}${regionCount}`
      const template: BubbleTemplate = { shape: state.stamp.shape, tail: state.stamp.tail, box }
      const region: Region = { id, kind: 'text', shapes: bubbleShapes(template), text: '', fill: state.stamp.fill, template }
      set({ region: id, slots: { ...state.slots, [state.source]: { ...slot, regions: [...slot.regions, region] } } })
      void get().render()
    },

    reshape: (id, change) => {
      const slot = get().slots[get().source]
      const region = slot?.regions.find((candidate) => candidate.id === id)
      if (!region || !region.template) return
      const template = { ...region.template, ...change }
      get().changeRegion(id, { template, shapes: bubbleShapes(template) })
    },

    moveRegion: (id, dx, dy) => {
      const slot = get().slots[get().source]
      const region = slot?.regions.find((candidate) => candidate.id === id)
      if (!region) return
      const moved = (points: [number, number][]) =>
        points.map(([x, y]) => [Math.round((x + dx) * 10) / 10, Math.round((y + dy) * 10) / 10] as [number, number])
      set({ nudge: null })
      const box = region.template?.box
      get().changeRegion(id, {
        shapes: region.shapes.map((shape) => ({ ...shape, points: moved(shape.points) })),
        template: region.template && box ? { ...region.template, box: [box[0] + dx, box[1] + dy, box[2] + dx, box[3] + dy] } : undefined,
      })
    },

    addShape: (shape) => {
      const state = get()
      const slot = state.slots[state.source]
      if (!slot) return
      const picked = slot.regions.find((region) => region.id === state.region)
      let regions: Region[]
      let id = state.region
      if (shape.type === 'erase') {
        // The eraser rubs out whatever it passes over, in every area, as in a paint program.
        if (!slot.regions.length) return
        regions = slot.regions.map((region) => (touches(region, { ...shape, type: 'stroke' }) ? { ...region, shapes: [...region.shapes, shape] } : region))
      } else if (picked && touches(picked, shape)) {
        // More paint on the picked area. An area painted in several goes is a shape to
        // fill, not a line to write along.
        regions = slot.regions.map((region) =>
          region === picked ? { ...region, shapes: [...region.shapes, shape], follow: false } : region,
        )
      } else {
        // Paint away from the picked area starts a new one: one area per bubble, each with its own text.
        regionCount += 1
        id = `a${Date.now().toString(36)}${regionCount}`
        // What is painted with the brush is a line to write along; an outline is a shape to fill.
        regions = [...slot.regions, { id, kind: 'text', shapes: [shape], text: '', fill: 'none', follow: isLine(shape) }]
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

    undoShape: (id) => {
      const state = get()
      const slot = state.slots[state.source]
      const region = slot?.regions.find((candidate) => candidate.id === id)
      if (!slot || !region) return
      const shapes = region.shapes.slice(0, -1)
      if (!shapes.some((shape) => shape.type !== 'erase')) {
        get().removeRegion(id)
        return
      }
      get().changeRegion(id, { shapes })
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
        // Saved the way the host saves a generation of the tab the editor was opened from.
        const saved = await api.save(slot.session, get().hostImage?.tab ?? 'txt2img')
        set({ status: `Saved to ${saved.path}`, warning: false, error: null })
      } catch (error) {
        fail(error)
      }
    },
  }
})
