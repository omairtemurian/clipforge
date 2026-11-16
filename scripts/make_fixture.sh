#!/usr/bin/env bash
# Build the pipeline test fixture with ffmpeg only (SPEC 9.1):
#   sample.mp4    60 s, 1280x720, 30 fps, H.264 yuv420p + AAC 48 kHz mono.
#                 Video: testsrc2 (Gaussian-blurred so that its per-frame
#                 random noise squares do not bloat the committed file) with a
#                 sharp drawn face-like overlay moving left to right.
#                 Audio: speech-like sine bursts and three laughs cut from a
#                 real CC0 recording of a crowd laughing (assets/sfx).
#   expected.json The media properties, burst times and face path used above.
#
# Usage: bash scripts/make_fixture.sh [output_dir]
# The default output_dir is backend/tests/fixtures. The script is idempotent:
# every input is deterministic (the committed lossless laughter clip,
# bitexact muxing, fixed encoder thread count), so re-running it rewrites
# identical files.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OUT_DIR="${1:-$ROOT/backend/tests/fixtures}"

DURATION=60
WIDTH=1280
HEIGHT=720
FPS=30
SAMPLE_RATE=48000
TITLE="ClipForge sample fixture"

# Speech-like phrases and laughs: "start end" in seconds, sorted, disjoint.
SPEECH=(
  "0.5 2.9" "3.45 6.05" "6.75 7.15" "7.7 10.5" "11.1 13.5"
  "16.9 19.7" "20.25 22.45" "23.25 23.6" "24.3 27.1" "27.65 30.05" "30.65 32.85"
  "35.8 38.4" "38.95 41.35" "42.1 42.45" "43.0 45.8" "46.4 48.8" "49.35 51.55"
  "55.5 57.9" "58.45 59.5"
)
LAUGHS=("13.8 16.3" "33.15 35.15" "51.85 54.85")
# Every laugh is an excerpt of LAUGH_SFX (CC0, see assets/sfx/LICENSES.md):
# "offset gain" per laugh, in LAUGHS order, is where the excerpt starts in
# the clip (s) and its gain (dB), which brings it to about -16.5 dBFS RMS,
# ~11 dB above the speech. YAMNet hears these excerpts as Laughter.
LAUGH_SFX="$ROOT/assets/sfx/crowd_laugh.flac"
LAUGH_CUTS=("1.00 -1.5" "1.32 -2.4" "0.48 -0.9")

SPEECH_AMP=0.13  # about -28 dBFS RMS while a phrase is playing
RAMP_S=0.03      # linear fade at both ends of every burst (avoids clicks)

# Face overlay: a FACE_W x FACE_H RGBA image whose head ellipse fills the
# box; its centre moves linearly from FACE_X0 to FACE_X1 over the video.
FACE_W=240
FACE_H=300
FACE_CY=360
FACE_X0=200
FACE_X1=1080
SKIN="236 192 160"

# ellipse CX CY RX RY -> expression that is <= 1 inside the ellipse.
ellipse() {
  printf 'pow((X-%s)/%s,2)+pow((Y-%s)/%s,2)' "$1" "$3" "$2" "$4"
}

# Face features from the top layer down: "condition|R G B". The colour
# terms may use ld(1), the head shading factor. The centre row (Y=150)
# crosses only skin, which the fixture test relies on.
FACE_LAYERS=(
  "lte($(ellipse 76 128 5 5),1)+lte($(ellipse 164 128 5 5),1)|15 10 10"
  "lte($(ellipse 76 128 10.5 10.5),1)+lte($(ellipse 164 128 10.5 10.5),1)|75 50 35"
  "lte($(ellipse 76 128 25 13),1)+lte($(ellipse 164 128 25 13),1)|248 248 248"
  "lte($(ellipse 76 104 27 6.5),1)+lte($(ellipse 164 104 27 6.5),1)|70 45 30"
  "lt(Y,46+0.0028*pow(X-120,2))|70 45 30"
  "lte($(ellipse 120 238 36 3.5),1)|100 30 35"
  "lte($(ellipse 120 238 44 14),1)|185 75 80"
  "lte($(ellipse 110 202 5 3.5),1)+lte($(ellipse 130 202 5 3.5),1)|120 70 60"
  "lte($(ellipse 120 180 13 26),1)|213*ld(1) 160*ld(1) 128*ld(1)"
)
HEAD="$(ellipse 120 150 118 148)"

# face_channel INDEX -> geq expression for colour channel 0 (R), 1 (G), 2 (B).
face_channel() {
  local skin rgb expr layer i
  read -r -a skin <<<"$SKIN"
  expr="${skin[$1]}*ld(1)"
  for ((i = ${#FACE_LAYERS[@]} - 1; i >= 0; i--)); do
    layer="${FACE_LAYERS[i]}"
    read -r -a rgb <<<"${layer#*|}"
    expr="if(${layer%%|*},${rgb[$1]},${expr})"
  done
  printf 'st(1,1-0.15*(%s));%s' "$HEAD" "$expr"
}

# gate BURST... -> expression that is 1 inside the bursts (with RAMP_S
# fades) and 0 elsewhere, evaluated on the sample time t.
gate() {
  local out="" burst start end
  for burst in "$@"; do
    start="${burst% *}"
    end="${burst#* }"
    out="${out:+$out+}if(between(t,$start,$end),min(1,min(t-$start,$end-t)/$RAMP_S),0)"
  done
  printf '%s' "$out"
}

# laugh_track -> filter chain from input 0 (LAUGH_SFX) to [laughs]: the
# LAUGH_CUTS excerpts placed at the LAUGHS times, silence elsewhere, padded
# to DURATION.
laugh_track() {
  local i start end offset gain delay_ms cuts="" chains="" mix=""
  for i in "${!LAUGHS[@]}"; do
    read -r start end <<<"${LAUGHS[i]}"
    read -r offset gain <<<"${LAUGH_CUTS[i]}"
    delay_ms="$(awk -v t="$start" 'BEGIN { printf "%d", t * 1000 + 0.5 }')"
    cuts+="[cut$i]"
    # adelay and amix leave some frames without timestamps (aeval would
    # compute NaN from them); asetpts renumbers them from the sample count.
    chains+="[cut$i]atrim=start=$offset,volume=volume=${gain}dB,adelay=delays=$delay_ms,"
    chains+="asetpts=N/SR/TB,atrim=end=$end[laugh$i];"
    mix+="[laugh$i]"
  done
  printf '[0:a]asplit=outputs=%s%s;%s%s' "${#LAUGHS[@]}" "$cuts" "$chains" "$mix"
  printf 'amix=inputs=%s:normalize=0,apad=whole_dur=%s,asetpts=N/SR/TB[laughs];' \
    "${#LAUGHS[@]}" "$DURATION"
}

# json_bursts BURST... -> JSON array items, one per line.
json_bursts() {
  local count=0 burst sep
  for burst in "$@"; do
    count=$((count + 1))
    sep=","
    [ "$count" -eq $# ] && sep=""
    printf '    {"start": %s, "end": %s}%s\n' "${burst% *}" "${burst#* }" "$sep"
  done
}

command -v ffmpeg >/dev/null 2>&1 || {
  echo "make_fixture.sh: ffmpeg not found (install it with: brew install ffmpeg)" >&2
  exit 1
}
[ -f "$LAUGH_SFX" ] || {
  echo "make_fixture.sh: laughter clip not found: $LAUGH_SFX" >&2
  exit 1
}

# Speech: a 120-180 Hz pitch contour (phase-integrated FM) with two
# harmonics and a 4 Hz syllable envelope. Laughs: the gated laugh track.
PHASE="2*PI*150*t-30/0.7*cos(2*PI*0.7*t)"
VOICE="0.6*sin(ld(0))+0.3*sin(2*ld(0))+0.1*sin(3*ld(0))"
AUDIO="st(0,$PHASE);$SPEECH_AMP*($(gate "${SPEECH[@]}"))*(0.55+0.45*sin(2*PI*4*t))*($VOICE)+($(gate "${LAUGHS[@]}"))*val(0)"
FACE_X="$FACE_X0-$FACE_W/2+($FACE_X1-$FACE_X0)*t/$DURATION"
FACE_Y=$((FACE_CY - FACE_H / 2))
HEAD_ALPHA="255*clip((1-($HEAD))*60,0,1)"

GRAPH="$(laugh_track)"
GRAPH+="testsrc2=size=${WIDTH}x${HEIGHT}:rate=$FPS:duration=$DURATION,gblur=sigma=2[bg];"
GRAPH+="color=color=black:size=${FACE_W}x${FACE_H}:rate=1:duration=1,format=gbrap,"
GRAPH+="geq=r='$(face_channel 0)':g='$(face_channel 1)':b='$(face_channel 2)':a='$HEAD_ALPHA'[face];"
GRAPH+="[bg][face]overlay=x='$FACE_X':y=$FACE_Y:eof_action=repeat[v];"
GRAPH+="[laughs]aeval=exprs='$AUDIO':channel_layout=mono[a]"

mkdir -p "$OUT_DIR"
tmp_video="$(mktemp "$OUT_DIR/.sample.XXXXXX")"
tmp_json="$(mktemp "$OUT_DIR/.expected.XXXXXX")"
trap 'rm -f "$tmp_video" "$tmp_json"' EXIT

ffmpeg -hide_banner -nostdin -loglevel error -y -i "$LAUGH_SFX" \
  -filter_complex "$GRAPH" -map "[v]" -map "[a]" -map_metadata -1 \
  -c:v libx264 -preset slower -crf 28 -pix_fmt yuv420p -threads 4 \
  -c:a aac -b:a 64k -ar "$SAMPLE_RATE" -ac 1 \
  -metadata title="$TITLE" \
  -fflags +bitexact -flags:v +bitexact -flags:a +bitexact \
  -movflags +faststart -f mp4 "$tmp_video"

read -r -a skin <<<"$SKIN"
cat >"$tmp_json" <<EOF
{
  "generator": "scripts/make_fixture.sh",
  "media": {
    "duration": $DURATION,
    "width": $WIDTH,
    "height": $HEIGHT,
    "fps": $FPS,
    "video_codec": "h264",
    "pix_fmt": "yuv420p",
    "audio_codec": "aac",
    "sample_rate": $SAMPLE_RATE,
    "channels": 1,
    "title": "$TITLE"
  },
  "speech": [
$(json_bursts "${SPEECH[@]}")
  ],
  "laughs": [
$(json_bursts "${LAUGHS[@]}")
  ],
  "face": {
    "description": "Drawn face-like overlay (skin-tone head ellipse with hair, brows, eyes, nose and mouth) that moves left to right at constant speed for the whole video; its vertical position is fixed. Positions are the face centre in pixels.",
    "width": $FACE_W,
    "height": $FACE_H,
    "skin_rgb": [${skin[0]}, ${skin[1]}, ${skin[2]}],
    "motion": "linear",
    "start": {"t": 0, "center_x": $FACE_X0, "center_y": $FACE_CY},
    "end": {"t": $DURATION, "center_x": $FACE_X1, "center_y": $FACE_CY}
  }
}
EOF

chmod 0644 "$tmp_video" "$tmp_json"
mv -f "$tmp_video" "$OUT_DIR/sample.mp4"
mv -f "$tmp_json" "$OUT_DIR/expected.json"
echo "Wrote $OUT_DIR/sample.mp4 and $OUT_DIR/expected.json"
