"""Checks driven by the app's OpenAPI document (tests only): the operations
of the public API, placeholder requests built from their parameters, and a
small JSON Schema validator for the schemas FastAPI/Pydantic write
($ref, anyOf/oneOf/allOf, type, enum, const, properties, required,
items/prefixItems, additionalProperties)."""

from dataclasses import dataclass
from typing import Any

from clipforge.api.app import create_app

Schema = dict[str, Any]
JSON_TYPES: dict[str, tuple[type, ...]] = {
    "object": (dict,),
    "array": (list,),
    "string": (str,),
    "integer": (int,),
    "number": (int, float),
    "boolean": (bool,),
    "null": (type(None),),
}
MISSING_ID = 987654


@dataclass(frozen=True)
class Operation:
    """One operation of the OpenAPI document."""

    method: str
    path: str
    spec: Schema

    @property
    def label(self) -> str:
        return f"{self.method.upper()} {self.path}"

    def url(self) -> str:
        """Return the path with placeholder values of its path parameters:
        an id that does not exist, or a name that does not."""
        url = self.path
        for param in self.spec.get("parameters", []):
            if param["in"] == "path":
                kind = param["schema"].get("type")
                value = MISSING_ID if kind == "integer" else "no-such-name"
                url = url.replace("{" + param["name"] + "}", str(value))
        return url

    def json_body(self) -> Any:
        """Return {} when the operation takes a JSON body, else None."""
        content = self.spec.get("requestBody", {}).get("content", {})
        return {} if "application/json" in content else None

    def response_schema(self, status: int) -> Schema | None:
        """Return the documented JSON schema of an answer with status (its
        own entry or the 4XX/5XX range), None if it has no JSON body."""
        responses = self.spec["responses"]
        entry = responses.get(str(status)) or responses.get(f"{str(status)[0]}XX")
        assert entry is not None, f"{self.label}: {status} is not documented"
        schema: Schema | None = (
            entry.get("content", {}).get("application/json", {}).get("schema")
        )
        return schema


def load_document() -> Schema:
    """Return the OpenAPI document of a fresh app (no lifespan needed)."""
    return create_app(run_worker=False, caption_previews=False).openapi()


def public_operations(document: Schema, prefix: str = "/api/v1/") -> list[Operation]:
    """Return every operation whose path starts with prefix."""
    return [
        Operation(method, path, spec)
        for path, item in document["paths"].items()
        if path.startswith(prefix)
        for method, spec in item.items()
    ]


def schema_errors(
    value: Any, schema: Schema, document: Schema, where: str = "$"
) -> list[str]:
    """Return where value breaks schema (an empty list: it conforms)."""
    if "$ref" in schema:
        name = schema["$ref"].removeprefix("#/components/schemas/")
        return schema_errors(
            value, document["components"]["schemas"][name], document, where
        )
    if "allOf" in schema:
        return [
            e
            for part in schema["allOf"]
            for e in schema_errors(value, part, document, where)
        ]
    for key in ("anyOf", "oneOf"):
        if key in schema:
            options = [
                schema_errors(value, part, document, where) for part in schema[key]
            ]
            if all(options):
                return [f"{where}: matches no option of {key}: {options}"]
            return []
    if "const" in schema and value != schema["const"]:
        return [f"{where}: {value!r} is not {schema['const']!r}"]
    if "enum" in schema and value not in schema["enum"]:
        return [f"{where}: {value!r} is not one of {schema['enum']}"]
    if "type" in schema and not _has_type(value, schema["type"]):
        return [f"{where}: {value!r} is not of type {schema['type']}"]
    if isinstance(value, dict):
        return _object_errors(value, schema, document, where)
    if isinstance(value, list):
        return _array_errors(value, schema, document, where)
    return []


def _has_type(value: Any, kinds: str | list[str]) -> bool:
    """Whether value is of one of the JSON types kinds (a bool is no number)."""
    for kind in [kinds] if isinstance(kinds, str) else kinds:
        if isinstance(value, bool) and kind in ("integer", "number"):
            continue
        if isinstance(value, JSON_TYPES[kind]):
            return True
    return False


def _object_errors(
    value: dict[str, Any], schema: Schema, document: Schema, where: str
) -> list[str]:
    errors = [
        f"{where}: {name} is required"
        for name in schema.get("required", [])
        if name not in value
    ]
    properties = schema.get("properties", {})
    extra = schema.get("additionalProperties", True)
    for name, item in value.items():
        if name in properties:
            errors += schema_errors(item, properties[name], document, f"{where}.{name}")
        elif extra is False:
            errors.append(f"{where}: {name} is not allowed")
        elif isinstance(extra, dict):
            errors += schema_errors(item, extra, document, f"{where}.{name}")
    return errors


def _array_errors(
    value: list[Any], schema: Schema, document: Schema, where: str
) -> list[str]:
    prefix = schema.get("prefixItems", [])
    errors: list[str] = []
    for index, item in enumerate(value):
        part = prefix[index] if index < len(prefix) else schema.get("items")
        if isinstance(part, dict):
            errors += schema_errors(item, part, document, f"{where}[{index}]")
    return errors
