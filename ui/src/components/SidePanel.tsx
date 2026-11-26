import { useEffect, useMemo, useRef, useState, type ReactNode } from 'react'
import { api } from '../api'
import { useStore } from '../store'
import type { LookOf, Region, RegionKind, Tool } from '../types'
import { Button, Label, Segmented, Select, Slider, TextInput, Toggle } from './controls'

type FieldName = 'text' | 'caption' | 'sfx'

interface SliderSpec {
  key: string
  label: string
  min: number
  max: number
  step: number
}

const ALL_TEXT: SliderSpec[] = [
  { key: 'soften', label: 'Soften the edges, px', min: 0, max: 3, step: 0.1 },
  { key: 'grain', label: 'Uneven ink', min: 0, max: 1, step: 0.05 },
  { key: 'arc', label: 'Bend into an arc', min: -1, max: 1, step: 0.05 },
  { key: 'rotation', label: 'Tilt, degrees', min: -45, max: 45, step: 0.5 },
  { key: 'opacity', label: 'Opacity', min: 0.1, max: 1, step: 0.05 },
]
const BUBBLES: SliderSpec[] = [
  { key: 'bubble_size', label: 'Largest font, % of image height', min: 1, max: 30, step: 0.5 },
  { key: 'bubble_min_size', label: 'Smallest readable font, %', min: 0.5, max: 10, step: 0.1 },
  { key: 'margin', label: 'Gap to the bubble edge', min: 0, max: 0.3, step: 0.01 },
  { key: 'white_threshold', label: 'Darkest fill still seen as a bubble', min: 40, max: 255, step: 1 },
]
const CAPTION: SliderSpec[] = [
  { key: 'free_size', label: 'Font size, % of image height', min: 1, max: 30, step: 0.5 },
  { key: 'stroke_width', label: 'Outline width', min: 0, max: 0.5, step: 0.01 },
  { key: 'shadow', label: 'Shadow', min: 0, max: 1, step: 0.05 },
]
const EFFECTS: SliderSpec[] = [
  { key: 'sfx_size', label: 'Font size, % of image height', min: 1, max: 30, step: 0.5 },
  { key: 'sfx_tilt', label: 'Largest tilt, degrees', min: 0, max: 45, step: 1 },
  { key: 'sfx_opacity', label: 'Opacity', min: 0.1, max: 1, step: 0.05 },
  { key: 'sfx_seed', label: 'Arrangement number (Move raises it)', min: 0, max: 999, step: 1 },
]
const CUSTOM_MOOD: SliderSpec[] = [
  { key: 'jitter', label: 'Letters wobble', min: 0, max: 1, step: 0.05 },
  { key: 'size_jitter', label: 'Letters differ in size', min: 0, max: 1, step: 0.05 },
  { key: 'rough', label: 'Ragged edges', min: 0, max: 1, step: 0.05 },
  { key: 'line_tilt', label: 'Lines tilt, degrees', min: 0, max: 15, step: 0.5 },
  { key: 'line_shift', label: 'Lines shift sideways', min: 0, max: 1, step: 0.05 },
  { key: 'line_spacing', label: 'Line spacing', min: 0.7, max: 1.6, step: 0.02 },
  { key: 'seed', label: 'Wobble pattern number', min: 0, max: 999, step: 1 },
]

/** How many mark buttons show before "All marks" is pressed. */
const FEW_MARKS = 8

/** The tools as a paint program shows them: an icon each. Paths are drawn on a 16 by 16 grid. */
const TOOLS: { value: Tool; label: string; icon: ReactNode }[] = [
  { value: 'off', label: 'Arrow: drag areas, captions and effects; click an area to edit its text', icon: <path d="M4 2l8 6-3.4.8L10.8 13l-1.7.8-2.3-4.2L4 12z" /> },
  {
    value: 'lasso',
    label: 'Outline: draw around an area',
    icon: (
      <>
        <ellipse cx="8" cy="6.5" rx="6" ry="4.5" strokeDasharray="2.6 1.8" />
        <path d="M5.2 10.5c-1.2 1.6-.2 3.4 1.6 3.4" />
      </>
    ),
  },
  {
    value: 'brush',
    label: 'Brush: paint an area',
    icon: (
      <>
        <path d="M10.5 2.5l3 3-5.6 5.6-3-3z" />
        <path d="M4.6 9.2c-1.6.5-2.2 2-2.2 4.2 2.2 0 3.8-.5 4.3-2.1" />
      </>
    ),
  },
  {
    value: 'eraser',
    label: 'Eraser: rub out what was painted',
    icon: (
      <>
        <path d="M2.8 10.2l6.4-6.4 4 4-6.4 6.4H4.6z" />
        <path d="M6.4 6.6l4 4M2.5 14.2h11" />
      </>
    ),
  },
]

function Icon({ children }: { children: ReactNode }) {
  return (
    <svg viewBox="0 0 16 16" width="16" height="16" fill="none" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      {children}
    </svg>
  )
}
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

/** The drawing tools and the areas drawn with them. */
function AreasPanel() {
  const tool = useStore((state) => state.tool)
  const brush = useStore((state) => state.brush)
  const picked = useStore((state) => state.region)
  const regions = useStore((state) => state.slots[state.source]?.regions)
  const { setTool, setBrush, pickRegion, changeRegion, removeRegion, undoShape, render } = useStore.getState()
  if (!regions) return null
  return (
    <Section title="Areas drawn by hand">
      <div className="flex items-center gap-1" role="toolbar" aria-label="Drawing tools">
        {TOOLS.map((entry) => (
          <button
            key={entry.value}
            type="button"
            title={entry.label}
            aria-label={entry.label}
            aria-pressed={tool === entry.value}
            onClick={() => setTool(entry.value)}
            className={`flex h-8 w-8 items-center justify-center rounded border ${
              tool === entry.value
                ? 'border-cl-accent bg-cl-accent/20 text-cl-accent-text'
                : 'border-cl-border bg-cl-raised text-cl-muted hover:border-cl-muted hover:text-cl-text'
            }`}
          >
            <Icon>{entry.icon}</Icon>
          </button>
        ))}
        <span className="flex-1" />
        <Button
          disabled={!picked}
          onClick={() => pickRegion(null)}
          title="The next thing you draw starts a new area, even on top of this one"
        >
          <Icon>
            <path d="M8 3v10M3 8h10" />
          </Icon>
          New area
        </Button>
      </div>
      {(tool === 'brush' || tool === 'eraser') && (
        <Slider
          label={tool === 'eraser' ? 'Eraser width, % of the image' : 'Brush width, % of the image'}
          value={Math.round(brush * 100)}
          min={1}
          max={30}
          step={1}
          onChange={(value) => setBrush(value / 100)}
          onCommit={() => undefined}
        />
      )}
      <p className="text-[11px] leading-snug text-cl-muted">
        {tool === 'off'
          ? 'Pick the outline or the brush and draw on the image. Text or an effect is fitted into the area; a keep-out area is left free. Once an area has its text and is closed with Done, its tint goes; point at it with the arrow to see it again.'
          : tool === 'eraser'
            ? 'The eraser rubs out whatever it passes over.'
            : 'Paint an area: a field for its text opens beside it. Done closes it, and the next thing you paint is a new area.'}
      </p>
      {regions.map((region, index) => (
        <div
          key={region.id}
          onClick={() => pickRegion(region.id)}
          className={`flex flex-col gap-1.5 rounded border p-2 ${region.id === picked ? 'border-cl-accent' : 'border-cl-border'}`}
        >
          <div className="flex items-center justify-between gap-2">
            <span className="text-xs text-cl-text">Area {index + 1}</span>
            <span className="flex items-center gap-1">
              <Button variant="quiet" onClick={() => undoShape(region.id)} title="Take back the last thing drawn in this area">
                Undo
              </Button>
              <Button variant="quiet" onClick={() => removeRegion(region.id)}>
                Delete
              </Button>
            </span>
          </div>
          <Segmented value={region.kind} options={KINDS} onChange={(kind) => changeRegion(region.id, { kind })} />
          {region.kind === 'text' && (
            <Segmented value={region.fill} options={FILLS} onChange={(fill) => changeRegion(region.id, { fill })} />
          )}
          {region.kind !== 'keepout' && (
            <textarea
              value={region.text}
              rows={2}
              spellCheck={false}
              placeholder={region.kind === 'sfx' ? 'One effect: BOOM, THUD x3' : 'Text for this area'}
              onChange={(event) => changeRegion(region.id, { text: event.target.value }, false)}
              onBlur={() => void render()}
              onKeyDown={(event) => {
                if (event.key === 'Enter' && (event.ctrlKey || event.metaKey)) void render()
              }}
              className="w-full resize-y rounded border border-cl-border bg-cl-raised px-2 py-1 text-sm placeholder:text-cl-muted"
            />
          )}
          {region.kind !== 'keepout' && region.shapes.some((shape) => shape.type === 'stroke') && (
            <Toggle
              checked={region.follow === true}
              onChange={(follow) => changeRegion(region.id, { follow })}
              label="Write along the brush stroke"
            />
          )}
          {region.kind !== 'keepout' && region.follow === true && (
            <Toggle
              checked={region.flip === true}
              onChange={(flip) => changeRegion(region.id, { flip })}
              label="Turn the text round"
            />
          )}
          {region.kind !== 'keepout' && (
            <>
              <Slider
                label="Size, % of what the area gives"
                value={Math.round((region.scale ?? 1) * 100)}
                min={30}
                max={300}
                step={5}
                onChange={(value) => changeRegion(region.id, { scale: value / 100 }, false)}
                onCommit={() => void render()}
              />
              {region.follow !== true && (
                <Slider
                  label={region.rotation === undefined && region.kind === 'sfx' ? 'Tilt, degrees (random now)' : 'Tilt, degrees'}
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
      ))}
    </Section>
  )
}

function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <div className="flex flex-col gap-2 border-t border-cl-border pt-3">
      <div className="text-xs font-medium text-cl-text">{title}</div>
      {children}
    </div>
  )
}

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
  const render = useStore((state) => state.render)
  return (
    <TextInput label={label} value={value} onChange={(next) => setSetting(name, next, false)} onCommit={() => void render()} />
  )
}

export function SidePanel() {
  const options = useStore((state) => state.options)
  const settings = useStore((state) => state.settings)
  const fields = {
    text: useStore((state) => state.text),
    caption: useStore((state) => state.caption),
    sfx: useStore((state) => state.sfx),
  }
  const numbers = useStore((state) => state.numbers)
  const lookOf = useStore((state) => state.lookOf)
  const auto = useStore((state) => state.auto)
  const embedded = useStore((state) => state.embedded)
  const { setField, setNumbers, setSetting, setLookOf, setAuto, moveEffects, resetLook, render } = useStore.getState()

  const areas = useRef<Record<FieldName, HTMLTextAreaElement | null>>({ text: null, caption: null, sfx: null })
  const lastField = useRef<FieldName>('sfx')
  const [fine, setFine] = useState(false)
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
    const area = areas.current[name]
    const value = fields[name]
    const start = area?.selectionStart ?? value.length
    const end = area?.selectionEnd ?? start
    const before = value.slice(0, start)
    const lead = before && !/\s$/.test(before) ? ' ' : ''
    setField(name, before + lead + mark + value.slice(end))
    requestAnimationFrame(() => {
      if (!area) return
      area.focus()
      area.selectionStart = area.selectionEnd = before.length + lead.length + mark.length
    })
  }

  const area = (name: FieldName, label: string, hint: string, rows: number, actions: ReactNode) => (
    <div>
      <div className="mb-1 flex items-center justify-between gap-2">
        <Label>{label}</Label>
        <span className="flex items-center gap-1">{actions}</span>
      </div>
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
    </div>
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

  const looks: { value: LookOf; label: string }[] = [
    { value: 'bubble', label: 'Bubbles' },
    { value: 'caption', label: 'Caption' },
    { value: 'sfx', label: 'Effects' },
  ]
  const drawn = settings.caption_bubble !== 'none'

  return (
    <aside className="flex w-80 shrink-0 flex-col gap-3 overflow-y-auto border-l border-cl-border bg-cl-surface p-3">
      {area(
        'text',
        'Bubbles',
        'One line per bubble; an empty line skips one.',
        3,
        <>
          <Toggle checked={numbers} onChange={setNumbers} label="Numbers" />
          {clear('text')}
        </>,
      )}
      {area('caption', 'Caption', 'Text on the art, outside the bubbles.', 2, clear('caption'))}
      {area(
        'sfx',
        'Sound effects',
        'One per line: SLAP, THUD x3.',
        2,
        <>
          <Button variant="quiet" onClick={moveEffects} title="Put the effects somewhere else">
            Move
          </Button>
          {clear('sfx')}
        </>,
      )}
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

      <AreasPanel />

      <Section title="Look">
        <Segmented value={lookOf} options={looks} onChange={setLookOf} />
        <div className="grid grid-cols-2 gap-2">
          {lookOf === 'bubble' && [
            list('font', 'Font', options.fonts, true),
            list('bubble_colors', 'Colors', options.palettes),
            list('bubble_mood', 'Mood', options.moods),
          ]}
          {lookOf === 'caption' && [
            list('caption_font', 'Font', [options.sameFont, ...options.fonts], true),
            list('caption_colors', 'Colors', options.palettes),
            list('caption_mood', 'Mood', options.moods),
            list('caption_extras', 'Marks around', options.extras),
            list('placement', 'Position', options.placements),
            list('caption_bubble', 'Put in a bubble', options.shapes),
            drawn && list('caption_bubble_theme', 'Bubble color', options.themes),
            drawn && list('caption_tail', 'Tail', options.tails),
          ]}
          {lookOf === 'sfx' && [
            list('sfx_font', 'Font', options.fonts, true),
            list('sfx_colors', 'Colors', options.palettes),
            list('sfx_mood', 'Mood', options.moods),
            list('sfx_extras', 'Marks around', options.extras),
          ]}
        </div>
      </Section>

      <div className="border-t border-cl-border pt-3">
        <button
          type="button"
          aria-expanded={fine}
          onClick={() => setFine(!fine)}
          className="flex w-full items-center justify-between text-xs font-medium text-cl-text"
        >
          <span>Fine tuning</span>
          <span className="text-cl-muted" aria-hidden="true">
            {fine ? '▴' : '▾'}
          </span>
        </button>
        {fine && (
          <div className="mt-2 flex flex-col gap-3">
            <Group title="All text">
              <Check name="uppercase" label="Capital letters" />
              <Sliders specs={ALL_TEXT} />
            </Group>
            <Group title="Bubbles">
              <Check name="erase" label="Erase the letters the model drew" />
              <Check name="spill" label="Text too long for a bubble goes to the caption" />
              <Sliders specs={BUBBLES} />
            </Group>
            <Group title="Caption">
              <Sliders specs={CAPTION} />
              <Color name="text_color" label="Text color for Colors: custom (#RRGGBB or auto)" />
              <Color name="stroke_color" label="Outline color for Colors: custom (#RRGGBB or auto)" />
            </Group>
            <Group title="Sound effects">
              <Sliders specs={EFFECTS} />
              <Color name="sfx_color" label="Color for Colors: custom (#RRGGBB or auto)" />
            </Group>
            <Group title="Mood: custom">
              <Sliders specs={CUSTOM_MOOD} />
            </Group>
            <div className="flex items-center justify-between gap-2">
              <Button onClick={() => resetLook(keepFonts)}>Reset the look</Button>
              <Toggle checked={keepFonts} onChange={setKeepFonts} label="Keep the fonts" />
            </div>
          </div>
        )}
      </div>

      {embedded && (
        <div className="border-t border-cl-border pt-3">
          <Toggle checked={auto} onChange={setAuto} label="Letter every new image while it is generated" />
          <p className="mt-1 text-[11px] leading-snug text-cl-muted">
            Uses the three texts above and this look for each image a generation makes.
          </p>
        </div>
      )}
    </aside>
  )
}
