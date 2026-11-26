import type { ReactNode } from 'react'
import { useStore } from '../store'
import type { Tool } from '../types'
import { Icon } from './controls'

/** The tools as a paint program shows them: an icon each, with the key that picks it. */
const TOOLS: { value: Tool; name: string; key: string; does: string; icon: ReactNode }[] = [
  {
    value: 'off',
    name: 'Arrow',
    key: 'V',
    does: 'drag areas, captions and effects; click an area to edit its text',
    icon: <path d="M4 2l8 6-3.4.8L10.8 13l-1.7.8-2.3-4.2L4 12z" />,
  },
  {
    value: 'bubble',
    name: 'Bubble',
    key: 'B',
    does: 'put a ready-made bubble on the image',
    icon: <path d="M8 2.2c3.4 0 6 2.1 6 4.7s-2.6 4.700-6 4.700c-.6 0-1.200-.1-1.800-.2L3.300 13.800l.8-2.900C2.800 10 2 8.500 2 6.900c0-2.600 2.600-4.700 6-4.700z" />,
  },
  {
    value: 'brush',
    name: 'Brush',
    key: 'P',
    does: 'paint an area',
    icon: (
      <>
        <path d="M10.5 2.5l3 3-5.6 5.6-3-3z" />
        <path d="M4.6 9.2c-1.6.5-2.2 2-2.2 4.2 2.2 0 3.8-.5 4.3-2.1" />
      </>
    ),
  },
  {
    value: 'eraser',
    name: 'Eraser',
    key: 'E',
    does: 'rub out what was painted',
    icon: (
      <>
        <path d="M2.8 10.2l6.4-6.4 4 4-6.4 6.4H4.6z" />
        <path d="M6.4 6.6l4 4M2.5 14.2h11" />
      </>
    ),
  },
]

const BUTTON = 'flex h-8 w-8 items-center justify-center rounded border disabled:opacity-40'
const IDLE = 'border-cl-border bg-cl-raised text-cl-muted hover:border-cl-muted hover:text-cl-text'

/** The drawing tools, in a rail beside the image: always in the same place, however far the panel is scrolled. */
export function ToolRail() {
  const tool = useStore((state) => state.tool)
  const picked = useStore((state) => state.region)
  const hasImage = useStore((state) => state.slots[state.source] !== null)
  const { setTool, pickRegion } = useStore.getState()
  return (
    <nav aria-label="Tools" className="flex w-12 shrink-0 flex-col items-center gap-1.5 border-r border-cl-border bg-cl-surface pt-2.5">
      {TOOLS.map((entry) => {
        const label = `${entry.name} (${entry.key}): ${entry.does}`
        return (
          <button
            key={entry.value}
            type="button"
            title={label}
            aria-label={label}
            aria-pressed={tool === entry.value}
            disabled={!hasImage}
            onClick={() => setTool(entry.value)}
            className={`${BUTTON} ${tool === entry.value ? 'border-cl-accent bg-cl-accent/20 text-cl-accent-text' : IDLE}`}
          >
            <Icon>{entry.icon}</Icon>
          </button>
        )
      })}
      <span className="h-px w-6 bg-cl-border" aria-hidden="true" />
      <button
        type="button"
        title="New area (N): the next thing you draw starts a new area, even on top of the picked one"
        aria-label="New area (N): the next thing you draw starts a new area, even on top of the picked one"
        disabled={!hasImage || !picked}
        onClick={() => pickRegion(null)}
        className={`${BUTTON} ${IDLE}`}
      >
        <Icon>
          <path d="M8 3v10M3 8h10" />
        </Icon>
      </button>
    </nav>
  )
}
