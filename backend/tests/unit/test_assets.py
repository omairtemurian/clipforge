"""Tests for the asset library helpers (clipforge.assets)."""

import shutil
from collections.abc import Iterator
from pathlib import Path

import pytest
from clipforge.assets import (
    AssetNotFoundError,
    add_asset,
    delete_asset,
    get_asset,
    list_assets,
    register_bundled_fonts,
    update_asset,
)
from clipforge.db import init_db
from clipforge.fonts import FONTS_DIR
from pydantic import ValidationError
from sqlalchemy import Engine
from sqlmodel import Session


@pytest.fixture
def session(engine: Engine) -> Iterator[Session]:
    """A session on a migrated database."""
    with Session(engine) as opened:
        yield opened


def test_add_asset_returns_it_with_an_id_and_stores_every_field(
    session: Session,
) -> None:
    added = add_asset(
        session,
        "music",
        "assets/music/calm.mp3",
        "CC-BY-4.0",
        attribution="Calm by Ada",
        source_url="https://example.com/calm",
        tags=["calm", "loop"],
    )

    assert added.id == 1
    assert get_asset(session, added.id) == added
    assert (added.kind, added.path, added.license) == (
        "music",
        "assets/music/calm.mp3",
        "CC-BY-4.0",
    )
    assert added.attribution == "Calm by Ada"
    assert added.source_url == "https://example.com/calm"
    assert added.tags == ["calm", "loop"]


def test_asset_defaults_to_no_attribution_url_or_tags(session: Session) -> None:
    added = add_asset(session, "sfx", "whoosh.wav", "CC0")

    assert (added.attribution, added.source_url, added.tags) == ("", None, [])


@pytest.mark.parametrize(
    ("kind", "path", "license"),
    [
        ("gif", "a.gif", "CC0"),
        ("image", "", "CC0"),
        ("image", "a.png", ""),
    ],
)
def test_add_asset_rejects_invalid_values_and_adds_nothing(
    session: Session, kind: str, path: str, license: str
) -> None:
    with pytest.raises(ValidationError):
        add_asset(session, kind, path, license)  # type: ignore[arg-type]

    assert list_assets(session) == []


def test_every_asset_kind_is_accepted(session: Session) -> None:
    kinds = ["video", "image", "audio", "font", "logo", "music", "sfx"]
    for kind in kinds:
        add_asset(session, kind, f"{kind}.bin", "CC0")  # type: ignore[arg-type]

    assert [a.kind for a in list_assets(session)] == kinds


def test_list_assets_filters_by_kind_and_tag_in_id_order(session: Session) -> None:
    add_asset(session, "logo", "a.png", "CC0", tags=["brand"])
    add_asset(session, "music", "b.mp3", "CC0", tags=["brand", "calm"])
    add_asset(session, "logo", "c.png", "CC0")

    assert [a.path for a in list_assets(session, kind="logo")] == ["a.png", "c.png"]
    assert [a.path for a in list_assets(session, tag="brand")] == ["a.png", "b.mp3"]
    assert [a.path for a in list_assets(session, kind="logo", tag="brand")] == ["a.png"]
    assert list_assets(session, kind="font") == []


def test_get_asset_returns_none_for_an_unknown_id(session: Session) -> None:
    assert get_asset(session, 99) is None


def test_update_asset_changes_only_the_given_fields(session: Session) -> None:
    added = add_asset(session, "image", "a.png", "CC0", tags=["x"])

    updated = update_asset(session, added.id, license="CC-BY-4.0", tags=["y", "z"])

    assert updated == added.model_copy(
        update={"license": "CC-BY-4.0", "tags": ["y", "z"]}
    )
    assert get_asset(session, added.id) == updated


def test_update_asset_rejects_bad_changes_and_keeps_the_asset(
    session: Session,
) -> None:
    added = add_asset(session, "image", "a.png", "CC0")

    with pytest.raises(ValidationError):
        update_asset(session, added.id, kind="gif")
    with pytest.raises(ValidationError):
        update_asset(session, added.id, license="")
    with pytest.raises(TypeError, match="id"):
        update_asset(session, added.id, id=5)
    with pytest.raises(TypeError, match="colour"):
        update_asset(session, added.id, colour="red")
    with pytest.raises(AssetNotFoundError):
        update_asset(session, 99, license="CC0")

    assert get_asset(session, added.id) == added


def test_delete_asset_removes_it(session: Session) -> None:
    first = add_asset(session, "image", "a.png", "CC0")
    second = add_asset(session, "image", "b.png", "CC0")

    delete_asset(session, first.id)

    assert list_assets(session) == [second]
    with pytest.raises(AssetNotFoundError):
        delete_asset(session, first.id)


def test_bundled_fonts_are_registered_with_their_license(session: Session) -> None:
    added = register_bundled_fonts(session)

    files = sorted(p.name for p in FONTS_DIR.glob("*.ttf"))
    assert [Path(a.path).name for a in added] == files
    fonts = list_assets(session, kind="font", tag="bundled")
    assert fonts == added
    for font in fonts:
        assert font.license == "OFL-1.1"
        assert "Copyright" in font.attribution
        assert Path(font.path).is_file()


def test_registering_the_bundled_fonts_twice_changes_nothing(
    session: Session,
) -> None:
    register_bundled_fonts(session)
    before = list_assets(session)

    assert register_bundled_fonts(session) == []
    assert list_assets(session) == before


def test_a_moved_font_directory_updates_the_paths(
    session: Session, tmp_path: Path
) -> None:
    register_bundled_fonts(session)
    before = list_assets(session)
    moved = tmp_path / "fonts"
    shutil.copytree(FONTS_DIR, moved)

    changed = register_bundled_fonts(session, moved)

    after = list_assets(session)
    assert [a.id for a in after] == [a.id for a in before]
    assert {a.id for a in changed} == {a.id for a in before}
    assert all(Path(a.path).parent == moved for a in after)


def test_fonts_in_a_directory_without_font_files_register_nothing(
    session: Session, tmp_path: Path
) -> None:
    (tmp_path / "LICENSES.md").write_text("none")

    assert register_bundled_fonts(session, tmp_path) == []
    assert list_assets(session) == []


def test_init_db_registers_the_bundled_fonts_once(data_dir: Path) -> None:
    for _ in range(2):
        engine = init_db()
        with Session(engine) as session:
            fonts = list_assets(session, kind="font")
        engine.dispose()
        assert len(fonts) == len(list(FONTS_DIR.glob("*.ttf")))
