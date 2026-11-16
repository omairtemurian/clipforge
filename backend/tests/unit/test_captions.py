"""Tests of pipeline/captions (SPEC 6.9): each template's Dialogue lines for
six words, the hook overlay at the top for 2.5 s, the styles on the output
frame, and how write_captions reads a job's transcript."""

from pathlib import Path

import pytest
from builders import make_clip, word
from caption_fakes import caption_dialogues, dialogues, write
from clipforge.captions_templates import get_template, load_templates
from clipforge.models import Aspect
from clipforge.pipeline.captions import build_ass, write_captions
from clipforge.pipeline.step import StepError

# Each v1 template's hook text, then the text of each word's Dialogue, with
# "brother" as the emphasis word: 3 words a line; "pizza" has an emoji in
# emoji_map.yaml. The SPEC-v2 templates are in tests/test_caption_templates_v2.
EXPECTED = {
    "karaoke_bold": [
        "HE ATE IT ALL",
        r"{\c&H3FD2FF&}WAIT,{\r}",
        r"{\c&H3FD2FF&}MY{\r} {\c&H356BFF&\fscx110\fscy110}BROTHER{\r} ATE",
        r"MY {\c&H3FD2FF&\fscx110\fscy110}BROTHER{\r} ATE",
        r"MY {\c&H356BFF&\fscx110\fscy110}BROTHER{\r} {\c&H3FD2FF&}ATE{\r}",
        r"{\c&H3FD2FF&}THE{\r}",
        r"{\c&H3FD2FF&}PIZZA.{\r}",
    ],
    "minimal": [
        "He ate it all",
        r"{\c&HFFFFFF&}Wait,{\r}",
        r"{\c&HFFFFFF&}my{\r} {\c&H3FD2FF&\fscx110\fscy110}brother{\r} ate",
        r"my {\c&HFFFFFF&\fscx110\fscy110}brother{\r} ate",
        r"my {\c&H3FD2FF&\fscx110\fscy110}brother{\r} {\c&HFFFFFF&}ate{\r}",
        r"{\c&HFFFFFF&}the{\r}",
        r"{\c&HFFFFFF&}pizza.{\r}",
    ],
    "boxed": [
        "HE ATE IT ALL",
        r"{\c&H356BFF&}WAIT,{\r}",
        r"{\c&H356BFF&}MY{\r} {\c&H3FD2FF&\fscx110\fscy110}BROTHER{\r} ATE",
        r"MY {\c&H356BFF&\fscx110\fscy110}BROTHER{\r} ATE",
        r"MY {\c&H3FD2FF&\fscx110\fscy110}BROTHER{\r} {\c&H356BFF&}ATE{\r}",
        r"{\c&H356BFF&}THE{\r}",
        r"{\c&H356BFF&}PIZZA.{\r}",
    ],
    "neon": [
        "HE ATE IT ALL",
        r"{\c&HD62BFF&}WAIT,{\r}",
        r"{\c&HD62BFF&}MY{\r} {\c&H14FF39&\fscx110\fscy110}BROTHER{\r} ATE",
        r"MY {\c&HD62BFF&\fscx110\fscy110}BROTHER{\r} ATE",
        r"MY {\c&H14FF39&\fscx110\fscy110}BROTHER{\r} {\c&HD62BFF&}ATE{\r}",
        r"{\c&HD62BFF&}THE{\r}",
        r"{\c&HD62BFF&}PIZZA.{\r} {\fnNoto Emoji}🍕{\fn}",
    ],
    "comic": [
        "HE ATE IT ALL",
        r"{\c&HFFFFFF&}WAIT,{\r}",
        r"{\c&HFFFFFF&}MY{\r} {\c&H303BFF&\fscx110\fscy110}BROTHER{\r} ATE",
        r"MY {\c&HFFFFFF&\fscx110\fscy110}BROTHER{\r} ATE",
        r"MY {\c&H303BFF&\fscx110\fscy110}BROTHER{\r} {\c&HFFFFFF&}ATE{\r}",
        r"{\c&HFFFFFF&}THE{\r}",
        r"{\c&HFFFFFF&}PIZZA.{\r} {\fnNoto Emoji}🍕{\fn}",
    ],
    "clean_subtitle": [
        "He ate it all",
        r"{\c&HFFFFFF&}Wait,{\r}",
        r"{\c&HFFFFFF&}my{\r} {\c&HFFFFFF&\fscx110\fscy110}brother{\r} ate",
        r"my {\c&HFFFFFF&\fscx110\fscy110}brother{\r} ate",
        r"my {\c&HFFFFFF&\fscx110\fscy110}brother{\r} {\c&HFFFFFF&}ate{\r}",
        r"{\c&HFFFFFF&}the{\r}",
        r"{\c&HFFFFFF&}pizza.{\r}",
    ],
}
STYLE_FORMAT = (
    "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, "
    "OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, "
    "ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, "
    "MarginR, MarginV, Encoding"
)
EVENT_FORMAT = (
    "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text"
)


def test_every_v1_template_has_expected_lines() -> None:
    assert set(EXPECTED) <= set(load_templates())


@pytest.mark.parametrize("name", list(EXPECTED))
def test_each_word_gets_a_dialogue_of_its_line(name: str, tmp_path: Path) -> None:
    hook, *texts = EXPECTED[name]

    assert dialogues(write(tmp_path, make_clip(name))) == caption_dialogues(hook, texts)
    assert (tmp_path / "captions_7.ass").is_file()


def test_the_file_draws_on_the_output_frame_with_two_styles() -> None:
    ass = build_ass([], get_template("karaoke_bold"), (1080, 1920), emoji_map={})

    assert ass == "\n".join(
        [
            "[Script Info]",
            "ScriptType: v4.00+",
            "PlayResX: 1080",
            "PlayResY: 1920",
            "WrapStyle: 0",
            "ScaledBorderAndShadow: yes",
            "YCbCr Matrix: None",
            "",
            "[V4+ Styles]",
            STYLE_FORMAT,
            "Style: Caption,Montserrat ExtraBold,62,&H00FFFFFF,&H003FD2FF,"
            "&H00000000,&H80000000,0,0,0,0,100,100,0,0,1,3.7,1.9,2,54,54,422,1",
            "Style: Hook,Montserrat ExtraBold,43,&H00FFFFFF,&H003FD2FF,"
            "&H00000000,&H80000000,0,0,0,0,100,100,0,0,1,3.7,1.9,8,54,54,192,1",
            "",
            "[Events]",
            EVENT_FORMAT,
            "",
        ]
    )


@pytest.mark.parametrize(
    ("name", "aspect", "caption", "hook"),
    [
        (
            "boxed",
            "16:9",
            "Caption,Montserrat ExtraBold,50,&H00FFFFFF,&H00356BFF,&H00000000,"
            "&H80000000,0,0,0,0,100,100,0,0,3,8.8,0,2,96,96,238,1",
            "Hook,Montserrat ExtraBold,35,&H00FFFFFF,&H00356BFF,&H00000000,"
            "&H80000000,0,0,0,0,100,100,0,0,3,8.8,0,8,96,96,108,1",
        ),
        (
            "minimal",
            "1:1",
            "Caption,Inter Bold,40,&H00D8D4D4,&H00FFFFFF,&H00000000,&H80000000,"
            "0,0,0,0,100,100,0,0,1,1.5,1.2,2,54,54,238,1",
            "Hook,Inter Bold,28,&H00D8D4D4,&H00FFFFFF,&H00000000,&H80000000,"
            "0,0,0,0,100,100,0,0,1,1.5,1.2,8,54,54,108,1",
        ),
    ],
)
def test_box_lower_third_and_aspect_show_in_the_styles(
    name: str, aspect: Aspect, caption: str, hook: str, tmp_path: Path
) -> None:
    lines = write(tmp_path, make_clip(name), aspect).splitlines()
    width, height = {"16:9": (1920, 1080), "1:1": (1080, 1080)}[aspect]

    assert lines[2:4] == [f"PlayResX: {width}", f"PlayResY: {height}"]
    assert lines[10:12] == [f"Style: {caption}", f"Style: {hook}"]


def test_the_hook_shows_at_the_top_for_two_and_a_half_seconds() -> None:
    ass = build_ass(
        [], get_template("comic"), (1080, 1920), hook_text="Wait {for} it", emoji_map={}
    )
    hook_style = next(
        line for line in ass.splitlines() if line.startswith("Style: Hook")
    )

    assert hook_style.split(",")[18] == "8"  # Alignment: top center
    assert dialogues(ass) == [
        r"Dialogue: 1,0:00:00.00,0:00:02.50,Hook,,0,0,0,,WAIT \{FOR\} IT"
    ]


@pytest.mark.parametrize("hook_text", ["", " \n "])
def test_a_blank_hook_text_has_no_hook(hook_text: str, tmp_path: Path) -> None:
    ass = write(tmp_path, make_clip("minimal", hook_text=hook_text))

    assert [line for line in dialogues(ass) if ",Hook," in line] == []
    assert len(dialogues(ass)) == 6


def test_a_clip_without_captions_shows_only_its_hook(tmp_path: Path) -> None:
    ass = write(
        tmp_path, make_clip("comic", hook_text="He ate it", show_captions=False)
    )

    assert [line.split(",")[3] for line in dialogues(ass)] == ["Hook"]


def test_caption_overrides_replace_the_text_of_their_words(tmp_path: Path) -> None:
    clip = make_clip("neon", caption_overrides=[word("lasagna!", 11.7, 12.2)])

    assert dialogues(write(tmp_path, clip))[-1] == (
        r"Dialogue: 0,0:00:01.70,0:00:02.20,Caption,,0,0,0,,{\c&HD62BFF&}LASAGNA!{\r}"
    )


def test_captions_follow_the_clip_with_its_cut_ranges_taken_out(
    tmp_path: Path,
) -> None:
    # "brother" (10.54-10.8) goes whole; the pause before "pizza." goes too.
    # At 30 fps the cuts' edges move to the nearest frame, as the render cuts
    # them: 10.84 to 10.833 and 11.25 to 11.267, so 0.766 s goes in all.
    clip = make_clip("minimal", cut_ranges=[(10.5, 10.84), (11.25, 11.7)])

    captions = [line for line in dialogues(write(tmp_path, clip)) if "Caption" in line]

    assert [line.split(",")[1:3] for line in captions] == [
        ["0:00:00.00", "0:00:00.36"],
        ["0:00:00.36", "0:00:00.51"],
        ["0:00:00.51", "0:00:00.81"],
        ["0:00:00.81", "0:00:00.93"],
        ["0:00:00.93", "0:00:01.43"],
    ]
    assert captions[-2].endswith(r",,my ate {\c&HFFFFFF&}the{\r}")
    assert captions[-1].endswith(r",,{\c&HFFFFFF&}pizza.{\r}")


def test_missing_transcript_or_template_raises(tmp_path: Path) -> None:
    with pytest.raises(StepError, match="run the transcribe step first"):
        write_captions(tmp_path, make_clip("neon"), (1080, 1920), 30)
    with pytest.raises(ValueError, match="unknown caption template 'nope'"):
        write(tmp_path, make_clip("nope"))
    assert not (tmp_path / "captions_7.ass").exists()
