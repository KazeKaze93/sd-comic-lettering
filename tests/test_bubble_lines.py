"""Line breaks typed by hand ("|") and a font size of its own ("[6]") for one bubble.

Run from the repository folder:  python -m pytest tests

The repository has no rendering test harness, so the regression test compares pixels with
PNG files kept in tests/golden. They were written by the code as it was before these two
features and hold what "unchanged" means. With the Pillow that drew them (GOLDEN_PILLOW) the
match is exact. Another Pillow may draw glyphs a fraction of a pixel away, so there the
pictures are compared blurred, within DRIFT_TOLERANCE: a Pillow upgrade does not fail the
test, a changed size or line break still does. To draw them again, check out the commit
before this feature, run with SDCL_UPDATE_GOLDEN=1, set GOLDEN_PILLOW and come back.
"""
import os
import sys
from typing import Dict, List, Tuple

import numpy as np
import PIL
import pytest
from PIL import Image, ImageChops, ImageDraw, ImageFilter

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from comic_lettering import Style, arrange, draw, letter  # noqa: E402
from comic_lettering.core import _Line  # noqa: E402

GOLDEN_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "golden")
UPDATE_GOLDEN = os.environ.get("SDCL_UPDATE_GOLDEN") == "1"
# The Pillow that drew tests/golden. With it the pictures must match to the pixel; with any
# other, to within what a glyph drawn a fraction of a pixel away can change.
GOLDEN_PILLOW = "12.2.0"
DRIFT_BLUR = 2.0      # radius of the blur both pictures get before they are compared, in pixels
# The largest difference left after the blur, of 255. Measured on these pages: the whole
# picture moved by a pixel each way leaves 68, a bubble font half a percent of the image
# height smaller, or a line broken elsewhere, leaves 130 and more.
DRIFT_TOLERANCE = 90
SMALL_SIZE = 2.0      # % of image height: a size no test line gets unless it asks for it

PAGE_SIZE = (672, 864)
PAGE_COLOR = (150, 140, 130)
BUBBLE_FILL = (255, 255, 255)
BUBBLE_OUTLINE = (0, 0, 0)
OUTLINE_WIDTH = 4
# Three bubbles, in reading order: a wide one, a tall narrow one beside it, a wide one below.
WIDE_BUBBLE = (40, 50, 330, 250)
TALL_BUBBLE = (440, 40, 620, 470)
LOW_BUBBLE = (60, 520, 420, 800)
BUBBLES = [WIDE_BUBBLE, TALL_BUBBLE, LOW_BUBBLE]
TALL = BUBBLES.index(TALL_BUBBLE)
PAD = 6  # pixels around a bubble's box that still belong to it when two pictures are compared

HEART = u"♥"
BROKEN_LINE = u"Go on,|ask nicely.|I might flex " + HEART
# Texts in the syntax of before: none has "|" or starts with "[".
OLD_TEXTS = {
    "plain": dict(text=u"Hi there!\nWhat are you looking at?\nNothing at all, really."),
    "marks": dict(text=u"Oh *no*! " + HEART + u"\nH-m-m... well <3\nUnbelievable, isn't it?"),
    "skipped": dict(text=u"\nGo on, ask nicely. I might flex " + HEART),
    "no_spill": dict(text=u"One\nA rather long line that has to be squeezed into the tall narrow bubble\nThree",
                     spill=False),
    "caption": dict(text=u"Hello\n\nBye", caption=u"Later that day...", placement="top"),
}


def page():
    # type: () -> Image.Image
    """A flat page with three empty speech bubbles on it."""
    image = Image.new("RGB", PAGE_SIZE, PAGE_COLOR)
    pen = ImageDraw.Draw(image)
    for box in BUBBLES:
        pen.ellipse(box, fill=BUBBLE_FILL, outline=BUBBLE_OUTLINE, width=OUTLINE_WIDTH)
    return image


def bubble_items(scene):
    # type: (Dict) -> Dict[int, Dict]
    """The scene's bubble items by the index of their bubble."""
    return dict((item["bubble"], item) for item in scene["items"] if item["kind"] == "bubble")


def line_texts(item):
    # type: (Dict) -> List[str]
    """The lines of a scene item as they read."""
    return [" ".join(word[0] for word in words) for words, _ in item["lines"]]


def around(box):
    # type: (Tuple[int, int, int, int]) -> Tuple[int, int, int, int]
    return (box[0] - PAD, box[1] - PAD, box[2] + PAD, box[3] + PAD)


def same_pixels(first, second, box):
    # type: (Image.Image, Image.Image, Tuple[int, int, int, int]) -> bool
    return bool((np.asarray(first.crop(box)) == np.asarray(second.crop(box))).all())


def blurred_difference(first, second):
    # type: (Image.Image, Image.Image) -> int
    """The largest difference in brightness between two pictures once both are blurred."""
    def soft(image):
        # type: (Image.Image) -> np.ndarray
        return np.asarray(image.convert("L").filter(ImageFilter.GaussianBlur(DRIFT_BLUR))).astype(np.int16)

    return int(np.abs(soft(first) - soft(second)).max())


def test_page_has_three_bubbles_in_reading_order():
    # type: () -> None
    scene = arrange(page(), numbers=True)
    assert len(scene["bubbles"]) == len(BUBBLES)
    for found, drawn in zip(scene["bubbles"], BUBBLES):
        assert abs(found[0] - drawn[0]) <= 2 * OUTLINE_WIDTH and abs(found[1] - drawn[1]) <= 2 * OUTLINE_WIDTH


@pytest.mark.parametrize("name", sorted(OLD_TEXTS))
def test_old_texts_render_as_before(name):
    # type: (str) -> None
    result, _ = letter(page(), **OLD_TEXTS[name])
    path = os.path.join(GOLDEN_DIR, name + ".png")
    if UPDATE_GOLDEN:
        os.makedirs(GOLDEN_DIR, exist_ok=True)
        result.save(path)
    golden = Image.open(path).convert("RGB")
    assert result.size == golden.size
    if PIL.__version__ == GOLDEN_PILLOW:
        differing = int((np.asarray(result) != np.asarray(golden)).any(axis=2).sum())
        assert differing == 0, "%d pixels differ from %s" % (differing, path)
    else:
        # Another Pillow may draw the same glyphs a fraction of a pixel away: compare the
        # pictures blurred, where that is small and a changed size or line break is not.
        drift = blurred_difference(result, golden)
        assert drift <= DRIFT_TOLERANCE, (
            "%s differs from %s by %d of 255 after blurring (allowed: %d). The reference was drawn with Pillow %s, "
            "this is Pillow %s." % (name, path, drift, DRIFT_TOLERANCE, GOLDEN_PILLOW, PIL.__version__))


def test_the_tolerance_tells_drift_from_a_changed_layout():
    # type: () -> None
    """What the comparison for another Pillow lets through, and what it does not."""
    golden = Image.open(os.path.join(GOLDEN_DIR, "plain.png")).convert("RGB")
    shifted = ImageChops.offset(golden, 1, 1)  # everything one pixel off: more than glyph drift ever is
    assert blurred_difference(golden, shifted) <= DRIFT_TOLERANCE
    smaller = Style()
    smaller.bubble_size -= 1.0
    changed, _ = letter(page(), style=smaller, **OLD_TEXTS["plain"])
    assert blurred_difference(golden, changed) > DRIFT_TOLERANCE


@pytest.mark.parametrize("line", [u"[sigh] Not again.", u"[6 apples] left", u"[] empty", u"[x2] twice", u"Wait [6] here"])
def test_brackets_without_a_size_stay_text(line):
    # type: (str) -> None
    assert _Line(line).size is None
    assert _Line(line).wrapped == line
    scene = arrange(page(), line)
    item = bubble_items(scene)[0]
    assert u" ".join(line_texts(item)) == line.upper()
    # It is fitted as any text is: a size of its own would have held it at that size.
    assert item["size"] > int(SMALL_SIZE / 100.0 * PAGE_SIZE[1])
    assert bubble_items(arrange(page(), u"[%g]%s" % (SMALL_SIZE, line)))[0]["size"] == int(SMALL_SIZE / 100.0 * PAGE_SIZE[1])


def test_old_texts_give_no_warnings():
    # type: () -> None
    for name in sorted(OLD_TEXTS):
        _, info = letter(page(), **OLD_TEXTS[name])
        assert info["warnings"] == [], name


def test_breaks_typed_by_hand_are_kept():
    # type: () -> None
    image = page()
    scene = arrange(image, u"\n" + BROKEN_LINE)
    item = bubble_items(scene)[TALL]
    assert line_texts(item) == [u"GO ON,", u"ASK NICELY.", u"I MIGHT FLEX " + HEART]
    assert item["text"] == BROKEN_LINE  # the editor finds the line's bubble by this text
    assert scene["info"]["warnings"] == []
    # Left to itself the same text is broken elsewhere: these breaks are the typed ones.
    automatic = bubble_items(arrange(image, u"\n" + BROKEN_LINE.replace(u"|", u" ")))[TALL]
    assert line_texts(automatic) != line_texts(item)
    # Nothing of the text is outside the bubble's box.
    result = draw(image, scene)
    assert same_pixels(result, image, (0, 0, TALL_BUBBLE[0] - PAD, PAGE_SIZE[1]))
    assert not same_pixels(result, image, around(TALL_BUBBLE))


def test_breaks_that_do_not_fit_fall_back_with_a_warning():
    # type: () -> None
    line = u"Unbelievably long words|sesquipedalian circumlocution everywhere"
    scene = arrange(page(), u"\n" + line)
    item = bubble_items(scene)[TALL]
    assert len(item["lines"]) > line.count(u"|") + 1  # wrapped automatically, not as typed
    assert len(scene["info"]["warnings"]) == 1
    assert "Bubble %d" % (TALL + 1) in scene["info"]["warnings"][0]
    # The same picture as the line without its breaks: the fallback is the automatic wrap.
    plain = arrange(page(), u"\n" + line.replace(u"|", u" "))
    assert line_texts(bubble_items(plain)[TALL]) == line_texts(item)
    assert plain["info"]["warnings"] == []


def test_size_of_one_bubble_leaves_the_others_alone():
    # type: () -> None
    image = page()
    lines = [u"Hi there!", u"Yes?", u"Nothing at all, really."]
    size = 3.0  # % of image height, well under what "Yes?" gets by itself
    sized = list(lines)
    sized[TALL] = u"[%g]%s" % (size, lines[TALL])
    before_scene, after_scene = arrange(image, u"\n".join(lines)), arrange(image, u"\n".join(sized))
    before, after = draw(image, before_scene), draw(image, after_scene)
    items_before, items_after = bubble_items(before_scene), bubble_items(after_scene)
    limit = int(size / 100.0 * PAGE_SIZE[1])
    assert items_before[TALL]["size"] > limit
    assert items_after[TALL]["size"] == limit
    assert line_texts(items_after[TALL]) == [u"YES?"]  # the mark itself is not drawn
    for index, box in enumerate(BUBBLES):
        if index == TALL:
            assert not same_pixels(before, after, around(box))
        else:
            assert items_before[index] == items_after[index]
            assert same_pixels(before, after, around(box))
    # Outside the sized bubble not one pixel moved.
    outside = np.ones((PAGE_SIZE[1], PAGE_SIZE[0]), dtype=bool)
    x0, y0, x1, y1 = around(TALL_BUBBLE)
    outside[y0:y1, x0:x1] = False
    assert not (np.asarray(before) != np.asarray(after)).any(axis=2)[outside].any()


def test_a_sized_line_is_not_sent_to_the_caption():
    # type: () -> None
    style = Style()
    readable = int(round(style.bubble_min_size / 100.0 * PAGE_SIZE[1]))
    # Too much for the tall bubble at a readable size, and the only line, so it tries every bubble.
    line = u"A rather long line that has to be squeezed into the tall narrow bubble, " * 3
    blocked = dict((index, u"x") for index in range(len(BUBBLES)) if index != TALL)

    def letter_tall(text):
        # type: (str) -> Dict
        lines = [blocked.get(index, text) for index in range(len(BUBBLES))]
        return arrange(page(), u"\n".join(lines), style=style, placement="top")

    plain = letter_tall(line.strip())
    assert TALL not in bubble_items(plain)
    assert plain["info"]["free_text"]
    sized = letter_tall(u"[%g]%s" % (style.bubble_size, line.strip()))
    assert bubble_items(sized)[TALL]["size"] < readable
    assert not sized["info"]["free_text"]


def test_a_line_sent_to_the_caption_keeps_its_breaks():
    # type: () -> None
    words = u"this line is far too long for any bubble on the page " * 12
    scene = arrange(page(), words.strip() + u"|and has a break", placement="top")
    captions = [item for item in scene["items"] if item["kind"] == "caption"]
    assert len(captions) == 1
    assert u"|" not in captions[0]["text"]
    assert captions[0]["text"].endswith(u"\nand has a break")
