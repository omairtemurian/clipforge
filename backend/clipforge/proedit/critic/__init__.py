"""The Pro Edit critic (SPEC-v3 3.7): it looks at frames of the proxy render,
an audio summary, the transcript and the EDL, and scores a checklist.

- vision: LLM requests with images, for each provider that can send them.
- capability: whether the configured model accepts images (probed once).
- sample: the frames the critic sees, at exact frame times.
- audio_summary: the loudness curve, speech/music/SFX levels and clipping.
- prompt: the checklist messages and the reply schema.
- score: the scored, metered and capped critic calls.
- changes: the EDL changes the critic may ask for.
- apply: those changes applied with validation, and what changed.
- revise: the rounds of scores and revisions, early stop and cost guard.
"""
