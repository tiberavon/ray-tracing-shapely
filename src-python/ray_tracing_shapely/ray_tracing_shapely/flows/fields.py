"""
Python-specific module: a flow's question, explained

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

    http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.

===============================================================================
PYTHON-SPECIFIC MODULE: fields
===============================================================================
`FieldExplanation`: a question a flow needs answered before it can go on --
what is asked, why it matters (a citation: a standard's section, or which
later step the answer feeds), and a worked example in the expected unit.
Self-contained, so a person or an agent who does not know the procedure can
answer it from the one message.

Every flow that asks questions uses it: the eye-safety intake flows and the
rayfile slicing flow. `ObservableFlow.explain_current_state()` returns its
`message` while the flow waits on that question.
===============================================================================
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional


@dataclass
class FieldExplanation:
    """One intake question, self-contained enough for a caller who does
    not already know the standard to answer correctly.

    Args:
        field: The payload field this question fills (e.g. `"alpha_rad"`).
        question: The plain-language question being asked.
        citation: Why this field matters (a standard section/boundary, or
            which downstream dispatch it feeds).
        example: A worked example value in the expected unit.
        message: A rendered sentence combining all of the above.
    """

    field: str
    question: str
    citation: str
    example: str
    message: str


def explain_field(field: str, question: str, citation: str, example: str) -> FieldExplanation:
    """Build a `FieldExplanation` for one intake field."""
    message = f"{question} ({citation}) {example}"
    return FieldExplanation(
        field=field, question=question, citation=citation, example=example, message=message,
    )


#: A question that must be answered: it has no default.
REQUIRED: Any = type("Required", (), {"__repr__": lambda self: "REQUIRED"})()

#: The kinds of answer a question can expect, and what each accepts.
FIELD_KINDS = {
    "path": "a file path, as a string",
    "quantity": 'a number with its unit, as a string: "7 mm", "0.4 mW"; a bare number is refused',
    "integer": "a whole number",
    "share_range": "two shares [low, high], 0 < low < high <= 1",
    "choice": "one of the listed choices",
    "bool": "true or false",
    "json": "any JSON value",
}


#: How a ``json`` question's answer can be asked as a form, field by field, instead of typed
#: (`ObservableFlow.question_form`). A form is plain JSON:
#:
#: - ``{"kind": "object", "fields": [field, ...]}`` answers an object: each field's value under
#:   its ``name``, a blank optional field left out;
#: - either may carry ``prompt``, the question in a form's words, shown instead of the field's
#:   (which is written for a typed answer);
#: - ``{"kind": "list", "item": form, "min": 1, "max": 2, "item_label": "axis", "add_label": ...}``
#:   answers a list of ``item`` answers;
#: - a field is ``{"name", "label", "kind", "help", "default", "optional"}``, its kind one of
#:   ``choice`` (``choices``: values, or ``{"value", "label"}``; or ``choices_by``:
#:   ``{"field": other field, "map": {that field's value: choices}}``, choices that depend on
#:   another field), ``number``, ``integer``, ``numbers`` (a list of numbers, typed with commas),
#:   ``text``, ``bool``; ``when``: ``{"field", "is": [values]}`` shows it only then; ``local``:
#:   true for a field that only shapes the form and is not part of the answer.
#:
#: The form is a convenience over the same answer: what it builds is checked by the box as any
#: typed answer is.
FORM_KINDS = ("object", "list")
FORM_FIELD_KINDS = ("choice", "number", "integer", "numbers", "text", "bool")


@dataclass(frozen=True)
class FlowField:
    """A question a flow's box asks, as data: what kind of answer it takes,
    in what unit, with what default, and why it is asked. So one verb,
    `ObservableFlow.answer(value)`, answers any box of any flow, and an
    agent reads the question without knowing the flow's methods.

    Args:
        name: The field the answer fills (``"package_width"``).
        kind: One of `FIELD_KINDS`.
        question: The question, in plain words.
        why: Why it is asked: a standard's section, or what the answer feeds.
        example: A worked example of an answer.
        unit: The expected unit, for a ``quantity``.
        default: The answer `answer_default` gives, or `REQUIRED`.
        choices: The allowed answers, for a ``choice``.
        pattern: For a ``path``, the files that fit, as a glob (``"*.scene.json"``):
            a form offers the matching files it finds, and its browser shows them.
    """

    name: str
    kind: str
    question: str
    why: str
    example: str
    unit: Optional[str] = None
    default: Any = REQUIRED
    choices: Optional[tuple] = None
    pattern: Optional[str] = None

    def __post_init__(self) -> None:
        if self.kind not in FIELD_KINDS:
            raise ValueError(f"kind must be one of {sorted(FIELD_KINDS)}, got {self.kind!r}")

    @property
    def required(self) -> bool:
        return self.default is REQUIRED

    def explanation(self, example: Optional[str] = None) -> FieldExplanation:
        """The question as a `FieldExplanation`, for `explain_current_state`."""
        return explain_field(self.name, self.question, self.why, example if example is not None else self.example)

    def coerce(self, value: Any) -> Any:
        """The answer as the box's check expects it, from what JSON can carry.
        Only the shape is handled here: the box's own check decides whether
        the answer is acceptable.

        Raises:
            ValueError: An answer of the wrong shape for this kind.
        """
        k = self.kind
        if k == "path":
            if not isinstance(value, str):
                raise ValueError(f"{self.name} takes a path as a string, got {type(value).__name__}: {value!r}")
        elif k == "integer":
            if isinstance(value, float) and value.is_integer():
                value = int(value)
            if isinstance(value, bool) or not isinstance(value, int):
                raise ValueError(f"{self.name} takes a whole number, got {value!r}")
        elif k == "share_range":
            if not isinstance(value, (list, tuple)) or len(value) != 2:
                raise ValueError(f"{self.name} takes two shares [low, high], got {value!r}")
            value = tuple(value)
        elif k == "choice":
            if value not in (self.choices or ()):
                raise ValueError(f"{self.name} takes one of {list(self.choices or ())}, got {value!r}")
        elif k == "bool":
            if not isinstance(value, bool):
                raise ValueError(f"{self.name} takes true or false, got {value!r}")
        return value

    def to_dict(self) -> Dict[str, Any]:
        """The question as JSON, for an agent: the default only when there is one."""
        d: Dict[str, Any] = {"name": self.name, "kind": self.kind, "accepts": FIELD_KINDS[self.kind],
                             "question": self.question, "why": self.why, "example": self.example,
                             "required": self.required}
        if self.unit is not None:
            d["unit"] = self.unit
        if not self.required:
            d["default"] = list(self.default) if isinstance(self.default, tuple) else self.default
        if self.choices is not None:
            d["choices"] = list(self.choices)
        if self.pattern is not None:
            d["pattern"] = self.pattern
        return d
