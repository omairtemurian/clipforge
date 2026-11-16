"""Generate frontend/src/api/types.ts from the backend Pydantic models.

The Pydantic models (backend/clipforge/models.py and the models of the API)
are the single source of truth (SPEC 0.9). Their JSON schemas are compiled to
TypeScript by json-schema-to-typescript and formatted with the frontend's
prettier:

    uv run python scripts/gen_types.py            # rewrite types.ts
    uv run python scripts/gen_types.py --check    # exit 1 if types.ts is stale

`make check` runs the --check form. Requires `npm --prefix frontend ci`.
"""

import argparse
import inspect
import json
import re
import subprocess
import sys
from collections.abc import Sequence
from pathlib import Path
from types import ModuleType
from typing import Any

from clipforge import models, settings_edit, usage
from clipforge.api import (
    accounts,
    caption_templates,
    dropbox,
    gdrive,
    proedit_style,
    quick_post,
    settings,
    sources,
    uploads,
)
from clipforge.captions_templates import CaptionTemplate
from clipforge.engines import base as engines_base
from clipforge.pipeline import preview_assets
from clipforge.sources import dropbox as dropbox_source
from clipforge.sources import gdrive as gdrive_source
from pydantic import BaseModel
from pydantic.json_schema import models_json_schema

REFERENCED_BY = re.compile(
    r"(?: \* ?\n)? \* This interface was referenced by `ApiTypes`'s JSON-Schema\n"
    r' \* via the `definition` "[^"]+"\.\n'
)
EMPTY_COMMENT = re.compile(r"/\*\*\n \*/\n")
ROOT_INTERFACE = re.compile(r"export interface ApiTypes \{.*?\n\}\n", re.DOTALL)
ROOT = Path(__file__).resolve().parent.parent
FRONTEND = ROOT / "frontend"
DEFAULT_OUTPUT = FRONTEND / "src" / "api" / "types.ts"
SOURCE_MODULES: tuple[ModuleType, ...] = (
    models,
    settings_edit,
    caption_templates,
    settings,
    sources,
    uploads,
    gdrive,
    gdrive_source,
    dropbox,
    dropbox_source,
    preview_assets,
    engines_base,
    usage,
    accounts,
    quick_post,
    proedit_style,
)
# Request bodies keep their optional fields; every other model is a response.
REQUEST_MODELS = frozenset(
    {
        "ProjectCreate",
        "ProjectPatch",
        "ClipPatch",
        "QuickPost",
        "CleanupOptions",
        "CleanupApply",
        "SettingsUpdate",
        "SourceProbe",
        "UploadComplete",
        "DriveFileRequest",
        "DriveImport",
        "DropboxFileRequest",
        "DropboxImport",
        "WatchedChannelCreate",
        "WatchedChannelPatch",
        "WatchedStreamerCreate",
        "WatchedStreamerPatch",
        "StyleRecipeCreate",
        "StyleRecipePatch",
    }
)
HEADER = """\
/* eslint-disable */
/**
 * GENERATED FILE - DO NOT EDIT BY HAND.
 * Source: the Pydantic models of backend/clipforge (models.py and the API).
 * Regenerate with: uv run python scripts/gen_types.py
 */

"""


def model_classes() -> list[type[BaseModel]]:
    """Return the models defined in SOURCE_MODULES plus CaptionTemplate, by name."""
    found: dict[str, type[BaseModel]] = {"CaptionTemplate": CaptionTemplate}
    for module in SOURCE_MODULES:
        for name, obj in inspect.getmembers(module, inspect.isclass):
            if issubclass(obj, BaseModel) and obj.__module__ == module.__name__:
                found[name] = obj
    return [found[name] for name in sorted(found)]


def simplify(node: Any, *, is_definition: bool = False) -> None:
    """Make a schema fit json-schema-to-typescript, in place.

    Property titles are dropped (each would become a type alias of its own)
    and `prefixItems` (draft 2020-12 tuples) becomes the draft-07 `items` list.
    """
    if isinstance(node, list):
        for item in node:
            simplify(item)
        return
    if not isinstance(node, dict):
        return
    if not is_definition:
        node.pop("title", None)
    if "prefixItems" in node:
        node["items"] = node.pop("prefixItems")
    for key, value in node.items():
        if key == "properties":
            for prop in value.values():
                simplify(prop)
        else:
            simplify(value)


def combined_schema() -> dict[str, Any]:
    """Return one JSON schema whose $defs hold every model.

    Responses are serialized with all their fields (a field with a default is
    always present), so every property of a response model is required.
    """
    _, schema = models_json_schema(
        [(cls, "serialization") for cls in model_classes()],
        ref_template="#/$defs/{model}",
    )
    # pydantic's own alias of a RootModel's schema; the model has its own def
    for name in [n for n in schema["$defs"] if n.startswith("RootModel_")]:
        del schema["$defs"][name]
    for name, definition in schema["$defs"].items():
        if name not in REQUEST_MODELS and definition.get("type") == "object":
            definition["required"] = list(definition.get("properties", {}))
        simplify(definition, is_definition=True)
    schema["title"] = "ApiTypes"
    return schema


def run_tool(command: list[str], stdin: str) -> str:
    """Run a frontend tool with stdin; return its stdout or exit with its error."""
    done = subprocess.run(  # noqa: S603 - fixed argument list, no shell
        command, input=stdin, capture_output=True, text=True, cwd=ROOT, check=False
    )
    if done.returncode != 0:
        sys.exit(
            f"gen_types: {' '.join(command)} failed ({done.returncode}): "
            f"{done.stderr.strip()}\nrun `npm --prefix frontend ci` first"
        )
    return done.stdout


def generate() -> str:
    """Return the full text of types.ts."""
    schema = json.dumps(combined_schema())
    typescript = run_tool(
        [
            "npm", "--prefix", "frontend", "exec", "--", "json2ts",
            "--unreachableDefinitions", "--no-additionalProperties",
            "--no-format", "--maxItems=-1", "--bannerComment=",
        ],
        schema,
    )  # fmt: skip
    typescript = ROOT_INTERFACE.sub("", REFERENCED_BY.sub("", typescript))
    typescript = EMPTY_COMMENT.sub("", typescript)
    formatted = run_tool(
        [
            "npm", "--prefix", "frontend", "exec", "--", "prettier",
            "--stdin-filepath", str(DEFAULT_OUTPUT),
        ],
        typescript,
    )  # fmt: skip
    return HEADER + formatted


def main(argv: Sequence[str] | None = None) -> int:
    """Write types.ts, or with --check compare it; return the exit code."""
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument(
        "--check", action="store_true", help="fail if the file is stale; write nothing"
    )
    parser.add_argument(
        "--output", type=Path, default=DEFAULT_OUTPUT, help="%(default)s"
    )
    args = parser.parse_args(argv)
    text = generate()
    current = args.output.read_text() if args.output.exists() else None
    if args.check:
        if current == text:
            return 0
        print(
            f"gen_types: {args.output} is stale; run "
            "`uv run python scripts/gen_types.py` and commit it",
            file=sys.stderr,
        )
        return 1
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(text)
    print(f"gen_types: wrote {args.output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
