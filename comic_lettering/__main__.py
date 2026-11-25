"""CLI for quick tests: python -m comic_lettering in.png out.png --text "Hello"."""
import argparse

from PIL import Image

from . import PLACEMENTS, Style, font_names, letter


def main():
    parser = argparse.ArgumentParser(prog="comic_lettering")
    parser.add_argument("src")
    parser.add_argument("dst")
    parser.add_argument("--text", default="", help=r"bubble lines, \n between bubbles")
    parser.add_argument("--caption", default="", help=r"text on the art, \n for a line break")
    parser.add_argument("--sfx", default="", help=r"sound effects, \n between them")
    parser.add_argument("--sfx-font", default="Bangers")
    parser.add_argument("--sfx-color", default="auto")
    parser.add_argument("--sfx-seed", type=int, default=0)
    parser.add_argument("--numbers", action="store_true", help="draw bubble numbers instead of text")
    parser.add_argument("--no-spill", action="store_true",
                        help="always write into the bubbles, drop lines left over")
    parser.add_argument("--placement", choices=PLACEMENTS, default="auto")
    parser.add_argument("--caption-font", default="")
    parser.add_argument("--font", default=font_names()[0])
    parser.add_argument("--no-uppercase", action="store_true")
    parser.add_argument("--no-erase", action="store_true")
    parser.add_argument("--white-threshold", type=int, default=120)
    for name, default in (("stroke-width", 0.12), ("shadow", 0.5), ("rotation", 0.0),
                          ("jitter", 0.3), ("arc", 0.0), ("soften", 0.4), ("grain", 0.0),
                          ("opacity", 1.0), ("free-size", 5.5), ("bubble-size", 9.0),
                          ("bubble-min-size", 1.5), ("margin", 0.08), ("sfx-size", 7.0),
                          ("sfx-tilt", 15.0), ("sfx-opacity", 0.95)):
        parser.add_argument("--" + name, type=float, default=default)
    parser.add_argument("--text-color", default="auto")
    parser.add_argument("--stroke-color", default="auto")
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--opt", action="append", default=[], metavar="NAME=VALUE",
                        help="any other Style option, e.g. --opt caption_colors=pink "
                             "--opt sfx_mood=shaky --opt caption_bubble=oval")
    args = parser.parse_args()
    style = Style(font=args.font, uppercase=not args.no_uppercase, text_color=args.text_color,
                  stroke_color=args.stroke_color, stroke_width=args.stroke_width,
                  shadow=args.shadow, rotation=args.rotation, jitter=args.jitter, arc=args.arc,
                  soften=args.soften, grain=args.grain, opacity=args.opacity,
                  free_size=args.free_size, bubble_size=args.bubble_size,
                  bubble_min_size=args.bubble_min_size, margin=args.margin, seed=args.seed,
                  sfx_font=args.sfx_font, sfx_size=args.sfx_size, sfx_color=args.sfx_color,
                  sfx_tilt=args.sfx_tilt, sfx_opacity=args.sfx_opacity, sfx_seed=args.sfx_seed,
                  caption_font=args.caption_font)
    for item in args.opt:
        name, _, value = item.partition("=")
        if not hasattr(style, name):
            parser.error("unknown option: " + name)
        current = getattr(style, name)
        setattr(style, name, type(current)(value) if isinstance(current, (int, float)) else value)
    image, info = letter(Image.open(args.src), args.text.replace("\\n", "\n"),
                         caption=args.caption.replace("\\n", "\n"), spill=not args.no_spill,
                         placement=args.placement, style=style, erase=not args.no_erase,
                         white_threshold=args.white_threshold, numbers=args.numbers,
                         sfx=args.sfx.replace("\\n", "\n"))
    image.save(args.dst)
    print(info)


if __name__ == "__main__":
    main()
