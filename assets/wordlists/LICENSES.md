# Word list licenses

The censor lists (SPEC-v2 3.4, `backend/clipforge/pipeline/censor.py`).

## censor_en.txt

- The default English censor list: common English swear words and slurs.
- Written for ClipForge from scratch on 2026-11-01 (no third-party list was
  copied or downloaded); it is part of ClipForge and ships under the
  project's license.
- Format: one entry a line, `#` comments; an entry ending in `*` is a prefix
  (`fuck*` also censors "fucking").

Lists for other languages are named `censor_<whisper code>.txt` (e.g.
`censor_es.txt`) and add to the English list for captions in that language.
Any list added here must list its source and license in this file.
