import { useEffect, useMemo } from 'react'
import { api } from './api'
import type { Options } from './types'

/** How a mark is painted: its shape cut out of a square in the color of the text around it.
 * A mark without a mask is the plain character, asked to be drawn as text and not as a color emoji. */
const MARK_RULES =
  '.cl-mark{display:inline-block;width:1em;height:1em;background-color:currentColor;' +
  '-webkit-mask-size:contain;mask-size:contain;-webkit-mask-repeat:no-repeat;mask-repeat:no-repeat;' +
  '-webkit-mask-position:center;mask-position:center}' +
  '.cl-mark-char{font-variant-emoji:text}'

/** What the page draws with that only the server has: the fonts, so a list can show each entry
 * in its own font, and the shapes of the marks, so a button shows what will be drawn. Both go
 * into one style sheet, written when the options arrive.
 *
 * Returns the font family to draw a font's name in, or undefined for a name that is not a font. */
export function useAssetStyles(options: Options | null) {
  const families = useMemo(() => {
    const map = new Map<string, string>()
    options?.fonts.forEach((name, index) => map.set(name, `clf-${index}`))
    return map
  }, [options])
  useEffect(() => {
    if (!options) return
    const style = document.createElement('style')
    const fonts = options.fonts
      .map((name, index) => `@font-face{font-family:'clf-${index}';src:url('${api.fontUrl(name)}');font-display:swap}`)
      .join('')
    const marks = (options.marks ?? [])
      .map((mark, index) => `.cl-mark-${index}{-webkit-mask-image:url("${mark.mask}");mask-image:url("${mark.mask}")}`)
      .join('')
    style.textContent = fonts + MARK_RULES + marks
    document.head.appendChild(style)
    return () => style.remove()
  }, [options])
  return (name: string) => (families.has(name) ? `'${families.get(name)}', sans-serif` : undefined)
}
