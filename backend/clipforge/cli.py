"""The `clipforge` command line.

`clipforge run <file|url>` processes a video from ingest to rendered clips and
prints the path of each clip. `clipforge step <name> <job_id> [--force]` runs
one pipeline step (SPEC 6) for an existing job, so steps can be rerun and
debugged one at a time. Both work in the configured data_dir and record their
work on the job row; log records go to stderr.
"""

import argparse
import logging
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import get_args

from pydantic import ValidationError
from sqlalchemy import Engine

from clipforge.aspect import PRESETS, check_aspect
from clipforge.db import init_db
from clipforge.ffmpeg import FFmpegError, check_ffmpeg
from clipforge.models import Genre, ProcessingSettings
from clipforge.pipeline.step import STEP_NAMES, StepError
from clipforge.process import create_job, run_process_job, run_step
from clipforge.testmode import ENV_VAR, RecordedInputs, RecordedLLM, recorded_inputs

PROG = "clipforge"


def build_parser() -> argparse.ArgumentParser:
    """Return the parser of the clipforge command line."""
    parser = argparse.ArgumentParser(prog=PROG, description="ClipForge tools.")
    commands = parser.add_subparsers(dest="command", required=True)

    run = commands.add_parser(
        "run",
        help="turn a video into rendered clips",
        description="Ingest, transcribe, analyze (signals), enrich, curate, "
        "score and snap a video, then render its best clips into "
        "{data_dir}/output/<project_id>/.",
    )
    run.add_argument("source", help="a video file or an http(s) URL")
    run.add_argument(
        "--genre",
        choices=get_args(Genre),
        help="default: auto (comedy above 1 laugh per minute, else podcast)",
    )
    run.add_argument(
        "--aspect",
        type=_aspect,
        metavar="W:H",
        help=f"{', '.join(PRESETS)} or a custom ratio up to 4:1 (default: 9:16)",
    )
    run.add_argument(
        "--num-clips",
        type=_num_clips,
        metavar="N",
        help="the most clips to render, 1 to 30 (default: default_num_clips)",
    )
    run.add_argument(
        "--fixtures-dir",
        type=Path,
        metavar="DIR",
        help=f"test mode, with {ENV_VAR}=1: use DIR/transcript.json and "
        "DIR/llm_response.json instead of whisper and the LLM",
    )

    step = commands.add_parser(
        "step",
        help="run one pipeline step for a job",
        description="Run one pipeline step in the job's work directory.",
    )
    step.add_argument("name", choices=STEP_NAMES, help="the step to run")
    step.add_argument("job_id", type=int, help="the id of the job")
    step.add_argument(
        "--force", action="store_true", help="redo the step even if its output exists"
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run the command line with argv (default: sys.argv) and return the exit code.

    run prints the path of each rendered clip and returns 0 if no clip failed
    (also when the video has no clips); step prints the step's output path and
    returns 0. Both print the error and return 1 if a step fails (or, for
    step, the job does not exist), and run also returns 1 if a clip fails to
    render. It first checks that ffmpeg has libass and returns 1 if not. Bad
    arguments exit with status 2.
    """
    parser = build_parser()
    args = parser.parse_args(argv)
    recorded: RecordedInputs | None = None
    if args.command == "run":
        try:
            recorded = recorded_inputs(args.fixtures_dir)
        except ValueError as exc:
            parser.error(str(exc))
    logging.basicConfig(
        level=logging.INFO, format="%(levelname)s %(name)s: %(message)s"
    )
    engine = init_db()
    try:
        check_ffmpeg()
        if args.command == "run":
            return _run(engine, args, recorded)
        return _step(engine, args)
    except (StepError, FFmpegError) as exc:
        print(f"{PROG}: error: {exc}", file=sys.stderr)
        return 1
    finally:
        engine.dispose()


def _run(
    engine: Engine, args: argparse.Namespace, recorded: RecordedInputs | None
) -> int:
    """Run `clipforge run` with the parsed args; return the exit code."""
    chosen = {"genre": args.genre, "aspect": args.aspect, "num_clips": args.num_clips}
    processing = ProcessingSettings.model_validate(
        {name: value for name, value in chosen.items() if value is not None}
    )
    job_id = create_job(engine, args.source, processing)
    if recorded is None:
        clips = run_process_job(engine, job_id)
    else:
        llm = RecordedLLM(recorded.llm_response)
        clips = run_process_job(engine, job_id, llm=llm, transcript=recorded.transcript)
    for clip in clips:
        if clip.output_path is not None:
            print(clip.output_path)
    failed = [clip.id for clip in clips if clip.status == "failed"]
    if failed:
        ids = ", ".join(map(str, failed))
        print(
            f"{PROG}: error: {len(failed)} of {len(clips)} clips failed to render "
            f"(ids: {ids})",
            file=sys.stderr,
        )
        return 1
    return 0


def _step(engine: Engine, args: argparse.Namespace) -> int:
    """Run `clipforge step` with the parsed args; return the exit code."""
    print(run_step(engine, args.name, args.job_id, force=args.force))
    return 0


def _num_clips(text: str) -> int:
    """Parse --num-clips as a clip count that ProcessingSettings accepts."""
    try:
        return ProcessingSettings.model_validate({"num_clips": text}).num_clips
    except ValidationError as exc:
        raise argparse.ArgumentTypeError(exc.errors()[0]["msg"].lower()) from exc


def _aspect(text: str) -> str:
    """Parse --aspect as a preset or custom W:H ratio."""
    try:
        return check_aspect(text)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(str(exc)) from exc


if __name__ == "__main__":
    raise SystemExit(main())
