"""CLI for quick tests: python -m comic_lettering in.png out.png --text "Hello"."""
import argparse

from PIL import Image

from . import MODES, PLACEMENTS, Style, font_names, letter


def main():
    parser = argparse.ArgumentParser(prog="comic_lettering")
    parser.add_argument("src")
    parser.add_argument("dst")
    parser.add_argument("--text", required=True, help=r"use \n for a line break, \n\n between bubbles")
    parser.add_argument("--mode", choices=MODES, default="auto")
    parser.add_argument("--placement", choices=PLACEMENTS, default="auto")
    parser.add_argument("--font", default=font_names()[0])
    parser.add_argument("--no-uppercase", action="store_true")
    parser.add_argument("--no-erase", action="store_true")
    parser.add_argument("--white-threshold", type=int, default=180)
    for name, default in (("stroke-width", 0.12), ("shadow", 0.5), ("rotation", 0.0),
                          ("jitter", 0.3), ("arc", 0.0), ("soften", 0.4), ("grain", 0.0),
                          ("opacity", 1.0), ("free-size", 5.5), ("bubble-size", 9.0),
                          ("bubble-min-size", 1.8),
                          ("margin", 0.08)):
        parser.add_argument("--" + name, type=float, default=default)
    parser.add_argument("--text-color", default="auto")
    parser.add_argument("--stroke-color", default="auto")
    parser.add_argument("--seed", type=int, default=0)
    args = parser.parse_args()
    style = Style(font=args.font, uppercase=not args.no_uppercase, text_color=args.text_color,
                  stroke_color=args.stroke_color, stroke_width=args.stroke_width,
                  shadow=args.shadow, rotation=args.rotation, jitter=args.jitter, arc=args.arc,
                  soften=args.soften, grain=args.grain, opacity=args.opacity,
                  free_size=args.free_size, bubble_size=args.bubble_size,
                  bubble_min_size=args.bubble_min_size, margin=args.margin,
                  seed=args.seed)
    image, info = letter(Image.open(args.src), args.text.replace("\\n", "\n"), mode=args.mode,
                         placement=args.placement, style=style, erase=not args.no_erase,
                         white_threshold=args.white_threshold)
    image.save(args.dst)
    print(info)


if __name__ == "__main__":
    main()
