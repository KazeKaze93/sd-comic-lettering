import { create } from 'zustand'
import { api, type NewSession } from './api'
import { tellHost, type NodeState } from './bridge'
import { boxOf, bubbleShapes, turned } from './geometry'
import type { BubbleTemplate, HostImage, LookOf, Options, Pin, Region, Settings, Shape, Slot, Source, Tool } from './types'

const FONT_KEYS = ['font', 'caption_font', 'sfx_font']

interface State {
  options: Options | null
  /** Whether the page runs inside the host's overlay (a host gallery exists). */
  embedded: boolean
  /** In ComfyUI: the node keeps the texts, the look and the layout, and the page writes them back to it. */
  comfy: boolean
  source: Source
  slots: Record<Source, Slot | null>
  hostImage: HostImage | null
  text: string
  caption: string
  sfx: string
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
  nudge: { id: string; dx: number; dy: number; factor?: number; turn?: number } | null
  /** The area under the pointer, with the arrow: its tint shows while the pointer is on it. */
  hover: string | null
  busy: boolean
  status: string
  warning: boolean
  error: string | null
  /** Whether there is a step to take back, and one to do again. */
  canUndo: boolean
  canRedo: boolean

  start:(embedded: boolean) => Promise<void>
  setSource: (source: Source) => void
  hostOpened: (image: HostImage, node?: NodeState) => Promise<void>
  loadFile: (file: Blob, name: string) => Promise<void>
  setField: (field: 'text' | 'caption' | 'sfx', value: string) => void
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
  /** Make an area larger or smaller about its middle, or turn it (degrees, clockwise); its text turns with it. */
  transformRegion: (id: string, factor: number, turn: number) => void
  /** Add what was just drawn to the picked area, or start a new area with it. */
  addShape: (shape: Shape) => void
  /** Change an area; `render` false while its text is being typed. */
  changeRegion: (id: string, change: Partial<Region>, render?: boolean) => void
  removeRegion: (id: string) => void
  /** Take back the last thing drawn in an area; an area left with nothing painted goes. */
  undoShape: (id: string) => void
  resetLook: (keepFonts: boolean) => void
  /** `record: false` for a render nobody's edit caused (another image shown): it is no step to take back. */
  render: (options?: { record?: boolean }) => Promise<void>
  save: () => Promise<void>
  /** Take back the last change of the texts, the look, a place or an area; and do it again. */
  undo: () => void
  redo: () => void
}

/** What undo goes back to. The texts and the look are the editor's; places and areas are an image's. */
interface HistoryEntry {
  text: string
  caption: string
  sfx: string
  settings: Settings
  source: Source
  session: string
  pins: Slot['pins']
  regions: Region[]
}

const HISTORY_LIMIT = 50

let saveTimer: ReturnType<typeof setTimeout> | undefined
let rendering = false
let renderAgain = false
// One timeline for both images: the texts and the look are shared, so two would undo each other's changes.
let past: HistoryEntry[] = []
let future: HistoryEntry[] = []
let replaying = false // a render caused by undo/redo: never recorded
let suppressRecord = false // a render caused by setSource / hostOpened / loadFile: never recorded

/** A value as text with its keys in order, to tell whether two hold the same. */
function stable(value: unknown): string {
  if (Array.isArray(value)) return `[${value.map(stable).join(',')}]`
  if (value && typeof value === 'object') {
    const entries = Object.entries(value as Record<string, unknown>).filter(([, item]) => item !== undefined)
    return `{${entries
      .sort(([a], [b]) => (a < b ? -1 : a > b ? 1 : 0))
      .map(([key, item]) => `${JSON.stringify(key)}:${stable(item)}`)
      .join(',')}}`
  }
  return JSON.stringify(value) ?? 'null'
}

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
/** In ComfyUI: the layout the node came with, kept for when there is no image to put it on yet. */
let nodeLayout: NodeState['layout'] = { pins: {}, regions: [] }

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
      const { settings, auto, text, caption, sfx, comfy, slots } = get()
      if (comfy) {
        // The node is the memory: hand it everything, so the next run of the workflow gives this picture.
        const slot = slots.generation
        tellHost({
          type: 'SDCL_STATE',
          state: { texts: { text, caption, sfx }, settings, layout: slot ? { pins: slot.pins, regions: slot.regions } : nodeLayout },
        })
        return
      }
      api.saveSettings(settings, { enabled: auto, text, caption, sfx }).catch(() => undefined)
    }, 400)
  }

  const fail = (error: unknown) => set({ busy: false, error: error instanceof Error ? error.message : String(error) })

  const syncHistoryFlags = () => set({ canUndo: past.length > 0, canRedo: future.length > 0 })

  /** Everything undo can bring back, as it stands now. */
  const liveEntry = (): HistoryEntry => {
    const { text, caption, sfx, settings, source, slots } = get()
    const slot = slots[source]
    return { text, caption, sfx, settings, source, session: slot?.session ?? '', pins: slot?.pins ?? {}, regions: slot?.regions ?? [] }
  }

  const restore = (entry: HistoryEntry) => {
    set((state) => {
      const slot = state.slots[entry.source]
      // Places and areas go back only onto the image they were made on.
      const slots =
        slot && slot.session === entry.session
          ? { ...state.slots, [entry.source]: { ...slot, pins: entry.pins, regions: entry.regions } }
          : state.slots
      const current = slots[state.source]
      return {
        text: entry.text,
        caption: entry.caption,
        sfx: entry.sfx,
        settings: entry.settings,
        slots,
        region: current?.regions.some((region) => region.id === state.region) ? state.region : null,
        selected: current?.items.some((item) => item.id === state.selected) ? state.selected : null,
      }
    })
    replaying = true
    syncHistoryFlags()
    void get().render()
    persist()
  }

  return {
    options: null,
    embedded: false,
    comfy: false,
    source: 'own',
    slots: { generation: null, own: null },
    hostImage: null,
    text: '',
    caption: '',
    sfx: '',
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
    canUndo: false,
    canRedo: false,

    start:async (embedded) => {
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
      void get().render({ record: false })
    },

    hostOpened: async (image, node) => {
      set({ hostImage: image, error: null })
      if (node) {
        // What the node holds wins over what the page had: its widgets may have been changed by hand.
        const now = get()
        const held = now.slots.generation
        const mine = {
          texts: { text: now.text, caption: now.caption, sfx: now.sfx },
          settings: now.settings,
          layout: held ? { pins: held.pins, regions: held.regions } : nodeLayout,
        }
        const theirs = { texts: node.texts, settings: { ...(now.options?.defaults ?? {}), ...node.settings }, layout: node.layout }
        if (stable(mine) !== stable(theirs)) {
          // The node was changed outside the editor: the steps taken here no longer lead back to it.
          past = []
          future = []
          syncHistoryFlags()
        }
        nodeLayout = node.layout
        set((state) => ({
          comfy: true,
          auto: false,
          text: node.texts.text,
          caption: node.texts.caption,
          sfx: node.texts.sfx,
          settings: { ...(state.options?.defaults ?? {}), ...node.settings },
        }))
      }
      if (!image.url && !node) {
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
            await get().render({ record: false })
            return
          }
          created = answer
        } catch (error) {
          if (!image.url) {
            // ComfyUI: the node has not run yet, so there is no image of its own to show.
            set((state) => ({ busy: false, slots: { ...state.slots, generation: null } }))
            return
          }
          void error
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
          slots: {
            ...state.slots,
            // In ComfyUI the layout the node holds goes onto the image the node last saw.
            generation: { ...slotOf(created), origin: created.origin, ...(node ? { pins: node.layout.pins, regions: node.layout.regions } : {}) },
          },
        }))
        await get().render({ record: false })
      } catch (error) {
        fail(error)
      }
    },

    loadFile:async (file, name) => {
      set({ busy: true, error: null })
      try {
        const created = await api.upload(file, name)
        set((state) => ({ busy: false, slots: { ...state.slots, own: slotOf(created) } }))
        await get().render({ record: false })
      } catch (error) {
        fail(error)
      }
    },

    setField: (field, value) => {
      set({ [field]: value } as Pick<State, 'text' | 'caption' | 'sfx'>)
      persist()
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

    transformRegion: (id, factor, turn) => {
      const slot = get().slots[get().source]
      const region = slot?.regions.find((candidate) => candidate.id === id)
      const box = region ? boxOf(region.shapes) : null
      if (!region || !box) return
      set({ nudge: null })
      // The text tilts counter-clockwise for a positive number; the area turns clockwise.
      let rotation = (region.rotation ?? 0) - turn
      while (rotation > 180) rotation -= 360
      while (rotation < -180) rotation += 360
      const change: Partial<Region> = turn ? { rotation: Math.round(rotation * 2) / 2 } : {}
      if (region.template) {
        const [x0, y0, x1, y1] = region.template.box
        const cx = (x0 + x1) / 2
        const cy = (y0 + y1) / 2
        const template = {
          ...region.template,
          box: [cx - ((x1 - x0) / 2) * factor, cy - ((y1 - y0) / 2) * factor, cx + ((x1 - x0) / 2) * factor, cy + ((y1 - y0) / 2) * factor] as [number, number, number, number],
          angle: (region.template.angle ?? 0) + turn,
        }
        get().changeRegion(id, { ...change, template, shapes: bubbleShapes(template) })
        return
      }
      const cx = (box[0] + box[2]) / 2
      const cy = (box[1] + box[3]) / 2
      get().changeRegion(id, {
        ...change,
        shapes: region.shapes.map((shape) =>
          shape.type === 'polygon'
            ? { ...shape, points: turned(shape.points, cx, cy, turn, factor) }
            : { ...shape, points: turned(shape.points, cx, cy, turn, factor), width: Math.max(2, shape.width * factor) },
        ),
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

    render: async (options) => {
      // Kept outside the call: a render that waits for the one under way is run again without its arguments.
      if (options?.record === false) suppressRecord = true
      const state = get()
      const slot = state.slots[state.source]
      if (!slot) return
      if (rendering) {
        renderAgain = true
        return
      }
      const { text, caption, sfx, settings, source } = state
      const signature = JSON.stringify([text, caption, sfx, settings, slot.pins, slot.regions])
      if (signature === slot.applied) {
        replaying = false
        suppressRecord = false
        return
      }
      if (!replaying && !suppressRecord && slot.applied !== '') {
        // What the image showed until now is the step to go back to.
        const [oldText, oldCaption, oldSfx, oldSettings, oldPins, oldRegions] = JSON.parse(slot.applied) as [
          string,
          string,
          string,
          Settings,
          Slot['pins'],
          Region[],
        ]
        const entry: HistoryEntry = {
          text: oldText,
          caption: oldCaption,
          sfx: oldSfx,
          settings: oldSettings,
          source,
          session: slot.session,
          pins: oldPins,
          regions: oldRegions,
        }
        const top = past[past.length - 1]
        // After a render that failed the same step would be kept twice.
        if (!top || JSON.stringify(top) !== JSON.stringify(entry)) past.push(entry)
        if (past.length > HISTORY_LIMIT) past.splice(0, past.length - HISTORY_LIMIT)
        future = []
      }
      replaying = false
      suppressRecord = false
      syncHistoryFlags()
      rendering = true
      set({ busy: true, error: null })
      try {
        const result = await api.render(slot.session, text, caption, sfx, settings, slot.pins, slot.regions)
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
        if (get().comfy) persist()
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

    undo: () => {
      const entry = past.pop()
      if (!entry) return
      future.push(liveEntry())
      restore(entry)
    },

    redo: () => {
      const entry = future.pop()
      if (!entry) return
      past.push(liveEntry())
      if (past.length > HISTORY_LIMIT) past.splice(0, past.length - HISTORY_LIMIT)
      restore(entry)
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
