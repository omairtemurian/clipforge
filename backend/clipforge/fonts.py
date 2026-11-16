"""The fonts that captions use, bundled in assets/fonts with their licenses.

Render burns captions in with libass (ffmpeg's subtitles filter with fontsdir
FONTS_DIR). libass selects the font of an ASS style or \\fn tag by family
name (name ID 1), or else by full name (name ID 4), reading the Windows
records of each font's name table (libass ass_fontselect.c), so caption
templates name their font one of these ways: "Montserrat ExtraBold" is a
family, "Inter Bold" the full name of the bold font of the family "Inter".

Fonts the owner uploads (SPEC-v2 3.4) are kept in {data_dir}/fonts. libass
reads one fonts directory only, so while there are uploads render uses
{data_dir}/fonts-render, which links the bundled and the uploaded fonts
(render_fonts_dir).

Text in a script that a caption's font lacks (Persian, Arabic or Hebrew in
Montserrat or Inter) is drawn in a bundled font of that script
(covering_font): libass would otherwise pick any system font that has the
glyphs (fontconfig or Core Text), which differs from machine to machine.
"""

import functools
import hashlib
import os
import struct
import unicodedata
from pathlib import Path

from fontTools.ttLib import TTFont, TTLibError

from clipforge import config

FONTS_DIR = Path(__file__).resolve().parents[2] / "assets" / "fonts"
FONT_SUFFIXES = (".ttf", ".otf")
USER_FONTS_DIRNAME = "fonts"
RENDER_FONTS_DIRNAME = "fonts-render"
MAX_FONT_BYTES = 20 * 1024 * 1024
TRUETYPE_OUTLINES = "\x00\x01\x00\x00"
CFF_OUTLINES = "OTTO"
REQUIRED_TABLES = ("head", "hhea", "hmtx", "maxp", "name", "cmap")
OUTLINE_TABLES = ("glyf", "CFF ", "CFF2")
# libass draws glyph outlines only and finds no fallback font for emoji, so
# captions switch to this monochrome emoji font to draw them.
EMOJI_FONT = "Noto Emoji"
# Bundled fonts for the scripts the caption templates' fonts lack, in order
# of preference: Arabic script (Persian, Arabic, Urdu) and Hebrew.
SCRIPT_FONTS = ("Vazirmatn Bold", "Noto Sans Hebrew Bold")
# Unicode categories of characters that draw no glyph of the font: spaces,
# controls and format characters (joiners, direction marks).
NO_GLYPH_CATEGORIES = ("Zs", "Zl", "Zp", "Cc", "Cf")

WINDOWS_PLATFORM = 3
FAMILY_NAME = 1
FULL_NAME = 4


def font_names(path: Path) -> set[str]:
    """Return the names libass can select the font in path by: the family
    and full names of the Windows records of its name table."""
    with TTFont(path, lazy=True) as font:
        names: set[str] = {
            record.toUnicode()
            for record in font["name"].names
            if record.platformID == WINDOWS_PLATFORM
            and record.nameID in (FAMILY_NAME, FULL_NAME)
        }
    return names


def bundled_fonts(fonts_dir: Path = FONTS_DIR) -> dict[str, Path]:
    """Map each name of the font files in fonts_dir to its file.

    A name that several files share maps to the first of them by file name.
    """
    fonts: dict[str, Path] = {}
    for path in sorted(fonts_dir.iterdir()):
        if path.suffix.lower() in FONT_SUFFIXES:
            for name in sorted(font_names(path)):
                fonts.setdefault(name, path)
    return fonts


class FontError(ValueError):
    """An uploaded file is not a usable font."""


class FontConflictError(FontError):
    """An uploaded font has a name that another font already has."""


def user_fonts_dir() -> Path:
    """Return the directory of the uploaded fonts."""
    return config.settings.data_dir / USER_FONTS_DIRNAME


def user_fonts() -> dict[str, Path]:
    """Map each name of the uploaded fonts to its file (bundled_fonts for
    the directory of the uploads, which may not exist yet)."""
    directory = user_fonts_dir()
    return bundled_fonts(directory) if directory.is_dir() else {}


def available_fonts() -> dict[str, Path]:
    """Map each name a caption style or brand template can use as its font
    to the font file: the bundled fonts, then the uploaded ones."""
    return {**user_fonts(), **bundled_fonts()}


def check_font(path: Path) -> set[str]:
    """Return the names libass can select the font in path by.

    The tables of the font are parsed (fontTools): a TrueType or OpenType
    (CFF) font has the tables every font needs, outlines, a character map
    with glyphs and a Windows family name. Raises FontError if not.
    """
    try:
        with TTFont(path, lazy=True) as font:
            if font.sfntVersion not in (TRUETYPE_OUTLINES, CFF_OUTLINES):
                raise FontError("not a TrueType or OpenType font")
            missing = [t.strip() for t in REQUIRED_TABLES if t not in font]
            if missing:
                raise FontError(f"the font has no {', '.join(missing)} table")
            if not any(table in font for table in OUTLINE_TABLES):
                raise FontError("the font has no outlines (glyf or CFF table)")
            if font["maxp"].numGlyphs < 1 or not font.getBestCmap():
                raise FontError("the font has no characters")
            names = font_names(path)
    except FontError:
        raise
    except (TTLibError, OSError, EOFError, struct.error, KeyError, ValueError,
            AssertionError, AttributeError, IndexError) as exc:  # fmt: skip
        raise FontError(f"the font tables cannot be read ({exc})") from exc
    if not names:
        raise FontError("the font has no Windows family or full name")
    return names


def store_font(data: bytes) -> tuple[Path, set[str]]:
    """Validate the font file data and store it in the uploaded fonts.

    The file is named by a hash of its bytes (the name the client gave is
    never used as a path) with .otf for CFF outlines, else .ttf. Returns
    the file and the names of the font. Raises FontError if data is empty,
    over MAX_FONT_BYTES or not a usable font, FontConflictError if a font
    already has one of its names; nothing is stored then.
    """
    if not data:
        raise FontError("the file is empty")
    if len(data) > MAX_FONT_BYTES:
        raise FontError(f"the file is over {MAX_FONT_BYTES // (1024 * 1024)} MB")
    directory = user_fonts_dir()
    directory.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha256(data).hexdigest()[:16]
    suffix = ".otf" if data[:4] == b"OTTO" else ".ttf"
    target = directory / f"{digest}{suffix}"
    staged = directory / f".upload-{digest}.tmp"
    staged.write_bytes(data)
    try:
        names = check_font(staged)
        taken = sorted(names & available_fonts().keys())
        if taken:
            raise FontConflictError(f"a font is already called {', '.join(taken)}")
        os.replace(staged, target)
    finally:
        staged.unlink(missing_ok=True)
    return target, names


def render_fonts_dir() -> Path:
    """Return the directory libass loads the fonts from: FONTS_DIR, or while
    there are uploaded fonts a directory of links to them and the bundled
    fonts, brought up to date now."""
    uploads = sorted(user_fonts().values())
    if not uploads:
        return FONTS_DIR
    wanted = {
        path.name: path.resolve()
        for path in [*sorted(FONTS_DIR.iterdir()), *uploads]
        if path.suffix.lower() in FONT_SUFFIXES
    }
    merged = config.settings.data_dir / RENDER_FONTS_DIRNAME
    merged.mkdir(parents=True, exist_ok=True)
    for link in merged.iterdir():
        if wanted.get(link.name) != link.resolve():
            link.unlink(missing_ok=True)
    for name, target in wanted.items():
        try:
            (merged / name).symlink_to(target)
        except FileExistsError:
            pass
    return merged


@functools.lru_cache(maxsize=64)
def _font_characters(path: Path, mtime_ns: int) -> frozenset[int]:
    """Return the code points that the font in path maps to glyphs (mtime_ns,
    the file's modification time, keys the cache)."""
    with TTFont(path, lazy=True) as font:
        return frozenset(font.getBestCmap() or {})


def font_characters(path: Path) -> frozenset[int]:
    """Return the code points that the font in path has glyphs for."""
    return _font_characters(path, path.stat().st_mtime_ns)


def covering_font(font: str, text: str) -> str:
    """Return the font that captions draw text in: font if it has a glyph
    for every character of text that draws one, else the font of
    SCRIPT_FONTS that has glyphs for most of the characters font lacks
    (the first on a tie). font stays if it is not an available font or if
    no script font has any of the characters it lacks."""
    fonts = available_fonts()
    path = fonts.get(font)
    if path is None:
        return font
    wanted = {
        ord(char)
        for char in text
        if unicodedata.category(char) not in NO_GLYPH_CATEGORIES
    }
    missing = wanted - font_characters(path)
    if not missing:
        return font
    best, found = font, 0
    for name in SCRIPT_FONTS:
        script = fonts.get(name)
        covered = len(missing & font_characters(script)) if script else 0
        if covered > found:
            best, found = name, covered
    return best
