# Stack

The project uses Python 3.11 and uv. Dependency versions below are resolved in
`uv.lock`; update this table from the lockfile when dependencies change.

| Package | Locked version |
| --- | --- |
| fastapi | 0.162.0 |
| uvicorn | 0.54.0 |
| pydantic | 2.14.2 |
| pydantic-settings | 2.16.2 |
| PyYAML | 6.0.3 |
| sqlmodel | 0.0.48 |
| sqlalchemy | 2.1.6 |
| yt-dlp | 2026.10.26 |
| ruff | 0.17.3 |
| mypy | 2.4.1 |
| pytest | 9.2.0 |
| types-yt-dlp | 2026.8.19.20261030 |
| types-PyYAML | 6.0.12.20261030 |
| fonttools | 4.68.0 |
| faster-whisper | 1.2.1 |
| ctranslate2 | 4.8.4 |
| mlx-whisper (Apple Silicon only) | 0.4.3 |
| mlx (Apple Silicon only) | 0.32.4 |
| torch (needed by mlx-whisper, Apple Silicon only) | 2.15.0 |
| huggingface-hub | 2.4.0 |
| hf-xet | 1.8.0 |
| tokenizers | 0.23.3 |
| av | 18.1.0 |
| onnxruntime | 1.31.1 |
| numpy | 2.4.6 |
| tqdm | 4.70.1 |
| librosa | 0.11.0 |
| numba | 0.68.1 |
| llvmlite | 0.50.0 |
| scipy | 1.17.1 |
| scikit-learn | 1.9.1 |
| soundfile | 0.14.0 |
| soxr | 1.1.0 |
| audioread | 3.1.0 |
| pooch | 1.9.0 |
| joblib | 1.6.0 |
| httpx | 0.28.1 |
| httpcore | 1.0.9 |
| certifi | 2026.10.23 |
| scenedetect | 0.7.2 |
| opencv-contrib-python | 5.0.0.93 |
| mediapipe | 0.10.33 |
| absl-py | 2.5.1 |
| matplotlib | 3.11.2 |
| pillow | 13.0.0 |
| sounddevice | 0.5.6 |
| cryptography | 50.0.2 |

System tools (not in the lockfile): ffmpeg/ffprobe 9.0.2 from Homebrew's
`ffmpeg-full` 9.0.2_1 (keg-only, /opt/homebrew/opt/ffmpeg-full/bin, which the
Makefile puts first on PATH; built with libass 0.17.5, `--enable-libass
--enable-libfreetype --enable-libfontconfig --enable-libharfbuzz`); GitHub
CLI `gh` 2.97.0 (the Copilot token: `gh auth token -u <COPILOT_ACCOUNT> -h
github.com`, default account <your-github-account>); Ollama 0.34.4 (optional, for LLM_PROVIDER=ollama);
Tesseract OCR 5.5.4 (Apache-2.0, Homebrew `tesseract`, leptonica 1.87.0, `eng`
+ `osd` data; optional: style learning reads burned-in captions with it,
TASK-230, and skips captions without it).

httpx (the LLM clients' HTTP) brings httpcore and certifi; its other
dependencies (anyio, idna, h11) were already locked.

cryptography 50.0.2 (TASK-138) encrypts the stored OAuth tokens (Fernet);
its only dependency, cffi 2.1.1, was already locked.

ctranslate2, huggingface-hub, hf-xet, tokenizers, av (PyAV), onnxruntime
(Silero VAD), numpy and tqdm come in with faster-whisper. Models (not in the
lockfile): faster-whisper "small" = `Systran/faster-whisper-small` on the
Hugging Face Hub, downloaded into `models/whisper/small` by
`scripts/download_models.py` (486.2 MB).

The signals (TASK-16) run YAMNet on onnxruntime and measure loudness with
librosa; onnxruntime and numpy are now direct dependencies. librosa brings
numba/llvmlite, scipy, scikit-learn (with threadpoolctl 3.7.0, narwhals
2.28.0), soundfile (cffi 2.1.1, pycparser 3.12), soxr, audioread, pooch
(requests 2.34.2, urllib3 2.8.0, charset-normalizer 3.5.2, platformdirs
4.14.0), joblib (cloudpickle 3.1.2), lazy-loader 0.6, msgpack 1.2.4 and
decorator 5.3.1. librosa 1.0 needs Python >= 3.12, so 0.11.0 is locked.
Model (not in the lockfile): YAMNet converted to ONNX,
`audiomagic/yamnet-onnx` at revision
f25b741c2f0bdc6d7e6db24b5fddda23347dbafd, downloaded into `models/yamnet`
by `scripts/download_models.py` (16.1 MB): `yamnet.onnx` (sha256
d3835ffbbd4a1bb3e777f0ca217b5007907f5171dd5d17c4236b95b2af8f908e) and
`yamnet_class_map.csv` (sha256
cdf24d193e196d9e95912a2667051ae203e92a2ba09449218ccb40ef787c6df2).

The scene cuts (TASK-17) use PySceneDetect (`scenedetect`, no py.typed),
which decodes with OpenCV (its own FFmpeg inside); its other dependencies
(click, numpy, platformdirs, tqdm) were already locked.

Reframe (TASK-22) finds faces with mediapipe 0.10.33 (pinned exactly: 0.10.35
and later log usage to Google's Clearcut, decisions.md; no py.typed), the
Tasks API wheel with a C library. It needs opencv-contrib-python, which
replaces opencv-python for PySceneDetect too (`[tool.uv]
exclude-dependencies`, both install `cv2`), absl-py, flatbuffers (already
locked), sounddevice (cffi) and matplotlib, which brings contourpy 1.3.3,
cycler 0.12.1, fonttools 4.68.0, kiwisolver 1.5.1, pillow 13.0.0,
pyparsing 3.3.3 and python-dateutil 3.0.0 (six 1.17.0, tzdata 2026.6).
Pillow 13.0.0 (MIT-CMU) became a direct dependency in TASK-212 (`uv add
"pillow>=13.0.0"`, same locked version): Pro Edit overlays draw their
procedural sprites and emoji with it (`proedit/overlays/procedural.py`).
Models (not in the lockfile; Apache-2.0 per their MediaPipe model cards),
downloaded into `models/face/` by `scripts/download_models.py` from
`https://storage.googleapis.com/mediapipe-models/` (sha256 pinned in
`model_files.py`):

- face detector BlazeFace full-range, float16 version 1,
  `face_detector/blaze_face_full_range/float16/1/blaze_face_full_range.tflite`
  (1.1 MB, sha256
  3698b18f063835bc609069ef052228fbe86d9c9a6dc8dcb7c7c2d69aed2b181b);
- face landmarker (mouth opening), float16 version 1,
  `face_landmarker/face_landmarker/float16/1/face_landmarker.task` (3.8 MB,
  sha256 64184e229b263107bc2b804c6625db1341ff2bb731874b0bcc2fe6544e0bc9ff);
- object detector EfficientDet-Lite0 (its "person" class), float32
  version 1,
  `object_detector/efficientdet_lite0/float32/1/efficientdet_lite0.tflite`
  (13.8 MB, sha256
  40338edf5ec70d43e318b0a716a84d4564cd1802759a7a07170c7e43796dbf58).

The short-range BlazeFace model of before (TASK-22 v1) is no longer used.
scipy (installed by other packages) is not used: the zero-lag smoother is a
few lines of Python (decisions.md).

The caption templates (TASK-24) read the bundled fonts' name tables with
fonttools, now a direct dependency (no py.typed), and load YAML with PyYAML
(types-PyYAML for mypy). Fonts (in `assets/fonts`, not in the lockfile;
sources and sha256 in `assets/fonts/LICENSES.md`, all SIL OFL 1.1):
Montserrat ExtraBold 9.000, Inter Bold 4.001 (Inter 4.1 release) and Noto
Emoji 3.002. Caption burn-in (TASK-26) draws them with ffmpeg's `subtitles`
filter, which needs libass: the plain Homebrew `ffmpeg` 9.0.1_1 has no libass,
so ffmpeg-full is required (docs/questions.md).

UI font (TASK-200): Poppins 4.004 Regular/Medium/SemiBold/Bold (SIL OFL 1.1,
google/fonts) in `frontend/public/fonts/`, loaded by `@font-face` in
`src/index.css`; sha256 in `assets/fonts/LICENSES.md`. It is not in
`assets/fonts`, so the caption font picker does not list it. Icons are
Phosphor (`@phosphor-icons/react`, MIT); lucide-react and Geist were removed.

Frontend package versions are resolved in `frontend/package-lock.json`.

| Package | Locked version |
| --- | --- |
| react | 18.3.1 |
| react-dom | 18.3.1 |
| react-router-dom | 7.18.5 |
| @tanstack/react-query | 5.105.0 |
| vite | 8.3.5 |
| @vitejs/plugin-react | 6.1.2 |
| tailwindcss | 4.3.3 |
| @tailwindcss/vite | 4.3.3 |
| shadcn | 4.23.0 |
| typescript | 5.9.3 |
| eslint | 10.14.0 |
| prettier | 3.9.10 |
| vitest | 5.0.5 |
| jsdom | 30.1.3 |
| @testing-library/react | 16.3.3 |
| @testing-library/jest-dom | 7.0.1 |
| @testing-library/user-event | 14.6.8 |
| @eslint/js | 10.0.1 |
| @types/node | 24.19.2 |
| @types/react | 18.3.31 |
| @types/react-dom | 18.3.7 |
| @vitejs/plugin-react | 6.1.2 |
| eslint-config-prettier | 10.1.8 |
| eslint-plugin-react-hooks | 7.1.1 |
| eslint-plugin-react-refresh | 0.5.7 |
| globals | 17.13.0 |
| typescript-eslint | 8.72.1 |
| class-variance-authority | 0.7.1 |
| cn | 0.5.1 |
| @phosphor-icons/react | 2.1.10 (MIT; icons, TASK-200) |
| radix-ui | 1.8.1 |
| tw-animate-css | 1.4.0 |

## Optional engines (v2), probed 2026-10-31 (TASK-55)

Machine: Apple M4 Max (arm64), 48 GiB RAM, macOS 27.0.1, 557 GiB free. None
of the engine packages is a dependency yet: each engine task adds its own
(uv pins the version, SPEC-v2 0.2). `Pip dry run` is `uv pip install
--dry-run --python .venv/bin/python <package>`: it resolves for this Mac
without installing (it says nothing about the model weights or the license,
which each engine task verifies). `make check-engines` runs the `engine_*`
tests (backend/tests/engine_probes.py).

| Engine | Probe command | Result on this Mac |
| --- | --- | --- |
| Ollama VLM (engine_ollama_vlm) | `ollama list`, then `ollama show <model>` (Capabilities) | Installed (client 0.34.4), server not running by default (`ollama serve`). Vision models: qwen3.5-35b-128k:latest (qwen35moe, 23 GB, Q4_K_M), huihui_ai/qwen3.5-abliterated:35b. The engine test passes with the server up. |
| DeepFilterNet (engine_deepfilternet) | `deep-filter --version`; `uv pip install deepfilternet` + `import df` in a scratch venv | Installed (TASK-113): the release program `deep-filter` 0.5.6 (aarch64-apple-darwin, Mach-O arm64) in `models/deepfilternet`, via `scripts/download_models.py --deepfilternet`. The pip package 0.5.6 installs (numpy 1.26.4, torch 2.15.0, torchaudio 2.11.1) but `import df` fails: `ModuleNotFoundError: No module named 'torchaudio.backend'`; it also pins numpy<2. Fallback filters in ffmpeg-full: `arnndn`, `afftdn` (`pipeline/enhance.py`). |
| Kokoro (engine_kokoro) | `uv pip install --python .venv/bin/python kokoro-onnx`, `scripts/download_models.py --kokoro` | Installed (TASK-117): kokoro-onnx 0.6.1 (MIT) with espeakng-loader 0.2.4 (bundles espeak-ng, GPL-3.0), phonemizer 3.4.0 (GPL-3.0-or-later), dlinfo 2.0.0, in `.venv` (not in pyproject: `uv sync` removes it). Model Kokoro-82M v1.0 (hexgrad, Apache-2.0) as `kokoro-v1.0.onnx` + `voices-v1.0.bin` from kokoro-onnx release model-files-v1.1, pinned by sha256, in `models/kokoro`. Load 0.7 s, a sentence 0.8 s, 24 kHz. |
| Piper (engine_piper) | `piper --help`, `scripts/download_models.py --piper` | Installed (TASK-117): piper-tts 1.8.0 (GPL-3.0-or-later) as a uv tool at ~/.local/bin/piper, run as a separate program (`PIPER_BIN` or PATH). Default voice `en_US-ljspeech-medium` from HF rhasspy/piper-voices (repo MIT) at commit b4e358ff, trained on LJ Speech (public domain per its MODEL_CARD), pinned by sha256, in `models/piper`. A sentence 0.8 s, 22.05 kHz. Not picked: lessac (Blizzard license), amy/alan (card says "see URL"). |
| Demucs (engine_demucs) | `uv pip install --dry-run demucs`, `import demucs` | Not installed; resolves (13 packages). |
| mflux / diffusers image (engine_image_gen) | `uv pip install --dry-run mflux` (23 packages) and `diffusers` (5), `import mflux` | Neither installed; both resolve. torch is absent. |
| Real-ESRGAN (engine_realesrgan) | `which realesrgan-ncnn-vulkan`, `uv pip install --dry-run realesrgan-ncnn-py` | Binary not on PATH; the Python wrapper resolves (1 package). |
| XTTS-class voice clone (engine_voice_clone) | `uv pip install --dry-run coqui-tts`, `import TTS` | Not installed; resolves (38 packages). License of the weights: verified in the dubbing task. |
| Gaze redirection (no marker yet) | `uv pip install --dry-run gaze-redirection` | "unsatisfiable": no package of that name. The eye contact task researches a model and records BLOCKED with evidence if none is usable. |
| Outpainting (no marker yet) | `uv pip install --dry-run diffusers` | Resolves, but no model has been picked: decided in the AI expand task, else BLOCKED. |
| Text-to-video (no marker yet) | `uv pip install --dry-run diffusers` | Resolves, but no model has been picked: decided in the AI video B-roll task, else BLOCKED. |
| MLX Whisper (engine_mlx_whisper, TASK-197) | `uv add` of `mlx-whisper`, `import mlx_whisper`, `models/whisper-mlx/<name>` | Installed and used (Apple Silicon marker in pyproject.toml; Python 3.11 on arm64 installs without errors). Word timestamps work (`transcribe(..., word_timestamps=True)`). Model `mlx-community/whisper-small-mlx` (481 MB): OpenAI Whisper small converted to MLX, MIT per the original; the card has no license field. Benchmarks in docs/decisions.md. |
| YAMNet (engine_yamnet) | files in `models/yamnet`, `load_yamnet()` | Installed (v1, onnxruntime 1.31.1). |
| sentence-transformers (engine_embeddings) | `uv pip install --dry-run sentence-transformers`, `import sentence_transformers` | Not installed; resolves (16 packages). Ollama embeddings are the alternative. |
