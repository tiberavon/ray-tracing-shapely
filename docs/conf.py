"""Sphinx configuration for ray_tracing_shapely.

Three things happen here beyond ordinary configuration, all before Sphinx
reads a single source file:

1. ``dev_doc/concepts/`` and ``dev_doc/architecture/`` are copied into the
   docs tree (``explanation/concepts``, ``reference/architecture``). The
   copies are build artefacts and are gitignored: ``dev_doc/`` is the one
   source, and the published set is exactly the two trees
   Both trees ship; the private roadmap tree does not.
   Symlinks would have been simpler and were rejected because the primary
   development machine is Windows, where a git symlink is a text file
   unless the checkout was configured for it.
2. Concept files carry their title in front matter and no H1; a heading
   ``# KA1 — <title>`` is injected into each copy so the key is the first
   thing on the page.
3. One API page per module is generated under ``reference/api``. A private
   name is documented if and only if a published page cites it — the list
   is derived by grepping the two trees for backticked underscore names.
"""
from __future__ import annotations

import importlib
import pkgutil
import re
import shutil
import sys
from pathlib import Path

DOCS = Path(__file__).resolve().parent
ROOT = DOCS.parent
DEV_DOC = ROOT / "dev_doc"
SRC = ROOT / "src-python"

sys.path.insert(0, str(DOCS / "_ext"))
for pkg_dir in ("ray_tracing_shapely", "ray_tracing_shapely_optiland"):
    sys.path.insert(0, str(SRC / pkg_dir))

# ---------------------------------------------------------------------------
# 1. Include the two published trees at build time
# ---------------------------------------------------------------------------
_TREES = {
    DEV_DOC / "concepts": DOCS / "explanation" / "concepts",
    DEV_DOC / "architecture": DOCS / "reference" / "architecture",
}
_FRONT = re.compile(r"\A---\n(.*?)\n---\n", re.S)


def _copy_trees() -> None:
    for src, dst in _TREES.items():
        if dst.exists():
            shutil.rmtree(dst)
        shutil.copytree(src, dst, ignore=shutil.ignore_patterns("*.pyc", "__pycache__"))
    # 2. Inject "# KEY — title" into each concept copy.
    for f in (DOCS / "explanation" / "concepts").glob("K[A-D]*_*.md"):
        text = f.read_text(encoding="utf-8")
        m = _FRONT.match(text)
        if not m:
            continue
        fm = m.group(1)
        key = re.search(r"^key:\s*(\S+)", fm, re.M)
        title = re.search(r"^title:\s*(.+)$", fm, re.M)
        if key and title:
            body = text[m.end():]
            f.write_text(f"{m.group(0)}\n# {key.group(1)} — {title.group(1).strip()}\n{body}", encoding="utf-8")


_copy_trees()

# ---------------------------------------------------------------------------
# 3. Generate one API page per module
# ---------------------------------------------------------------------------
_PRIVATE_CITED = sorted({
    m.group(1)
    for tree in _TREES
    for f in tree.rglob("*.md")
    for m in re.finditer(r"`(_[A-Za-z][A-Za-z0-9_]*)`", f.read_text(encoding="utf-8"))
})
_SKIP = ("developer_tests", "examples", "tests", "__pycache__")


def _modules(pkg_name: str) -> list[tuple[str, bool]]:
    """(module name, is_package) pairs, without importing anything but the root."""
    pkg = importlib.import_module(pkg_name)
    names = [(pkg_name, True)]
    for info in pkgutil.walk_packages(pkg.__path__, prefix=pkg_name + "."):
        if any(s in info.name for s in _SKIP):
            continue
        names.append((info.name, info.ispkg))
    return sorted(names)


def _private_members_for(modname: str) -> list[str]:
    try:
        mod = importlib.import_module(modname)
    except Exception:
        return []
    return [n for n in _PRIVATE_CITED if hasattr(mod, n)]


def _generate_api() -> None:
    api = DOCS / "reference" / "api"
    if api.exists():
        shutil.rmtree(api)
    api.mkdir(parents=True)
    index = ["# API reference", "",
             "One page per module, generated from the docstrings. A citation like",
             "`[KA9: …]` in a docstring is a link to the concept that explains the",
             "code it sits in; `C-EYE-04` is a link to the contract that states what",
             "must hold there. A private name appears here only when a published",
             "page cites it.", "", "```{toctree}", ":maxdepth: 1", ""]
    for pkg_name in ("ray_tracing_shapely", "ray_tracing_shapely_optiland"):
        try:
            mods = _modules(pkg_name)
        except Exception as e:  # satellite may be uninstallable in some builds
            print(f"[conf.py] skipping {pkg_name}: {e}", file=sys.stderr)
            continue
        for mod, is_package in mods:
            page = api / (mod + ".md")
            priv = _private_members_for(mod)
            if is_package:
                # A package's __all__ re-exports its submodules' names; documenting
                # them here would duplicate every one. Show the package docstring
                # and let each submodule document its own members once.
                opts = ["   :no-members:"]
            else:
                opts = ["   :members:", "   :undoc-members:", "   :show-inheritance:"]
                if priv:
                    opts.append("   :private-members: " + ", ".join(priv))
            page.write_text(
                f"# `{mod}`\n\n```{{eval-rst}}\n.. automodule:: {mod}\n" + "\n".join(opts) + "\n```\n",
                encoding="utf-8",
            )
            index.append(mod)
    index += ["```", ""]
    (api / "index.md").write_text("\n".join(index), encoding="utf-8")


_generate_api()

# ---------------------------------------------------------------------------
# Ordinary Sphinx configuration
# ---------------------------------------------------------------------------
project = "ray_tracing_shapely"
author = "Michele Benedetto"
copyright = "2026, Tiberavon Ltd"

extensions = [
    "myst_parser",
    "sphinx_design",
    "sphinx.ext.autodoc",
    "sphinx.ext.napoleon",
    "sphinx.ext.viewcode",
    "concept_links",
]

myst_enable_extensions = ["colon_fence", "deflist", "tasklist"]
myst_heading_anchors = 3
source_suffix = {".md": "markdown", ".rst": "restructuredtext"}
exclude_patterns = ["_build", "Thumbs.db", ".DS_Store", "**/README.md"]

# Docstrings use single backticks for code, markdown-style. In reStructuredText
# that is "interpreted text" and would render as emphasis; make it code.
default_role = "literal"

autodoc_member_order = "bysource"
autodoc_typehints = "description"
autodoc_mock_imports = []
for _optional in ("optiland", "trame", "trame_vtk", "trame_vuetify", "vtk", "pyvista", "mcp", "graphviz", "transitions"):
    try:
        importlib.import_module(_optional)
    except Exception:
        autodoc_mock_imports.append(_optional)

napoleon_google_docstring = True
napoleon_numpy_docstring = False
napoleon_use_ivar = True

html_theme = "furo"
html_title = "ray_tracing_shapely"
html_static_path = []

suppress_warnings = ["myst.header", "myst.xref_missing"]
