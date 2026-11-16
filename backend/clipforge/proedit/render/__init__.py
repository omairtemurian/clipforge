"""The Pro Edit renderer (SPEC-v3 3.6): one ffmpeg filter graph that frames
and cuts a clip as its normal render does and draws the items of its EDL on
it (graph), stage by stage (grade, ...), run as a 540p proxy or the final at
the source's resolution and checked with ffprobe (run)."""
