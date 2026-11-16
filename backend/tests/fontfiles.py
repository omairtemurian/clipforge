"""Font files for tests, built with fontTools (tests only)."""

from io import BytesIO

from clipforge.fonts import FONTS_DIR
from fontTools.fontBuilder import FontBuilder
from fontTools.pens.t2CharStringPen import T2CharStringPen
from fontTools.ttLib import TTFont

WINDOWS = (3, 1, 0x409)
FAMILY, FULL_NAME, POSTSCRIPT_NAME = 1, 4, 6


def renamed_inter(family: str) -> bytes:
    """Return the bundled Inter Bold as a TrueType font called family (its
    full name is "<family> Bold")."""
    font = TTFont(FONTS_DIR / "Inter-Bold.ttf", recalcTimestamp=False)
    names = font["name"]
    names.names = [n for n in names.names if n.nameID not in (16, 17, 21, 22)]
    names.setName(family, FAMILY, *WINDOWS)
    names.setName(f"{family} Bold", FULL_NAME, *WINDOWS)
    names.setName(family.replace(" ", "") + "-Bold", POSTSCRIPT_NAME, *WINDOWS)
    out = BytesIO()
    font.save(out)
    return out.getvalue()


def tiny_otf(family: str) -> bytes:
    """Return an OpenType font with CFF outlines called family, with one
    glyph (A) that is a square."""
    builder = FontBuilder(1000, isTTF=False)
    builder.setupGlyphOrder([".notdef", "A"])
    builder.setupCharacterMap({65: "A"})
    pen = T2CharStringPen(600, None)
    pen.moveTo((50, 0))
    pen.lineTo((550, 0))
    pen.lineTo((550, 500))
    pen.lineTo((50, 500))
    pen.closePath()
    glyph = pen.getCharString()
    ps_name = family.replace(" ", "") + "-Regular"
    builder.setupCFF(
        ps_name,
        {"FullName": f"{family} Regular"},
        dict.fromkeys([".notdef", "A"], glyph),
        {},
    )
    builder.setupHorizontalMetrics({".notdef": (600, 0), "A": (600, 0)})
    builder.setupHorizontalHeader(ascent=800, descent=-200)
    builder.setupNameTable(
        {
            "familyName": family,
            "styleName": "Regular",
            "psName": ps_name,
            "fullName": f"{family} Regular",
        }
    )
    builder.setupOS2(sTypoAscender=800, sTypoDescender=-200, usWinAscent=800)
    builder.setupPost()
    out = BytesIO()
    builder.save(out)
    return out.getvalue()
