import { useEffect, useMemo, useRef, useState, type ReactNode } from 'react'
import { api } from '../api'
import { useStore } from '../store'
import { BUBBLE_SHAPES, BUBBLE_TAILS } from '../geometry'
import type { BubbleShape, BubbleTail, Region, RegionKind, SectionId, Tool } from '../types'
import { Button, ColorField, Icon, IconButton, Section, Segmented, Select, Slider, Toggle } from './controls'

type FieldName = 'text' | 'caption' | 'sfx'

interface SliderSpec {
  key: string
  label: string
  hint: string
  min: number
  max: number
  step: number
}

// A label is short enough for one line; the hint says the same in full, on hover.
const ALL_TEXT: SliderSpec[] = [
  { key: 'soften', label: 'Soften edges, px', hint: 'Blur the letter edges, in pixels', min: 0, max: 3, step: 0.1 },
  { key: 'grain', label: 'Uneven ink', hint: 'Ink that is thinner in places, like a worn stamp', min: 0, max: 1, step: 0.05 },
  { key: 'arc', label: 'Bend into an arc', hint: 'Curve the lines up or down', min: -1, max: 1, step: 0.05 },
  { key: 'rotation', label: 'Tilt, °', hint: 'Tilt all text, degrees', min: -45, max: 45, step: 0.5 },
  { key: 'opacity', label: 'Opacity', hint: 'How solid all text is', min: 0.1, max: 1, step: 0.05 },
]
const BUBBLES: SliderSpec[] = [
  { key: 'bubble_size', label: 'Largest font, %', hint: 'Largest font in a bubble, % of image height', min: 1, max: 30, step: 0.5 },
  {
    key: 'bubble_min_size',
    label: 'Smallest font, %',
    hint: 'Smallest font still readable, % of image height; longer text goes elsewhere',
    min: 0.5,
    max: 10,
    step: 0.1,
  },
  { key: 'margin', label: 'Gap to the edge', hint: "Space between the text and the bubble's edge", min: 0, max: 0.3, step: 0.01 },
  { key: 'white_threshold', label: 'Darkest bubble fill', hint: 'The darkest fill still taken for a bubble (0-255)', min: 40, max: 255, step: 1 },
]
const CAPTION: SliderSpec[] = [
  { key: 'free_size', label: 'Font size, %', hint: 'Caption font size, % of image height', min: 1, max: 30, step: 0.5 },
  { key: 'stroke_width', label: 'Outline width', hint: 'Caption outline width', min: 0, max: 0.5, step: 0.01 },
  { key: 'shadow', label: 'Shadow', hint: 'Caption shadow strength', min: 0, max: 1, step: 0.05 },
]
const EFFECTS: SliderSpec[] = [
  { key: 'sfx_size', label: 'Font size, %', hint: 'Effect font size, % of image height', min: 1, max: 30, step: 0.5 },
  { key: 'sfx_tilt', label: 'Largest tilt, °', hint: 'Effects tilt at random up to this many degrees', min: 0, max: 45, step: 1 },
  { key: 'sfx_opacity', label: 'Opacity', hint: 'How solid the effects are', min: 0.1, max: 1, step: 0.05 },
]
const CUSTOM_MOOD: SliderSpec[] = [
  { key: 'jitter', label: 'Letters wobble', hint: 'Letters move off the line', min: 0, max: 1, step: 0.05 },
  { key: 'size_jitter', label: 'Letter sizes vary', hint: 'Letters differ in size', min: 0, max: 1, step: 0.05 },
  { key: 'rough', label: 'Ragged edges', hint: 'Letter edges are torn', min: 0, max: 1, step: 0.05 },
  { key: 'line_tilt', label: 'Lines tilt, °', hint: 'Each line tilts a little, degrees', min: 0, max: 15, step: 0.5 },
  { key: 'line_shift', label: 'Lines shift', hint: 'Lines move sideways', min: 0, max: 1, step: 0.05 },
  { key: 'line_spacing', label: 'Line spacing', hint: 'Space between lines', min: 0.7, max: 1.6, step: 0.02 },
]

/** The part of the panel each text field is in. */
const SECTION_OF: Record<FieldName, SectionId> = { text: 'bubbles', caption: 'caption', sfx: 'sfx' }

/** How many mark buttons show before "All marks" is pressed. */
const FEW_MARKS = 8

const KINDS: { value: RegionKind; label: string }[] = [
  { value: 'text', label: 'Text' },
  { value: 'sfx', label: 'Effect' },
  { value: 'keepout', label: 'Keep out' },
]
const FILLS: { value: Region['fill']; label: string }[] = [
  { value: 'none', label: 'On the art' },
  { value: 'light', label: 'Light bubble' },
  { value: 'dark', label: 'Dark bubble' },
]

const KIND_NAMES: Record<RegionKind, string> = { text: 'text', sfx: 'effect', keepout: 'keep out' }

/** What to do with the tool in hand, in a line; shown while no area is picked. */
const TOOL_HINTS: Record<Tool, string> = {
  off: 'Pick a drawing tool on the left, or click an area to change it.',
  bubble: 'Drag on the image where the bubble goes, or just click.',
  brush: 'Paint where the words go. A field for the text opens beside it.',
  eraser: 'Rub out what was painted.',
}

/** The areas drawn by hand. The picked one shows its settings (its text is typed on the image);
 * the others are a line each. What the tool in hand will draw next shows only while no area is
 * picked, so a bubble's shape and tail are never on the panel twice. */
function AreasPanel() {
  const tool = useStore((state) => state.tool)
  const brush = useStore((state) => state.brush)
  const pickedId = useStore((state) => state.region)
  const regions = useStore((state) => state.slots[state.source]?.regions)
  const stamp = useStore((state) => state.stamp)
  const { setBrush, pickRegion, changeRegion, removeRegion, undoShape, render, setStamp, reshape } = useStore.getState()
  const shapes = BUBBLE_SHAPES.map((value) => ({ value, label: value[0].toUpperCase() + value.slice(1) }))
  if (!regions) return null
  const picked = regions.some((region) => region.id === pickedId) ? pickedId : null
  return (
    <>
      {picked === null && tool === 'bubble' && (
        <>
          <Segmented<BubbleShape> value={stamp.shape} options={shapes} onChange={(shape) => setStamp({ shape })} />
          <div className="grid grid-cols-2 gap-2">
            <Select label="Tail" value={stamp.tail} options={BUBBLE_TAILS} onChange={(tail) => setStamp({ tail: tail as BubbleTail })} />
            <Select label="Bubble color" value={stamp.fill} options={['light', 'dark']} onChange={(fill) => setStamp({ fill: fill as 'light' | 'dark' })} />
          </div>
        </>
      )}
      {picked === null && (tool === 'brush' || tool === 'eraser') && (
        <Slider
          label={tool === 'eraser' ? 'Eraser width, %' : 'Brush width, %'}
          hint="Width, % of the image's shorter side"
          value={Math.round(brush * 100)}
          min={1}
          max={30}
          step={1}
          onChange={(value) => setBrush(value / 100)}
          onCommit={() => undefined}
        />
      )}
      {picked === null && <p className="text-[11px] leading-snug text-cl-muted">{TOOL_HINTS[tool]}</p>}
      {regions.map((region, index) =>
        region.id !== picked ? (
          <div key={region.id} className="flex items-center gap-1">
            <button
              type="button"
              onClick={() => pickRegion(region.id)}
              className="flex h-8 min-w-0 flex-1 items-center gap-2 rounded border border-cl-border px-2 text-left hover:border-cl-muted focus-visible:outline focus-visible:outline-2 focus-visible:outline-cl-accent"
            >
              <span className={`h-2.5 w-2.5 shrink-0 rounded-sm ${region.kind === 'keepout' ? 'bg-cl-danger' : 'bg-cl-hand'}`} aria-hidden="true" />
              <span className="shrink-0 text-xs font-medium text-cl-text">Area {index + 1}</span>
              <span className="shrink-0 text-[11px] text-cl-muted">{KIND_NAMES[region.kind]}</span>
              <span className="min-w-0 flex-1 truncate text-[11px] text-cl-muted">
                {region.kind !== 'keepout' && region.text.trim() ? region.text.trim().replace(/\s+/g, ' ') : '—'}
              </span>
            </button>
            <IconButton label={`Delete area ${index + 1}`} onClick={() => removeRegion(region.id)}>
              <Icon>
                <path d="M3 4.5h10M6.5 4.5V3h3v1.5M4.5 4.5l.7 8.5h5.6l.7-8.5" />
              </Icon>
            </IconButton>
          </div>
        ) : (
          <div key={region.id} className="flex flex-col gap-1.5 rounded border border-cl-accent p-2">
            <div className="flex items-center justify-between gap-2">
              <span className="text-xs font-medium text-cl-text">Area {index + 1}</span>
              <span className="flex items-center">
                <Button variant="quiet" onClick={() => undoShape(region.id)} title="Take back the last thing drawn in this area">
                  Undo stroke
                </Button>
                <Button variant="quiet" onClick={() => removeRegion(region.id)}>
                  Delete
                </Button>
                <Button
                  variant="quiet"
                  onClick={() => {
                    void render()
                    pickRegion(null)
                  }}
                >
                  Done
                </Button>
              </span>
            </div>
            <Segmented value={region.kind} options={KINDS} onChange={(kind) => changeRegion(region.id, { kind })} />
            {region.template && (
              <>
                <Segmented<BubbleShape> value={region.template.shape} options={shapes} onChange={(shape) => reshape(region.id, { shape })} />
                <Select label="Tail" value={region.template.tail} options={BUBBLE_TAILS} onChange={(tail) => reshape(region.id, { tail: tail as BubbleTail })} />
              </>
            )}
            {region.kind === 'text' && <Segmented value={region.fill} options={FILLS} onChange={(fill) => changeRegion(region.id, { fill })} />}
            {region.kind !== 'keepout' && region.shapes.some((shape) => shape.type === 'stroke') && (
              <Toggle checked={region.follow === true} onChange={(follow) => changeRegion(region.id, { follow })} label="Write along the brush stroke" />
            )}
            {region.kind !== 'keepout' && region.follow === true && (
              <Toggle checked={region.flip === true} onChange={(flip) => changeRegion(region.id, { flip })} label="Turn the text round" />
            )}
            {region.kind !== 'keepout' && (
              <>
                <Slider
                  label="Size, %"
                  hint="Text size, % of what the area gives"
                  value={Math.round((region.scale ?? 1) * 100)}
                  min={30}
                  max={300}
                  step={5}
                  onChange={(value) => changeRegion(region.id, { scale: value / 100 }, false)}
                  onCommit={() => void render()}
                />
                {region.follow !== true && (
                  <Slider
                    label={region.rotation === undefined && region.kind === 'sfx' ? 'Tilt, ° (random now)' : 'Tilt, °'}
                    hint="Tilt of the text, degrees"
                    value={region.rotation ?? 0}
                    min={-90}
                    max={90}
                    step={1}
                    onChange={(value) => changeRegion(region.id, { rotation: value }, false)}
                    onCommit={() => void render()}
                  />
                )}
                {region.follow !== true && region.rotation !== undefined && (
                  <Button variant="quiet" onClick={() => changeRegion(region.id, { rotation: undefined })}>
                    {region.kind === 'sfx' ? 'Back to a random tilt' : 'Back to no tilt of its own'}
                  </Button>
                )}
              </>
            )}
          </div>
        ),
      )}
    </>
  )
}

/** A small heading inside a section. */
function Group({ title, children }: { title: string; children: ReactNode }) {
  return (
    <div className="flex flex-col gap-2">
      <div className="mt-1 text-[11px] uppercase tracking-wide text-cl-muted">{title}</div>
      {children}
    </div>
  )
}

function Sliders({ specs }: { specs: SliderSpec[] }) {
  const settings = useStore((state) => state.settings)
  const setSetting = useStore((state) => state.setSetting)
  const render = useStore((state) => state.render)
  return (
    <>
      {specs.map((spec) => (
        <Slider
          key={spec.key}
          label={spec.label}
          hint={spec.hint}
          value={Number(settings[spec.key] ?? 0)}
          min={spec.min}
          max={spec.max}
          step={spec.step}
          onChange={(value) => setSetting(spec.key, value, false)}
          onCommit={() => void render()}
        />
      ))}
    </>
  )
}

function Check({ name, label }: { name: string; label: string }) {
  const value = useStore((state) => Boolean(state.settings[name]))
  const setSetting = useStore((state) => state.setSetting)
  return <Toggle checked={value} onChange={(next) => setSetting(name, next)} label={label} />
}

function Color({ name, label }: { name: string; label: string }) {
  const value = useStore((state) => String(state.settings[name] ?? 'auto'))
  const setSetting = useStore((state) => state.setSetting)
  return (
    <ColorField
      label={label}
      hint={`${label}: left to the script, or a color of your own`}
      value={value}
      onDraft={(next) => setSetting(name, next, false)}
      onCommit={(next) => setSetting(name, next, true)}
    />
  )
}

/** The sliders behind the mood "custom". There is one set of them: every text set to custom follows it. */
function CustomMood() {
  return (
    <Group title="Custom mood (shared by all text)">
      <Sliders specs={CUSTOM_MOOD} />
    </Group>
  )
}

/** What a folded section says of its text: the first line that has something in it, cut short. */
function firstLine(text: string) {
  const line = text.split('\n').find((entry) => entry.trim()) ?? ''
  const short = line.trim()
  if (!short) return 'empty'
  return short.length > 24 ? `${short.slice(0, 23)}…` : short
}

export function SidePanel() {
  const options = useStore((state) => state.options)
  const settings = useStore((state) => state.settings)
  const fields = {
    text: useStore((state) => state.text),
    caption: useStore((state) => state.caption),
    sfx: useStore((state) => state.sfx),
  }
  const auto = useStore((state) => state.auto)
  const embedded = useStore((state) => state.embedded)
  const comfy = useStore((state) => state.comfy)
  const open = useStore((state) => state.open)
  const areaCount = useStore((state) => state.slots[state.source]?.regions.length ?? 0)
  const { setField, setSetting, setAuto, setOpen, moveEffects, resetLook, render } = useStore.getState()

  const areas = useRef<Record<FieldName, HTMLTextAreaElement | null>>({ text: null, caption: null, sfx: null })
  // Bubbles is the part that is unfolded at the start.
  const lastField = useRef<FieldName>('text')
  const [more, setMore] = useState<Record<FieldName, boolean>>({ text: false, caption: false, sfx: false })
  const [allMarks, setAllMarks] = useState(false)
  const [keepFonts, setKeepFonts] = useState(true)

  // Every font of the lists, so an entry can be drawn in its own font.
  const families = useMemo(() => {
    const map = new Map<string, string>()
    options?.fonts.forEach((name, index) => map.set(name, `clf-${index}`))
    return map
  }, [options])
  useEffect(() => {
    if (!options) return
    const style = document.createElement('style')
    style.textContent = options.fonts
      .map((name, index) => `@font-face{font-family:'clf-${index}';src:url('${api.fontUrl(name)}');font-display:swap}`)
      .join('')
    document.head.appendChild(style)
    return () => style.remove()
  }, [options])

  if (!options) return null
  const fontOf = (name: string) => (families.has(name) ? `'${families.get(name)}', sans-serif` : undefined)
  const list = (key: string, label: string, choices: string[], fonts = false) => (
    <Select
      key={key}
      label={label}
      value={String(settings[key] ?? '')}
      options={choices}
      onChange={(value) => setSetting(key, value)}
      fontOf={fonts ? fontOf : undefined}
    />
  )

  /** Put a mark where the cursor is in the text field used last. */
  const insert = (mark: string) => {
    const name = lastField.current
    // The field may be folded away: show where the mark went.
    setOpen(SECTION_OF[name], true)
    const area = areas.current[name]
    const value = fields[name]
    const start = area?.selectionStart ?? value.length
    const end = area?.selectionEnd ?? start
    const before = value.slice(0, start)
    const lead = before && !/\s$/.test(before) ? ' ' : ''
    setField(name, before + lead + mark + value.slice(end))
    requestAnimationFrame(() => {
      const field = areas.current[name]
      if (!field) return
      field.focus()
      field.selectionStart = field.selectionEnd = before.length + lead.length + mark.length
    })
  }

  const field = (name: FieldName, hint: string, rows: number) => (
    <textarea
      ref={(element) => {
        areas.current[name] = element
      }}
      value={fields[name]}
      rows={rows}
      placeholder={hint}
      spellCheck={false}
      onFocus={() => {
        lastField.current = name
      }}
      onChange={(event) => setField(name, event.target.value)}
      onBlur={() => void render()}
      onKeyDown={(event) => {
        if (event.key === 'Enter' && (event.ctrlKey || event.metaKey)) void render()
      }}
      className="w-full resize-y rounded border border-cl-border bg-cl-raised px-2 py-1.5 text-sm placeholder:text-cl-muted"
    />
  )
  const clear = (name: FieldName) => (
    <Button
      variant="quiet"
      onClick={() => {
        setField(name, '')
        void render()
      }}
    >
      Clear
    </Button>
  )
  /** The button that shows the rest of a kind's settings, and those settings. */
  const rest = (name: FieldName, children: ReactNode) => (
    <>
      <div>
        <Button variant="quiet" onClick={() => setMore({ ...more, [name]: !more[name] })}>
          {more[name] ? 'Less' : 'More…'}
        </Button>
      </div>
      {more[name] && children}
    </>
  )
  const drawn = settings.caption_bubble !== 'none'
  const fold = (id: SectionId) => (value: boolean) => setOpen(id, value)

  return (
    <aside className="flex w-80 shrink-0 flex-col gap-3 overflow-y-auto border-l border-cl-border bg-cl-surface p-3">
      <Section
        id="cl-bubbles"
        title="Bubbles"
        summary={`${firstLine(fields.text)} · ${String(settings.font ?? '')}`}
        open={open.bubbles}
        onToggle={fold('bubbles')}
        actions={clear('text')}
      >
        {field('text', 'One line per bubble, in the order of the numbers on the image; an empty line skips one.', 3)}
        <div className="grid grid-cols-2 gap-2">
          {list('font', 'Font', options.fonts, true)}
          {list('bubble_colors', 'Colors', options.palettes)}
          {list('bubble_mood', 'Mood', options.moods)}
        </div>
        {settings.bubble_mood === 'custom' && <CustomMood />}
        {rest(
          'text',
          <>
            <Check name="erase" label="Erase the letters the model drew" />
            <Check name="spill" label="Text too long for a bubble goes to the caption" />
            <Sliders specs={BUBBLES} />
            {settings.bubble_colors === 'custom' && <Color name="text_color" label="Text color (shared with Caption)" />}
          </>,
        )}
      </Section>

      <Section
        id="cl-caption"
        title="Caption"
        summary={`${firstLine(fields.caption)} · ${String(settings.placement ?? '')}`}
        open={open.caption}
        onToggle={fold('caption')}
        actions={clear('caption')}
      >
        {field('caption', 'Text on the art, outside the bubbles.', 2)}
        <div className="grid grid-cols-2 gap-2">
          {list('caption_font', 'Font', [options.sameFont, ...options.fonts], true)}
          {list('caption_colors', 'Colors', options.palettes)}
          {list('caption_mood', 'Mood', options.moods)}
          {list('caption_extras', 'Marks around', options.extras)}
          {list('placement', 'Position', options.placements)}
          {list('caption_bubble', 'Put in a bubble', options.shapes)}
          {drawn && list('caption_bubble_theme', 'Bubble color', options.themes)}
          {drawn && list('caption_tail', 'Tail', options.tails)}
        </div>
        {settings.caption_mood === 'custom' && <CustomMood />}
        {rest(
          'caption',
          <>
            <Sliders specs={CAPTION} />
            {settings.caption_colors === 'custom' && (
              <>
                <Color name="text_color" label="Text color (shared with Bubbles)" />
                <Color name="stroke_color" label="Outline color" />
              </>
            )}
          </>,
        )}
      </Section>

      <Section
        id="cl-sfx"
        title="Sound effects"
        summary={`${firstLine(fields.sfx)} · ${String(settings.sfx_font ?? '')}`}
        open={open.sfx}
        onToggle={fold('sfx')}
        actions={
          <>
            <Button variant="quiet" onClick={moveEffects} title="Put the effects somewhere else">
              Shuffle
            </Button>
            {clear('sfx')}
          </>
        }
      >
        {field('sfx', 'One per line: SLAP, THUD x3.', 2)}
        <div className="grid grid-cols-2 gap-2">
          {list('sfx_font', 'Font', options.fonts, true)}
          {list('sfx_colors', 'Colors', options.palettes)}
          {list('sfx_mood', 'Mood', options.moods)}
          {list('sfx_extras', 'Marks around', options.extras)}
        </div>
        {settings.sfx_mood === 'custom' && <CustomMood />}
        {rest(
          'sfx',
          <>
            <Sliders specs={EFFECTS} />
            {settings.sfx_colors === 'custom' && <Color name="sfx_color" label="Color" />}
          </>,
        )}
      </Section>

      <div className="flex flex-wrap items-center gap-1">
        {(allMarks ? options.symbols : options.symbols.slice(0, FEW_MARKS)).map((mark) => (
          <Button key={mark} onClick={() => insert(mark)} title="Insert at the cursor">
            {mark}
          </Button>
        ))}
        {options.symbols.length > FEW_MARKS && (
          <Button variant="quiet" onClick={() => setAllMarks(!allMarks)}>
            {allMarks ? 'Fewer' : `All ${options.symbols.length} marks`}
          </Button>
        )}
        <span className="basis-full text-[11px] text-cl-muted">
          Marks are drawn as shapes in the text's colors. *word* makes a word bigger.
        </span>
      </div>

      <Section
        id="cl-areas"
        title="Areas drawn by hand"
        summary={areaCount ? `${areaCount} ${areaCount === 1 ? 'area' : 'areas'}` : 'none'}
        open={open.areas}
        onToggle={fold('areas')}
      >
        <AreasPanel />
      </Section>

      <Section
        id="cl-all"
        title="All text"
        summary={`capitals ${settings.uppercase ? 'on' : 'off'} · opacity ${String(settings.opacity ?? '')}`}
        open={open.all}
        onToggle={fold('all')}
      >
        <Check name="uppercase" label="Capital letters" />
        <Sliders specs={ALL_TEXT} />
        <div className="grid min-w-0 grid-cols-[minmax(0,1fr)_auto_48px] items-center gap-2">
          <span className="truncate text-xs text-cl-text" title="One number picks the wobble pattern, the marks around and the drawn caption bubble">
            Pattern
          </span>
          <Button onClick={() => setSetting('seed', (Number(settings.seed) || 0) + 1)}>
            <Icon>
              <rect x="2.5" y="2.5" width="11" height="11" rx="2" />
              <circle cx="5.5" cy="5.5" r="0.6" />
              <circle cx="8" cy="8" r="0.6" />
              <circle cx="10.5" cy="10.5" r="0.6" />
            </Icon>
            Try another
          </Button>
          <span className="text-right text-[11px] text-cl-muted">#{Number(settings.seed) || 0}</span>
        </div>
        <div className="flex items-center justify-between gap-2">
          <Button onClick={() => resetLook(keepFonts)}>Reset the look</Button>
          <Toggle checked={keepFonts} onChange={setKeepFonts} label="Keep the fonts" />
        </div>
      </Section>

      {embedded && !comfy && (
        <Section id="cl-auto" title="Automatic mode" summary={auto ? 'on' : 'off'} open={open.auto} onToggle={fold('auto')}>
          <div>
            <Toggle id="cl-auto-toggle" checked={auto} onChange={setAuto} label="Letter every new image while it is generated" />
            <p className="mt-1 text-[11px] leading-snug text-cl-muted">
              Uses the three texts above and this look for each image a generation makes.
            </p>
          </div>
        </Section>
      )}
    </aside>
  )
}
