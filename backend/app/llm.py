"""The Claude model this app uses, in one place.

Four call sites reach the API — the roleplay conversation, the tutor, the lesson
content generator and the curriculum skeleton builder. They had drifted apart
(two pinned claude-opus-4-8, one claude-opus-5), which meant a model change was
three edits and an easy one to half-finish.

Anything that changes here changes what Jacob is billed for and how good the
answers are, so it is worth being a deliberate, single edit.
"""

from __future__ import annotations

# Current default. Everything in this app is either short-form reasoning about
# grammar or careful content authoring, both of which reward the better model.
MODEL = "claude-opus-5"


def parsed_or_raise(response, what: str):
    """A structured-output response's parsed value, or an error that says why not.

    `parsed_output` is None for two completely different reasons, and telling
    them apart is the whole point of this function. When a response is cut off
    at the token limit there is no complete JSON to parse, so the symptom is
    identical to the model returning nothing at all — and the obvious error
    message ("no valid content came back") sends you to look at your key, your
    model id and your schema, none of which are wrong.

    That cost two rounds of misdiagnosis on the curriculum skeleton builder: a
    truncated plan reported as "model returned no plan", chased as an auth
    problem. Both call sites that use structured output go through here now, so
    the diagnosis exists once and cannot drift between them.
    """
    if response.parsed_output is not None:
        return response.parsed_output

    stop = getattr(response, "stop_reason", None)
    if stop == "max_tokens":
        used = getattr(getattr(response, "usage", None), "output_tokens", "?")
        raise RuntimeError(
            f"{what}: cut off at the token limit ({used} output tokens). "
            f"Raise the max_tokens budget for this call, or ask for less at once."
        )
    raise RuntimeError(f"{what}: no valid content came back (stop_reason={stop or 'unknown'})")
