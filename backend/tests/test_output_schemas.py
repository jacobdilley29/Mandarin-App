"""The schema we send Claude has to be one Claude accepts (spec §3.5, §3.7).

Every Claude call site in this app is tested with a stub client, because the
suite makes no API calls. A stub never validates a schema, so a schema the API
rejects passed all 366 tests — and the first real run of the content generator
came back 400 eighty times:

    output_config.format.schema: Invalid schema: Reference to non-existent
    definition: #/$defs/__main_____make_models___locals___Example-Input__1

The cause is a field named `examples`. It is a reserved JSON Schema keyword, and
pydantic emits a $ref for such a field while dropping the matching $defs entry,
so the schema references a definition that isn't there. Nothing about our own
logic is wrong, which is exactly why nothing caught it.

These tests build the schema the SDK would send — the same
TypeAdapter().json_schema() -> transform_schema() path anthropic uses in
messages.parse() — and assert every reference resolves. No key, no network, no
spend, and it fails on the real defect.
"""

from __future__ import annotations

import importlib

import pytest
from pydantic import BaseModel, TypeAdapter

from app import conversation, tutor

transform_schema = pytest.importorskip(
    "anthropic.lib._parse._transform"
).transform_schema


def _sdk_schema(model) -> dict:
    """Exactly what anthropic sends as output_config.format.schema."""
    return transform_schema(TypeAdapter(model).json_schema())


def _dangling_refs(model) -> list[str]:
    """Names this schema points at but never defines. Any is a 400."""
    schema = _sdk_schema(model)
    defined = set(schema.get("$defs", {}))
    used: set[str] = set()

    def walk(node) -> None:
        if isinstance(node, dict):
            if "$ref" in node:
                used.add(node["$ref"].rsplit("/", 1)[-1])
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for value in node:
                walk(value)

    walk(schema)
    return sorted(used - defined)


def _all_output_models() -> dict:
    """Every model this app hands to client.messages.parse(output_format=...)."""
    generate_content = importlib.import_module("scripts.generate_content")
    build_skeleton = importlib.import_module("scripts.build_skeleton")
    return {
        "tutor (ask a question)": tutor._models(),
        "conversation (roleplay turn)": conversation._models(),
        "generate_content (lesson)": generate_content._make_models(),
        "build_skeleton (level plan)": build_skeleton._theme_models(),
    }


@pytest.mark.parametrize("name", sorted(_all_output_models()))
def test_every_schema_we_send_is_self_contained(name):
    """The regression guard for the whole class of bug."""
    model = _all_output_models()[name]

    assert _dangling_refs(model) == [], (
        f"{name}: the schema references definitions it does not carry, so the "
        f"API will reject every request with a 400. A field named after a JSON "
        f"Schema keyword (`examples`) is the usual cause — rename it and map it "
        f"back when the response is applied."
    )


def test_no_output_model_uses_a_reserved_field_name():
    """Catch the cause directly, not just its symptom.

    Checked by name as well as by behaviour, because a future pydantic could
    stop producing a dangling ref while the field name stays a bad idea.
    """
    reserved = {"examples", "$defs", "properties", "definitions"}

    for name, model in _all_output_models().items():
        fields = set(TypeAdapter(model).json_schema().get("properties", {}))
        for sub in _sdk_schema(model).get("$defs", {}).values():
            fields |= set(sub.get("properties", {}))
        assert not (fields & reserved), f"{name} uses a reserved key: {fields & reserved}"


def test_a_field_called_examples_really_does_break_the_schema():
    """Records *why* the rename exists, so nobody reverts it as cosmetic."""

    class Example(BaseModel):
        hanzi: str

    class WithReservedName(BaseModel):
        examples: list[Example]

    class WithSafeName(BaseModel):
        example_sentences: list[Example]

    assert _dangling_refs(WithReservedName), "the trap this guards against is gone"
    assert _dangling_refs(WithSafeName) == []
