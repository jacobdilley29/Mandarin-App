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
