"""The tools of the MCP server (SPEC-v2 3.14), built from the OpenAPI
document of the public API /api/v1: one tool per operation, with a JSON
Schema of its inputs (path and query parameters, then the fields of the
JSON body, or the form fields of an upload with the path of a local file).

The tools mirror the API 1:1 except for the operations that agents must
not do. Queueing and publishing a post and approving or rejecting an
autopilot draft are the owner's (rule of 2026-10-31, SPEC-v2 3.19): they
get no tool, and neither does the `queue` flag of the bulk
scheduler. The server enforces the same rule with 403 human_only. A few
operations that cannot work over MCP (chunked uploads, the event stream,
the raw cover upload) are left out too.
"""

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

Schema = dict[str, Any]
V1_PREFIX = "/api/v1/"
REF_PREFIX = "#/components/schemas/"
DEFS_PREFIX = "#/$defs/"
BODY_KEY = "body"

HUMAN_ONLY = frozenset(
    {
        "POST /api/v1/posts/{post_id}/queue",
        "POST /api/v1/posts/{post_id}/publish",
        "POST /api/v1/drafts/{draft_id}/approve",
        "POST /api/v1/drafts/{draft_id}/reject",
        "POST /api/v1/campaigns/{campaign_id}/drafts/approve",
    }
)
NOT_OVER_MCP = frozenset(
    {
        "POST /api/v1/uploads",
        "GET /api/v1/uploads/{upload_id}",
        "PATCH /api/v1/uploads/{upload_id}",
        "DELETE /api/v1/uploads/{upload_id}",
        "POST /api/v1/uploads/{upload_id}/complete",
        "GET /api/v1/jobs/{job_id}/events",
        "POST /api/v1/clips/{clip_id}/thumbnail/upload",
    }
)
HIDDEN_FIELDS = {"POST /api/v1/posts/bulk-schedule": frozenset({"queue"})}
BodyKind = Literal["json", "multipart"]


@dataclass(frozen=True)
class ToolSpec:
    """One tool: the API operation it calls and the layout of its inputs."""

    name: str
    description: str
    method: str
    path: str
    input_schema: Schema
    path_params: tuple[str, ...]
    query_params: tuple[str, ...]
    body_kind: BodyKind | None
    body_fields: tuple[str, ...]
    file_fields: tuple[str, ...]

    @property
    def read_only(self) -> bool:
        return self.method == "GET"


@dataclass(frozen=True)
class ApiRequest:
    """The pieces of an HTTP request that a tool call makes."""

    url: str
    params: dict[str, Any]
    json: Any
    data: dict[str, str] | None
    files: dict[str, tuple[str, bytes]] | None


def _ref_name(schema: Any) -> str | None:
    if isinstance(schema, dict) and str(schema.get("$ref", "")).startswith(REF_PREFIX):
        return str(schema["$ref"])[len(REF_PREFIX) :]
    return None


def _rewrite(node: Any, used: set[str]) -> Any:
    """Return node with its $refs pointing at #/$defs, and add the names it
    refers to to used."""
    if isinstance(node, list):
        return [_rewrite(item, used) for item in node]
    if not isinstance(node, dict):
        return node
    out: Schema = {}
    for key, value in node.items():
        if key == "$ref" and isinstance(value, str) and value.startswith(REF_PREFIX):
            used.add(value[len(REF_PREFIX) :])
            out[key] = DEFS_PREFIX + value[len(REF_PREFIX) :]
        else:
            out[key] = _rewrite(value, used)
    return out


def _with_defs(schema: Schema, components: Schema, used: set[str]) -> Schema:
    """Add to schema the $defs of every component in used and, in turn, of
    the components those refer to."""
    defs: Schema = {}
    pending = set(used)
    while pending:
        name = pending.pop()
        if name in defs:
            continue
        more: set[str] = set()
        defs[name] = _rewrite(components[name], more)
        pending |= more - defs.keys()
    if defs:
        schema["$defs"] = defs
    return schema


def _tool_name(operation_id: str) -> str:
    """Return the function name of a FastAPI operation id
    (`create_project_api_v1_projects_post` -> `create_project`)."""
    return operation_id.split("_api_v1_")[0]


def _parameter_schema(parameter: Schema, used: set[str]) -> Schema:
    schema = _rewrite(parameter.get("schema", {}), used)
    if parameter.get("description"):
        schema["description"] = parameter["description"]
    return dict(schema)


def _body(
    spec: Schema, components: Schema, hidden: frozenset[str]
) -> tuple[BodyKind | None, Schema, list[str], tuple[str, ...]]:
    """Return (kind, body schema, required fields, file fields) of an
    operation's request body; fields of an object body are inputs of their
    own, any other body is the input `body`."""
    content = spec.get("requestBody", {}).get("content", {})
    kind: BodyKind = "multipart" if "multipart/form-data" in content else "json"
    media = content.get("multipart/form-data") or content.get("application/json")
    if media is None:
        return None, {}, [], ()
    schema = media["schema"]
    resolved = components[_ref_name(schema) or ""] if _ref_name(schema) else schema
    if resolved.get("type") != "object" or "properties" not in resolved:
        required = [BODY_KEY] if spec["requestBody"].get("required") else []
        return kind, {BODY_KEY: schema}, required, ()
    properties = {k: v for k, v in resolved["properties"].items() if k not in hidden}
    files = tuple(
        name
        for name, prop in properties.items()
        if prop.get("contentMediaType") == "application/octet-stream"
    )
    required = [name for name in resolved.get("required", []) if name in properties]
    return kind, properties, required, files


def build_tool(
    method: str, path: str, spec: Schema, components: Schema
) -> ToolSpec | None:
    """Return the tool of an operation, or None if agents get none."""
    label = f"{method.upper()} {path}"
    if label in HUMAN_ONLY or label in NOT_OVER_MCP:
        return None
    hidden = HIDDEN_FIELDS.get(label, frozenset())
    used: set[str] = set()
    properties: Schema = {}
    required: list[str] = []
    located: dict[str, list[str]] = {"path": [], "query": []}
    for parameter in spec.get("parameters", []):
        where = parameter["in"]
        if where not in located:
            raise ValueError(f"{label}: {where} parameters are not supported")
        located[where].append(parameter["name"])
        properties[parameter["name"]] = _parameter_schema(parameter, used)
        if parameter.get("required"):
            required.append(parameter["name"])
    kind, body, body_required, files = _body(spec, components, hidden)
    for name, schema in body.items():
        if name in properties:
            raise ValueError(f"{label}: body field {name} is also a parameter")
        properties[name] = _rewrite(schema, used)
    for name in files:
        properties[name] = {
            "type": "string",
            "description": "Path of a local file to upload",
        }
    required += body_required
    schema_: Schema = {"type": "object", "properties": properties}
    if required:
        schema_["required"] = required
    schema_["additionalProperties"] = False
    summary = spec.get("summary", "")
    text = re.sub(r"\s+", " ", spec.get("description", "")).strip()
    return ToolSpec(
        name=_tool_name(spec["operationId"]),
        description=f"{summary}. {text}".strip() if text else summary,
        method=method.upper(),
        path=path,
        input_schema=_with_defs(schema_, components, used),
        path_params=tuple(located["path"]),
        query_params=tuple(located["query"]),
        body_kind=kind,
        body_fields=tuple(body) if body.keys() != {BODY_KEY} else (BODY_KEY,),
        file_fields=files,
    )


def build_tools(document: Schema) -> list[ToolSpec]:
    """Return the tools of the public API described by an OpenAPI document,
    in its order, with unique names."""
    components = document.get("components", {}).get("schemas", {})
    tools: list[ToolSpec] = []
    for path, item in document["paths"].items():
        if not path.startswith(V1_PREFIX):
            continue
        for method, spec in item.items():
            tool = build_tool(method, path, spec, components)
            if tool is not None:
                tools.append(tool)
    names = [tool.name for tool in tools]
    duplicates = {name for name in names if names.count(name) > 1}
    if duplicates:
        raise ValueError(f"duplicate tool names: {sorted(duplicates)}")
    return tools


def build_request(tool: ToolSpec, arguments: dict[str, Any]) -> ApiRequest:
    """Return the HTTP request of a call of tool with arguments; ValueError
    names a wrong argument (unknown, missing, or a file that is not there)."""
    known = set(tool.input_schema["properties"])
    unknown = sorted(set(arguments) - known)
    if unknown:
        raise ValueError(f"unknown argument(s) for {tool.name}: {', '.join(unknown)}")
    missing = [n for n in tool.input_schema.get("required", []) if n not in arguments]
    if missing:
        raise ValueError(f"missing argument(s) for {tool.name}: {', '.join(missing)}")
    url = tool.path
    for name in tool.path_params:
        url = url.replace("{" + name + "}", str(arguments[name]))
    params = {n: arguments[n] for n in tool.query_params if n in arguments}
    fields = {n: arguments[n] for n in tool.body_fields if n in arguments}
    if tool.body_kind == "json":
        body = fields[BODY_KEY] if BODY_KEY in tool.body_fields else fields
        return ApiRequest(url, params, body, None, None)
    if tool.body_kind == "multipart":
        files = {}
        for name in (n for n in tool.file_fields if n in fields):
            source = Path(str(fields.pop(name))).expanduser()
            if not source.is_file():
                raise ValueError(f"{name}: {source} is not a file")
            files[name] = (source.name, source.read_bytes())
        data = {
            n: v if isinstance(v, str) else json.dumps(v) for n, v in fields.items()
        }
        return ApiRequest(url, params, None, data, files)
    return ApiRequest(url, params, None, None, None)
