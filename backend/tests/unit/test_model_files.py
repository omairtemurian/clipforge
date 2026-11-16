"""Tests of where ClipForge keeps its models and how it downloads them.

huggingface_hub.snapshot_download is replaced by a fake, so nothing is
fetched; the real download is checked by hand (see docs/progress.md), and
the slow test checks the YAMNet files that `make setup` downloaded.
"""

import hashlib
import os
from pathlib import Path
from typing import Any

import huggingface_hub
import pytest
from clipforge import model_files
from clipforge.config import Settings
from clipforge.model_files import (
    WHISPER_PATTERNS,
    WHISPER_REQUIRED,
    YAMNET_REVISION,
    YAMNET_SHA256,
    download_whisper_model,
    download_yamnet_model,
    file_sha256,
    missing_whisper_files,
    missing_yamnet_files,
    use_project_hf_home,
    whisper_model_dir,
    whisper_repo_id,
    yamnet_model_dir,
)


class FakeSnapshotDownload:
    """Records each call, with HF_HOME, and writes files into local_dir."""

    def __init__(self) -> None:
        self.files: tuple[str, ...] = WHISPER_REQUIRED
        self.calls: list[dict[str, Any]] = []

    def __call__(self, repo_id: str, **kwargs: Any) -> str:
        self.calls.append(
            {"repo_id": repo_id, **kwargs, "HF_HOME": os.environ.get("HF_HOME")}
        )
        local_dir = Path(kwargs["local_dir"])
        local_dir.mkdir(parents=True, exist_ok=True)
        for name in self.files:
            (local_dir / name).write_text(name)
        return str(local_dir)


@pytest.fixture
def fake_download(monkeypatch: pytest.MonkeyPatch) -> FakeSnapshotDownload:
    """Replace snapshot_download with a fake, with HF_HOME unset."""
    fake = FakeSnapshotDownload()
    monkeypatch.setattr(huggingface_hub, "snapshot_download", fake)
    monkeypatch.delenv("HF_HOME", raising=False)
    return fake


@pytest.fixture
def cfg(tmp_path: Path) -> Settings:
    """Settings with the default whisper model and models in tmp_path/models."""
    return Settings(models_dir=tmp_path / "models", whisper_model="small")


@pytest.mark.parametrize(
    ("name", "dirname"),
    [
        ("small", "small"),
        ("Systran/faster-whisper-small", "Systran--faster-whisper-small"),
    ],
)
def test_each_whisper_model_has_a_directory_in_the_models_dir(
    tmp_path: Path, name: str, dirname: str
) -> None:
    cfg = Settings(models_dir=tmp_path, whisper_model=name)
    assert whisper_model_dir(cfg) == tmp_path / "whisper" / dirname


@pytest.mark.parametrize(
    ("name", "repo_id"),
    [
        ("small", "Systran/faster-whisper-small"),
        ("large-v3", "Systran/faster-whisper-large-v3"),
        ("me/my-whisper", "me/my-whisper"),
    ],
)
def test_whisper_model_names_map_to_hub_repos(name: str, repo_id: str) -> None:
    assert whisper_repo_id(name) == repo_id


def test_unknown_whisper_model_is_an_error() -> None:
    with pytest.raises(ValueError, match="unknown whisper model 'smal'; .* small,"):
        whisper_repo_id("smal")


def test_download_writes_the_model_files_into_the_models_dir(
    fake_download: FakeSnapshotDownload, cfg: Settings
) -> None:
    target = download_whisper_model(cfg)

    assert target == cfg.models_dir / "whisper" / "small"
    assert missing_whisper_files(target) == []
    assert fake_download.calls == [
        {
            "repo_id": "Systran/faster-whisper-small",
            "local_dir": target,
            "allow_patterns": WHISPER_PATTERNS,
            "force_download": False,
            "HF_HOME": str((cfg.models_dir / "huggingface").absolute()),
        }
    ]


def test_model_that_is_there_is_downloaded_again_only_when_forced(
    fake_download: FakeSnapshotDownload, cfg: Settings
) -> None:
    download_whisper_model(cfg)
    download_whisper_model(cfg)
    download_whisper_model(cfg, force=True)
    assert [call["force_download"] for call in fake_download.calls] == [False, True]


def test_repo_without_the_model_files_is_an_error(
    fake_download: FakeSnapshotDownload, tmp_path: Path
) -> None:
    fake_download.files = ("config.json",)
    cfg = Settings(models_dir=tmp_path, whisper_model="me/not-whisper")
    with pytest.raises(
        RuntimeError, match="^me/not-whisper has no model.bin, tokenizer.json: not a"
    ):
        download_whisper_model(cfg)


def test_hf_home_that_is_set_is_kept(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, cfg: Settings
) -> None:
    monkeypatch.setenv("HF_HOME", str(tmp_path / "hf"))
    assert use_project_hf_home(cfg) == tmp_path / "hf"
    assert os.environ["HF_HOME"] == str(tmp_path / "hf")


def sha256_of(text: str) -> str:
    """Return the SHA-256 of text, as the fake download writes it."""
    return hashlib.sha256(text.encode()).hexdigest()


@pytest.fixture
def fake_yamnet(
    fake_download: FakeSnapshotDownload, monkeypatch: pytest.MonkeyPatch
) -> FakeSnapshotDownload:
    """The fake writes the YAMNet files, with the sha256s that are expected."""
    fake_download.files = tuple(YAMNET_SHA256)
    expected = {name: sha256_of(name) for name in YAMNET_SHA256}
    monkeypatch.setattr(model_files, "YAMNET_SHA256", expected)
    return fake_download


def test_yamnet_is_downloaded_from_a_pinned_revision(
    fake_yamnet: FakeSnapshotDownload, cfg: Settings
) -> None:
    target = download_yamnet_model(cfg)

    assert target == cfg.models_dir / "yamnet"
    assert missing_yamnet_files(target) == []
    assert fake_yamnet.calls == [
        {
            "repo_id": "audiomagic/yamnet-onnx",
            "revision": YAMNET_REVISION,
            "local_dir": target,
            "allow_patterns": ["yamnet.onnx", "yamnet_class_map.csv"],
            "force_download": False,
            "HF_HOME": str((cfg.models_dir / "huggingface").absolute()),
        }
    ]


def test_yamnet_that_is_there_is_downloaded_again_only_when_forced(
    fake_yamnet: FakeSnapshotDownload, cfg: Settings
) -> None:
    download_yamnet_model(cfg)
    download_yamnet_model(cfg)
    download_yamnet_model(cfg, force=True)
    assert [call["force_download"] for call in fake_yamnet.calls] == [False, True]


def test_yamnet_files_with_other_sha256s_are_deleted_and_an_error(
    fake_download: FakeSnapshotDownload, cfg: Settings
) -> None:
    fake_download.files = tuple(YAMNET_SHA256)
    with pytest.raises(RuntimeError) as error:
        download_yamnet_model(cfg)
    assert str(error.value) == (
        f"audiomagic/yamnet-onnx@{YAMNET_REVISION} "
        + "; ".join(
            f"{name}: sha256 is {sha256_of(name)}, expected {expected}"
            for name, expected in YAMNET_SHA256.items()
        )
    )
    assert missing_yamnet_files(yamnet_model_dir(cfg)) == list(YAMNET_SHA256)


def test_yamnet_repo_without_a_file_is_an_error(
    fake_yamnet: FakeSnapshotDownload, cfg: Settings
) -> None:
    fake_yamnet.files = ("yamnet.onnx",)
    with pytest.raises(RuntimeError, match="yamnet_class_map.csv: sha256 is missing"):
        download_yamnet_model(cfg)


@pytest.mark.slow
def test_downloaded_yamnet_files_have_the_pinned_sha256s(
    yamnet_cfg: Settings,
) -> None:
    model_dir = yamnet_model_dir(yamnet_cfg)
    assert {name: file_sha256(model_dir / name) for name in YAMNET_SHA256} == (
        YAMNET_SHA256
    )
