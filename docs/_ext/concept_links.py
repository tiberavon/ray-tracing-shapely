"""Sphinx extension: turn concept and contract citations into links.

The code's docstrings cite concepts as ``[KA9: clause]`` and contracts as
``C-EYE-04`` (see dev_doc/architecture/02_conventions.md
and §4.1). Rendered as plain text those are informative; rendered as links
they make the API reference the front door to the reasoning. This transform
walks every document after parsing and replaces both patterns with
cross-references to the copied concept and contract pages.

Two cases are handled:

- A ``Text`` node containing ``[KA9: clause]`` or ``C-EYE-04`` anywhere in
  running prose (this is what autodoc produces from a docstring).
- A ``literal`` node whose whole content is a key — the `` `KA9` `` form the
  architecture pages use — is wrapped in a reference, keeping the literal.

The key -> docname map is built once per build from the files actually
present under ``explanation/concepts`` and ``reference/architecture/contracts``,
so a key with no page is left as plain text and reported once.
"""
from __future__ import annotations

import re
from pathlib import Path

from docutils import nodes
from sphinx import addnodes
from sphinx.transforms import SphinxTransform
from sphinx.util import logging

logger = logging.getLogger(__name__)

CONCEPT_RE = re.compile(r"\[(K[A-D]\d+)(?::\s*([^\]]*?))?\]")
CONTRACT_RE = re.compile(r"\b(C-[A-Z0-9]+-\d{2})\b")
BARE_KEY_RE = re.compile(r"^(K[A-D]\d+|C-[A-Z0-9]+-\d{2})$")

_SKIP_PARENTS = (
    nodes.literal_block, nodes.raw, nodes.comment, nodes.reference,
    addnodes.pending_xref, nodes.title, nodes.FixedTextElement,
)


def _build_map(app) -> dict[str, str]:
    src = Path(app.srcdir)
    mapping: dict[str, str] = {}
    for f in (src / "explanation" / "concepts").glob("K[A-D]*_*.md"):
        mapping[f.name.split("_", 1)[0]] = "/explanation/concepts/" + f.stem
    for f in (src / "reference" / "architecture" / "contracts").glob("C-*.md"):
        mapping[f.stem] = "/reference/architecture/contracts/" + f.stem
    return mapping


def _xref(target: str, label_node: nodes.Node) -> addnodes.pending_xref:
    ref = addnodes.pending_xref(
        "", refdomain="std", reftype="doc", reftarget=target,
        refexplicit=True, refwarn=True,
    )
    ref += label_node
    return ref


class ConceptLinks(SphinxTransform):
    default_priority = 750

    def apply(self, **kwargs):
        mapping = getattr(self.env, "_concept_link_map", None)
        if not mapping:
            return
        missing: set[str] = getattr(self.env, "_concept_link_missing", set())

        # Case 2 first: a literal whose whole text is a key.
        for lit in list(self.document.findall(nodes.literal)):
            if isinstance(lit.parent, (nodes.reference, addnodes.pending_xref)):
                continue
            m = BARE_KEY_RE.match(lit.astext().strip())
            if not m:
                continue
            key = m.group(1)
            if key in mapping:
                lit.replace_self(_xref(mapping[key], lit.deepcopy()))
            else:
                missing.add(key)

        # Case 1: keys inside running text.
        for text in list(self.document.findall(nodes.Text)):
            parent = text.parent
            if parent is None or isinstance(parent, _SKIP_PARENTS) or isinstance(parent, nodes.literal):
                continue
            s = str(text)
            if "[K" not in s and "C-" not in s:
                continue
            pieces = self._split(s, mapping, missing)
            if pieces is not None:
                text.parent.replace(text, pieces)

        self.env._concept_link_missing = missing

    @staticmethod
    def _split(s: str, mapping: dict[str, str], missing: set[str]):
        out: list[nodes.Node] = []
        pos = 0
        changed = False
        spans = []
        for m in CONCEPT_RE.finditer(s):
            spans.append((m.start(), m.end(), m.group(1), m.group(2), True))
        for m in CONTRACT_RE.finditer(s):
            spans.append((m.start(), m.end(), m.group(1), None, False))
        spans.sort()
        last_end = -1
        for start, end, key, clause, is_concept in spans:
            if start < last_end:
                continue
            if key not in mapping:
                missing.add(key)
                continue
            if start > pos:
                out.append(nodes.Text(s[pos:start]))
            if is_concept:
                label = f"{key}: {clause}" if clause else key
                out.append(_xref(mapping[key], nodes.inline(label, label, classes=["concept-ref"])))
            else:
                out.append(_xref(mapping[key], nodes.literal(key, key)))
            pos = end
            last_end = end
            changed = True
        if not changed:
            return None
        if pos < len(s):
            out.append(nodes.Text(s[pos:]))
        return out


def _on_builder_inited(app):
    app.env._concept_link_map = _build_map(app)
    app.env._concept_link_missing = set()
    logger.info("concept_links: %d keys resolvable", len(app.env._concept_link_map))


def _on_build_finished(app, exception):
    missing = getattr(app.env, "_concept_link_missing", set())
    if missing:
        logger.warning("concept_links: cited but no page: %s", ", ".join(sorted(missing)))


def setup(app):
    app.connect("builder-inited", _on_builder_inited)
    app.connect("build-finished", _on_build_finished)
    app.add_transform(ConceptLinks)
    return {"version": "0.1", "parallel_read_safe": False}
