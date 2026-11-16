"""scripts/check_prereqs.py: credential names only, never values."""

import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / "scripts" / "check_prereqs.py"
SECRET = "s3cr3t-value-that-must-not-print"


def run_script(env: dict[str, str], tmp: Path) -> subprocess.CompletedProcess[str]:
    """Run a copy of the script under tmp, so it reads no real .env files, with
    only PATH and env in its environment."""
    (tmp / "scripts").mkdir()
    script = tmp / "scripts" / SCRIPT.name
    script.write_text(SCRIPT.read_text())
    return subprocess.run(
        [sys.executable, str(script)],
        capture_output=True,
        text=True,
        env={"PATH": os.environ["PATH"], **env},
        check=False,
    )


def env_example_names() -> set[str]:
    return set(re.findall(r"^([A-Z0-9_]+)=", (ROOT / ".env.example").read_text(), re.M))


def listed_names(stdout: str) -> list[str]:
    return [line.split(":")[0] for line in stdout.splitlines() if ": " in line]


def test_prints_present_and_missing_by_name_and_exits_zero(tmp_path: Path) -> None:
    result = run_script({"PEXELS_API_KEY": SECRET, "SMTP_HOST": ""}, tmp_path)
    assert result.returncode == 0
    assert "PEXELS_API_KEY: present" in result.stdout
    assert "SMTP_HOST: missing" in result.stdout
    assert SECRET not in result.stdout + result.stderr


def test_lists_every_v2_credential_of_env_example(tmp_path: Path) -> None:
    result = run_script({}, tmp_path)
    v2 = env_example_names() - {
        "LLM_PROVIDER",
        "GITHUB_COPILOT_TOKEN",
        "COPILOT_ACCOUNT",
        "ANTHROPIC_API_KEY",
        "ANTHROPIC_BASE_URL",
        "ANTHROPIC_MODEL",
        "CLAUDE_CODE_BIN",
        "CLAUDE_CODE_MODEL",
        "DEEP_FILTER_BIN",
        "PIPER_BIN",
        "OPENAI_API_KEY",
        "OPENAI_BASE_URL",
        "LLM_MODEL",
        "OLLAMA_HOST",
        "VLM_MODEL",
        "FFMPEG_BIN",
        "FFPROBE_BIN",
        "VIDEO_ENCODER",
        "YTDLP_COOKIES_FROM_BROWSER",
        "YTDLP_COOKIES_FILE",
    }
    assert len(v2) == 25
    assert set(listed_names(result.stdout)) >= v2


def test_reads_env_local_of_the_repo(tmp_path: Path) -> None:
    sys.path.insert(0, str(ROOT / "scripts"))
    try:
        import check_prereqs
    finally:
        sys.path.remove(str(ROOT / "scripts"))
    (tmp_path / ".env.local").write_text(f"X_CLIENT_ID={SECRET}\nX_CLIENT_SECRET=\n")
    values = check_prereqs.load_values(tmp_path, {"HF_TOKEN": "abc"})
    lines = check_prereqs.status_lines(values)
    assert "X_CLIENT_ID: present" in lines
    assert "X_CLIENT_SECRET: missing" in lines
    assert "HF_TOKEN: present" in lines
