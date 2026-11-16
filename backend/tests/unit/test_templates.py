"""Checks the caption templates, the bundled fonts and the emoji map (SPEC 6.9).

The fonts' name tables are read here with fontTools directly, not through
clipforge.fonts, so that a bug there cannot hide a template font that libass
would not find. libass selects a font by the family name (name ID 1) or full
name (name ID 4) of its Windows name records.
"""

import hashlib
import re
import shutil
from collections import Counter
from pathlib import Path
from typing import Any

import pytest
import yaml
from clipforge.captions_templates import (
    EMOJI_MAP,
    TEMPLATES_DIR,
    CaptionTemplate,
    get_template,
    load_emoji_map,
    load_template,
    load_templates,
)
from clipforge.fonts import EMOJI_FONT, FONTS_DIR, bundled_fonts, font_names
from clipforge.models import ProcessingSettings
from fontTools.ttLib import TTFont

SPEC_TEMPLATES = {"karaoke_bold", "minimal", "boxed", "neon", "comic", "clean_subtitle"}
# SPEC 6.9 fields, then SPEC-v2 3.4 (stroke color, line count, animation).
SPEC_FIELDS = (
    "font size primary_color highlight_color emphasis_color outline shadow box "
    "uppercase position max_words_per_line emoji outline_color max_lines animation"
)
# Font file -> (its license file, OS/2 weight class).
FONT_FILES = {
    "Montserrat-ExtraBold.ttf": ("Montserrat-OFL.txt", 800),
    "Inter-Bold.ttf": ("Inter-OFL.txt", 700),
    "NotoEmoji-VariableFont_wght.ttf": ("NotoEmoji-OFL.txt", 400),
    "Vazirmatn-Bold.ttf": ("Vazirmatn-OFL.txt", 700),
    "NotoSansHebrew-Bold.ttf": ("NotoSansHebrew-OFL.txt", 700),
    # The Google Fonts display fonts of TASK-199.
    "Poppins-Black.ttf": ("Poppins-OFL.txt", 900),
    "Anton-Regular.ttf": ("Anton-OFL.txt", 400),
    "BebasNeue-Regular.ttf": ("BebasNeue-OFL.txt", 400),
    "Bangers-Regular.ttf": ("Bangers-OFL.txt", 400),
    "ArchivoBlack-Regular.ttf": ("ArchivoBlack-OFL.txt", 400),
    "LilitaOne-Regular.ttf": ("LilitaOne-OFL.txt", 400),
    "TitanOne-Regular.ttf": ("TitanOne-OFL.txt", 400),
    "Bungee-Regular.ttf": ("Bungee-OFL.txt", 400),
    "PassionOne-Black.ttf": ("PassionOne-OFL.txt", 900),
    "Righteous-Regular.ttf": ("Righteous-OFL.txt", 400),
    "Staatliches-Regular.ttf": ("Staatliches-OFL.txt", 400),
    "LuckiestGuy-Regular.ttf": ("LuckiestGuy-LICENSE.txt", 400),
    "PermanentMarker-Regular.ttf": ("PermanentMarker-LICENSE.txt", 400),
}
# The fonts under the Apache License 2.0; every other one is under the OFL.
APACHE_FONTS = {"LuckiestGuy-Regular.ttf", "PermanentMarker-Regular.ttf"}
NEW_FONTS = 13
EMOJI_FONT_FILE = FONTS_DIR / "NotoEmoji-VariableFont_wght.ttf"
WINDOWS, FAMILY, FULL_NAME, LICENSE = 3, 1, 4, 13
VALID: dict[str, Any] = {
    "font": "Inter Bold",
    "size": 64,
    "primary_color": "#FFFFFF",
    "highlight_color": "#FFD23F",
    "emphasis_color": "#FF6B35",
    "outline": 2.5,
    "shadow": 0,
    "box": False,
    "uppercase": True,
    "position": "bottom",
    "max_words_per_line": 4,
    "emoji": True,
}


def names(path: Path, *name_ids: int) -> set[str]:
    """Return the Windows name records of the font in path with name_ids."""
    with TTFont(path, lazy=True) as font:
        return {
            record.toUnicode()
            for record in font["name"].names
            if record.platformID == WINDOWS and record.nameID in name_ids
        }


def write(path: Path, data: object) -> Path:
    """Write data to path as YAML and return path."""
    path.write_text(yaml.safe_dump(data, allow_unicode=True), encoding="utf-8")
    return path


def test_the_spec_templates_load() -> None:
    templates = load_templates()
    assert SPEC_TEMPLATES <= set(templates)
    assert set(CaptionTemplate.model_fields) == set(SPEC_FIELDS.split())
    for name in SPEC_TEMPLATES:
        assert 3 <= templates[name].max_words_per_line <= 4
    default = ProcessingSettings.model_fields["caption_template"].default
    assert default in templates


def test_get_template_returns_a_template_by_name() -> None:
    assert get_template("boxed") == load_templates()["boxed"]
    assert get_template("boxed").box


def test_get_template_lists_the_templates_for_an_unknown_name() -> None:
    with pytest.raises(ValueError, match="'fancy'.*boxed, clean_subtitle, comic"):
        get_template("fancy")


def test_each_template_font_names_one_bundled_font_file() -> None:
    font_files = {
        file: names(FONTS_DIR / file, FAMILY, FULL_NAME) for file in FONT_FILES
    }
    used = set()
    for name, template in load_templates().items():
        matches = [file for file, found in font_files.items() if template.font in found]
        assert len(matches) == 1, (name, template.font, matches)
        used.add(template.font)
    assert {"Montserrat ExtraBold", "Inter Bold"} <= used


def test_the_fonts_are_the_weights_the_templates_name() -> None:
    assert names(FONTS_DIR / "Montserrat-ExtraBold.ttf", FAMILY) == {
        "Montserrat ExtraBold"
    }
    assert names(FONTS_DIR / "Inter-Bold.ttf", FAMILY) == {"Inter"}
    assert names(FONTS_DIR / "Inter-Bold.ttf", FULL_NAME) == {"Inter Bold"}
    for file, (_, weight) in FONT_FILES.items():
        with TTFont(FONTS_DIR / file, lazy=True) as font:
            assert font["OS/2"].usWeightClass == weight, file


def test_every_font_file_is_open_licensed_and_listed() -> None:
    licenses = (FONTS_DIR / "LICENSES.md").read_text(encoding="utf-8")
    files = {p.name for p in FONTS_DIR.iterdir() if p.suffix in (".ttf", ".otf")}
    assert files == set(FONT_FILES)
    for file, (license_file, _) in FONT_FILES.items():
        text = (FONTS_DIR / license_file).read_text(encoding="utf-8")
        if file in APACHE_FONTS:
            assert "Apache License" in text, license_file
            assert "Version 2.0, January 2004" in text, license_file
        else:
            notice = " ".join(next(iter(names(FONTS_DIR / file, LICENSE))).split())
            assert "SIL Open Font License, Version 1.1" in notice, file
            assert "SIL OPEN FONT LICENSE Version 1.1" in text, license_file
        assert license_file in licenses


def test_every_font_file_has_its_own_row_in_licenses_md() -> None:
    """A font file is a "## file" section or a table row of LICENSES.md that
    also names its license file and SHA-256."""
    lines = (FONTS_DIR / "LICENSES.md").read_text(encoding="utf-8").splitlines()
    for path in sorted(FONTS_DIR.iterdir()):
        if path.suffix not in (".ttf", ".otf"):
            continue
        section = f"## {path.name}"
        row = [line for line in lines if line.startswith(f"| `{path.name}` |")]
        assert section in lines or len(row) == 1, f"{path.name} has no LICENSES.md row"
        license_file = FONT_FILES[path.name][0]
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        if row:
            assert license_file in row[0] and digest in row[0], path.name


def test_the_new_fonts_come_to_at_least_ten_open_licensed_files() -> None:
    assert len(FONT_FILES) - 5 == NEW_FONTS >= 10


def test_bundled_fonts_maps_family_and_full_names_to_files() -> None:
    fonts = bundled_fonts()
    assert fonts["Montserrat ExtraBold"] == FONTS_DIR / "Montserrat-ExtraBold.ttf"
    assert fonts["Inter"] == fonts["Inter Bold"] == FONTS_DIR / "Inter-Bold.ttf"
    assert fonts[EMOJI_FONT] == EMOJI_FONT_FILE
    assert font_names(FONTS_DIR / "Inter-Bold.ttf") == {"Inter", "Inter Bold"}


def test_bundled_fonts_skips_other_files_and_keeps_the_first_file(
    tmp_path: Path,
) -> None:
    shutil.copy(FONTS_DIR / "Inter-Bold.ttf", tmp_path / "b.TTF")
    shutil.copy(FONTS_DIR / "Inter-Bold.ttf", tmp_path / "c.ttf")
    (tmp_path / "a.txt").write_text("not a font")
    assert bundled_fonts(tmp_path) == {
        "Inter": tmp_path / "b.TTF",
        "Inter Bold": tmp_path / "b.TTF",
    }


def test_load_templates_reads_every_template_but_the_emoji_map(
    tmp_path: Path,
) -> None:
    write(tmp_path / "mine.yaml", VALID)
    write(tmp_path / EMOJI_MAP, {"laugh": "😂"})
    (tmp_path / "notes.txt").write_text("not a template")
    assert load_templates(tmp_path) == {"mine": CaptionTemplate.model_validate(VALID)}


@pytest.mark.parametrize(
    "changes",
    [
        {"max_words_per_line": 0},
        {"max_words_per_line": 7},
        {"max_lines": 0},
        {"max_lines": 3},
        {"animation": "spin"},
        {"outline_color": "black"},
        {"primary_color": "#FFF"},
        {"highlight_color": "yellow"},
        {"position": "upper_third"},
        {"size": 0},
        {"outline": -1},
        {"shadow": "big"},
        {"box": "maybe"},
        {"font": ""},
        {"font": None},
        {"bold": True},
    ],
)
def test_load_template_rejects_an_invalid_template(
    tmp_path: Path, changes: dict[str, Any]
) -> None:
    data = {key: value for key, value in (VALID | changes).items() if value is not None}
    path = write(tmp_path / "bad.yaml", data)
    with pytest.raises(ValueError, match="bad.yaml is not a valid caption template"):
        load_template(path)


@pytest.mark.parametrize("text", ["", "- karaoke\n", "font: [Inter Bold\n"])
def test_load_template_rejects_a_file_without_a_template(
    tmp_path: Path, text: str
) -> None:
    path = tmp_path / "bad.yaml"
    path.write_text(text)
    with pytest.raises(ValueError, match=r"bad.yaml is not (a )?valid"):
        load_template(path)


def test_load_template_rejects_a_font_that_is_not_bundled(tmp_path: Path) -> None:
    path = write(tmp_path / "bad.yaml", VALID | {"font": "Comic Sans MS"})
    with pytest.raises(ValueError, match="font 'Comic Sans MS' is not in"):
        load_template(path)


def test_the_emoji_map_holds_lowercase_words_and_single_emoji() -> None:
    emoji = load_emoji_map()
    assert len(emoji) >= 100
    assert emoji["laugh"] == "😂"
    assert emoji["money"] == "💰"
    assert emoji["love"] == "❤\ufe0f"
    for keyword in ("think", "look", "time", "work", "okay", "yes", "no"):
        assert keyword not in emoji


def test_the_emoji_map_has_no_duplicate_keys() -> None:
    # PyYAML keeps the last of duplicate keys without a warning.
    text = (TEMPLATES_DIR / EMOJI_MAP).read_text(encoding="utf-8")
    keys = Counter(re.findall(r"(?m)^(\S+):", text))
    assert [key for key, count in keys.items() if count > 1] == []
    assert sum(keys.values()) == len(load_emoji_map())


def test_the_emoji_font_draws_every_emoji() -> None:
    assert EMOJI_FONT in names(EMOJI_FONT_FILE, FAMILY)
    with TTFont(EMOJI_FONT_FILE, lazy=True) as font:
        cmap = font.getBestCmap()
    missing = {
        keyword: emoji
        for keyword, emoji in load_emoji_map().items()
        if any(ord(char) not in cmap for char in emoji)
    }
    assert missing == {}


@pytest.mark.parametrize(
    "data",
    [
        {"Laugh": "😂"},
        {"big laugh": "😂"},
        {"laugh2": "😂"},
        {"laugh": "x"},
        {"laugh": ":)"},
        {"laugh": "😂😂"},
        {"laugh": "😂 "},
        {"family": "👨\u200d👩\u200d👧"},
        {"one": "1\ufe0f\u20e3"},
        ["😂"],
    ],
)
def test_load_emoji_map_rejects_an_invalid_map(tmp_path: Path, data: object) -> None:
    path = write(tmp_path / EMOJI_MAP, data)
    with pytest.raises(ValueError, match="is not a valid emoji map"):
        load_emoji_map(path)


def test_an_unquoted_yaml_boolean_key_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / EMOJI_MAP
    path.write_text("on: 🔛\n", encoding="utf-8")
    with pytest.raises(ValueError, match="is not a valid emoji map"):
        load_emoji_map(path)
