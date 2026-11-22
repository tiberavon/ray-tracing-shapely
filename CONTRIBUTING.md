# Contributing to Ray Tracing Shapely

Thank you for your interest in contributing! This document describes the
conventions, patterns, and architectural decisions you should follow when
working on this codebase.

## Getting Started

### Install from source (editable)

This is a monorepo publishing several independent distributions.
`src-python/<distribution>/` holds one `pyproject.toml` each, sibling to the others,
none special-cased at the repo root. Install the ones you need:

```bash
git clone https://github.com/tiberavon/ray-tracing-shapely.git
cd ray-tracing-shapely
pip install -e "src-python/ray_tracing_shapely[dev]"        # core — start here
pip install -e "src-python/ray_tracing_shapely_optiland[dev]"  # 3D verification, planning stage
pip install -e "src-python/optiland_sms[dev]"                  # Optiland SMS plugin, planning stage
```

### Run the tests

Each distribution's tests run from inside its own directory (they are independent
packages, not a single unified test tree):

```bash
cd src-python/ray_tracing_shapely && pytest ray_tracing_shapely/developer_tests/
cd src-python/ray_tracing_shapely_optiland && pytest
cd src-python/optiland_sms && pytest
```

### Notebook hygiene (run this once per machine)

Saving a notebook writes whichever kernel is locally attached into its metadata
(`kernelspec.display_name`/`name`, `language_info.version`) — since every machine
registers its Jupyter kernel under a locally chosen name, this produces a diff on
every commit that touches purely which machine last saved the file, not its content.
`nbstripout` is set up to strip this (plus execution counts and per-cell execution
timestamps, which are the same problem) at commit time, while preserving actual cell
outputs. Run this once on every machine/clone that will commit notebooks — it is
local git configuration, not something that travels with the repository on its own:

```bash
pip install nbstripout
nbstripout --install --attributes .gitattributes
git config filter.nbstripout.clean "nbstripout --keep-output"
git config filter.nbstripout.extrakeys "metadata.kernelspec metadata.language_info.version"
```

`.gitattributes` (committed) tells git which files go through the filter; the four
lines above configure *what the filter does* on this machine, and are not themselves
stored in the repository — `nbstripout --status` shows the active configuration if
you want to confirm a machine is set up correctly.

## Jupyter notebooks: the template for examples

Every example notebook is laid out the same way, so a reader (or an agent) finds
the same things in the same places, and a cell can be named in a question or a
review ("cell 2.3 fails").

The rules are chosen to agree with two tools many notebook users already work
with: **nbdev** (notebooks as source, tests and documentation) and **Quarto**
(the publishing system nbdev uses). A habit from either carries over, and a
notebook written here still works under them. Each rule below says where it
comes from: *our own* (a choice for this project, nothing outside requires it),
or the nbdev or Quarto behaviour it follows, with the page or source file that
states it, so a case these rules do not cover can be checked there (see "A case
not covered here", below). The nbdev and Quarto points were read from their
documentation and source when these rules were written; where either has since
changed, its current documentation or source is what counts.

### Sections and cells

- **Sections.** A title cell says what the notebook shows and lists its
  sections. Each section starts with a markdown heading, `## <n>. <title>`.
  **Section 0 is always housekeeping**; the notebook's own work starts at
  section 1. *Our own.*
- **One snippet per code cell, labelled.** A code cell holds one code snippet.
  Its label names the cell and the snippet: `# cell 2.1: the scene saved as a
  file` is the first code cell of section 2. A snippet too long for one cell is
  spread over several, lettered in order: `2.1a`, `2.1b`, ... Markdown cells are
  not numbered; they explain the code cell that follows. *Our own.*
- **nbdev directives come before the label.** A cell that carries directives
  (`#| hide`, `#| eval: false`) starts with them, and the label follows:

  ```python
  #| eval: false
  # cell 7.1: the MCP server, for an agent
  ```

  nbdev reads directives only from a cell's leading lines: lines that are `#|`
  directives, blank, or a `%%` cell magic. The first other line ends them, so a
  `#|` line after the label is silently ignored. *nbdev*: directives are
  described at <https://nbdev.fast.ai/explanations/directives.html>; the
  leading-lines rule is in fastcore's notebook reader, which nbdev uses
  (`fastcore/nbio.py`: `_dir_pre`, `first_code_ln`), not stated on that page.

### Section 0, housekeeping

- **Cell 0.1, the environment.** `notebook_env_check.check_venv()` compares the
  kernel with the `VIRTUAL_ENV` that the repository's `.env` names, and stops the
  notebook when they differ: a kernel attached to the wrong install on a machine
  set up for the right one. Without a `.env` (a contributor's machine, CI,
  `nbdev_test`) it warns and goes on. *Our own.*
- **Cell 0.2, the imports, checked, and the save folder.**
  - Every import the notebook needs is made here, so a missing package or extra
    fails at once, not halfway through. It prints which `ray_tracing_shapely` was
    imported, and from where. An optional section's import that needs an
    optional extra stays in that section. *Our own.*
  - The save folder is a subfolder beside the notebook, named after it:
    `notebooks/_<name>_runs/` (ignored by git through `notebooks/_*_runs/`).
    Everything the notebook writes (scene files, flow runs, transcripts) goes
    under it. The leading underscore keeps it out of a published site and out of
    nbdev's notebook search. *Quarto*: a project renders every `.qmd`, `.ipynb`
    and `.md` file in it except those with a file or directory prefix of `.` or
    `_` (<https://quarto.org/docs/projects/quarto-projects.html>, "Render
    Targets"), so a transcript written there does not become a page. *nbdev*:
    `nbglob` skips files and folders matching `^[_.]` by default
    (`nbdev/doclinks.py`).
  - The cell checks that the notebook runs from its own folder, since the save
    folder is relative to it. *nbdev*: `nbdev_test` runs each notebook in its own
    folder (`nbdev/test.py`, `working_directory(fn.parent)`), as Jupyter and VS
    Code do, so the check passes there.

```python
# cell 0.1: the environment
import sys
sys.path.insert(0, '.')  # notebook_env_check.py lives in notebooks/ alongside the notebooks

from notebook_env_check import check_venv

venv_root = check_venv()
```

```python
# cell 0.2: the imports, checked, and the save folder
from pathlib import Path

import ray_tracing_shapely
from ray_tracing_shapely.core.scene import Scene
# ... every other import the notebook uses

print('ray_tracing_shapely', ray_tracing_shapely.__version__, 'from', Path(ray_tracing_shapely.__file__).parent)

NOTEBOOK = 'my_example'                                   # this notebook's file name, without .ipynb
assert (Path.cwd() / f'{NOTEBOOK}.ipynb').exists(), f'run this notebook from its own folder, not {Path.cwd()}'
RUNS = Path.cwd() / '_my_example_runs'                   # the save folder: beside the notebook, named after it
RUNS.mkdir(exist_ok=True)
```

### Checks, optional sections, long steps

- **A check is an `assert`.** A cell that compares a result with a reference (a
  hand calculation, a datasheet value) ends with an `assert` on the difference,
  not only a printed table, so a regression fails the run. *nbdev*: a notebook is
  its own test, and a cell that raises fails `nbdev_test`, which runs every
  cell and stops at the first exception (`nbdev/test.py`, `run_all(...,
  exc_stop=True)`); `nbconvert --execute` fails the same way.
- **An optional section is off by default.** It comes last; its cell has a flag
  the reader sets (`START_MCP = False`) and the directive `#| eval: false`, so
  neither `nbdev_test` nor a documentation build runs it. *Our own* (the flag);
  *nbdev* (the directive, on its directives page).
- **A step over a minute runs as a flow or a job**, and the notebook waits on the
  run's record (`flow.wait`), never on a process list. *Our own.*
- **The last cell names the notebook's kind** for the documentation
  (`-> tag: how-to`). *Our own.*

### The notebook is the source

The notebook is what is edited and reviewed, as in nbdev. A notebook may be
*first* written by a generator script beside it, `notebooks/_gen_<name>_nb.py`
(useful when an agent writes it), and executed with
`python -m jupyter nbconvert --to notebook --execute --inplace <notebook>`. Once
anyone edits the notebook by hand, the generator stops being run: delete it, or
say in its docstring that the notebook has moved on. Running it would overwrite
the edits. *nbdev*: notebooks are the source
(<https://nbdev.fast.ai/>); the `_` prefix keeps the generator out of nbdev's
search (`nbglob`, above).

A file name that starts with `_` or `.` is skipped by nbdev and by Quarto, so a
notebook meant to be tested or published never starts with one.

### Papermill templates: a notebook run once per point

A sweep over independent points runs one notebook, the *template*, once per
point with **papermill**, each run in a fresh kernel with its own output notebook.
A template is an example notebook first: everything above applies, plus the
rules below. The driver that runs it follows its own rules, after them.
Papermill's usage is described at
<https://papermill.readthedocs.io/en/latest/usage-parameterize.html> and
<https://papermill.readthedocs.io/en/latest/usage-execute.html>; the behaviour
cited below was checked against papermill 2.7, in its source
(`papermill/execute.py`, `parameterize.py`, `clientwrap.py`) and on a test
sweep.

**The template.**
- **Its file name ends `_template_pm`** (before the extension), so a template is told from an example
  at a glance. *Our own.*
- **It runs as it is, with its defaults.** Executed on its own (nbconvert,
  `nbdev_test`) it is the run at its default point, and that is its test.
  *papermill*: the defaults are the tagged cell's values, used when a parameter
  is not given.
- **Cell 0.3 holds the parameters, and only them.** It is labelled like any
  cell (`# cell 0.3: the parameters`) and carries the cell tag `parameters` (a
  tag in the cell's metadata, not a `#|` directive, so it does not conflict with
  nbdev). It holds one literal assignment a line, each with a comment saying
  what it is and its unit; no imports, no computation. *papermill*: the values
  of a run are injected as a new cell, tagged `injected-parameters`, placed right
  after the tagged cell, so a value computed *inside* the tagged cell from a
  default would keep the default; anything derived goes in a later cell. The
  trailing comment is what `papermill.inspect_notebook` reports as the
  parameter's help.
- **Parameter names start `ip_`** (input parameter), so a swept value is told
  from the notebook's own variables. *Our own* (the existing templates' practice).
- **The physical parameters are kept apart from the numerical ones**, in two
  groups in the cell, and saved apart in the run (`persist_run_artifacts`:
  `physical_params`, `numerical_params`), so a comparison across points can tell
  a change in the device from a change in the simulation. *Our own.*
- **Cell 0.4 sets the save folder from a parameter.** Cell 0.3 has
  `ip_run_dir = None`; cell 0.4 sets `RUNS` to it when the driver gives one, and
  to the notebook's own `_<name>_runs/` folder otherwise. The save folder moves
  from cell 0.2 to cell 0.4 in a template because it depends on a parameter.
  *Our own.*
- **A point that cannot be computed fails loudly.** A check is an `assert`, as
  above, and the template does not catch its own errors: the driver needs the
  error to record the point as failed. *papermill*: a run fails only when a cell
  raises.

**The driver.** A script in `papermill_scripts/`, one per sweep. *Our own*
(the existing drivers' place).
- **A failing point does not stop the sweep.** Each `execute_notebook` call is
  wrapped: `except papermill.PapermillExecutionError` (a cell raised) and
  `except Exception` (the kernel died, a cell timed out: `nbclient`'s
  `DeadKernelError`, `CellTimeoutError`) each record the point as failed, and
  the loop goes on. *papermill*: a cell that raises stops *that* notebook at the
  failing cell, the output notebook is written with the traceback and a red
  banner at its top (later cells not run), and `PapermillExecutionError` is
  raised, naming the cell; the next point starts in a fresh kernel, so it is not
  affected. `report_mode=True` does **not** make papermill carry on after an
  error: it only hides the code cells in the output notebook.
- **The parameter names are checked before the first point.** The driver reads
  the names assigned in the template's `parameters` cell and refuses a name not
  among them. *papermill*: an unknown name only logs "Passed unknown parameter"
  and is injected anyway, so a misspelt name sweeps nothing and fails nothing.
- **The kernel and the language are named** (`kernel_name=`, `language=`).
  *Our own, because of nbstripout*: committed notebooks have their kernel
  metadata stripped (see "Notebook hygiene"), and papermill refuses a notebook
  that names neither a kernel nor a language and is given neither ("No language
  found in notebook and no override provided"; `inspect_notebook`, which takes no
  override, refuses it too).
- **The notebook runs in its own folder** (`cwd=` the template's folder), so
  section 0's checks pass and relative paths resolve. *papermill*: `cwd` is the
  directory the notebook is executed in; by default it is the driver's.
- **Each point has its own folder**, `notebooks/_<template>_runs/<sweep>/<point>/`,
  passed as `ip_run_dir`; its output notebook is written there. *Our own.*
- **Every path the driver passes is absolute.** The notebook runs in its own
  folder, not the driver's, so a relative `ip_run_dir` would be read from there
  (`notebooks/notebooks/...`). *Our own*, following from `cwd=` above.
- **A hung point is bounded** with `execution_timeout=` (seconds a cell).
  *papermill*: passed to nbclient as the cell timeout.
- **The sweep leaves a record**: a `summary.json` in the sweep's folder, one
  entry a point (its parameters, `ok` or `failed`, the error, its output
  notebook), rewritten after every point so a sweep stopped halfway still says
  what ran. The script exits non-zero when any point failed. *Our own.*
- **A sweep expected to take over a minute is started as a job** (on this
  machine, `LocalProcessExecutor`) and followed through its record, not left
  running in a terminal. *Our own* (the long-jobs rule). A sweep of a saved
  scene's parameter is better run by the `parameter_study` flow, a job a point,
  than by papermill.

```python
# the core of a driver: one point after another, a failure recorded, the loop going on
import ast, json
from pathlib import Path

import nbformat
import papermill as pm

TEMPLATE = Path("notebooks/my_example_template_pm").with_suffix(".ipynb").resolve()  # absolute: the run's cwd is its folder
SWEEP = TEMPLATE.parent / "_my_example_template_pm_runs" / "n_sample_sweep"
points = [{"ip_n_sample": n} for n in (1.33, 1.40, 1.47)]

cell = next(c for c in nbformat.read(TEMPLATE, 4).cells if "parameters" in c.metadata.get("tags", []))
known = {t.id for node in ast.parse(cell.source).body if isinstance(node, ast.Assign) for t in node.targets}
unknown = {k for p in points for k in p} - known
assert not unknown, f"not parameters of {TEMPLATE.name}: {sorted(unknown)}"

summary = []
for i, params in enumerate(points):
    run_dir = SWEEP / f"point_{i:03d}"
    run_dir.mkdir(parents=True, exist_ok=True)
    output = (run_dir / "run").with_suffix(".ipynb")                   # the point's executed notebook
    entry = {"point": i, "parameters": params, "notebook": str(output)}
    try:
        pm.execute_notebook(TEMPLATE, output, parameters={**params, "ip_run_dir": str(run_dir)},
                            kernel_name="python3", language="python", cwd=TEMPLATE.parent, execution_timeout=600, progress_bar=False)
        entry["status"] = "ok"
    except pm.PapermillExecutionError as exc:      # a cell raised: the notebook stopped there
        entry.update(status="failed", error=f"cell {exc.cell_index}: {exc.ename}: {exc.evalue}")
    except Exception as exc:                       # the kernel died, a cell timed out
        entry.update(status="failed", error=f"{type(exc).__name__}: {exc}")
    summary.append(entry)
    (SWEEP / "summary.json").write_text(json.dumps(summary, indent=1))

raise SystemExit(1 if any(e["status"] == "failed" for e in summary) else 0)
```

### A case not covered here

Before asking, check it in this order:
1. **This section.** A rule marked *our own* is settled here; change it here,
   not in one notebook.
2. **nbdev**, for anything about cells, directives, tests and notebooks as
   source: <https://nbdev.fast.ai/> (the directives page above), and where the
   documentation is silent, its source (`nbdev/`, and `fastcore/nbio.py` for how
   cells and directives are read).
3. **papermill**, for anything about a template's parameters and how a run
   executes or fails: its usage pages above, and its source (`papermill/`).
4. **Quarto**, for anything about what a published site includes or how a page
   renders: <https://quarto.org/docs/projects/quarto-projects.html>.

If one of them settles it and nothing here contradicts it, it is allowed. If
they disagree with each other, or with a rule here, ask.

## Project Layout

```
src-python/
    ray_tracing_shapely/                    # core distribution
        pyproject.toml
        ray_tracing_shapely/
            core/               # Simulation engine (scene, rays, objects, renderer)
            analysis/           # Python-specific analysis utilities
                glass_geometry.py          # Edge descriptions, interfaces, boundaries
                ray_geometry_queries.py    # Spatial queries (rays vs. geometry)
                saving.py                  # CSV/XML export, ray filtering, statistics
                simulation_result.py       # SimulationResult container
                lineage_analysis.py        # Post-hoc ray tree analysis
                fresnel_utils.py           # Standalone Fresnel equation utilities
                agentic_tools.py           # JSON-serializable wrappers for LLM APIs
                tool_registry.py           # Tool discovery registry
            optical_elements/   # Prism design helpers
            examples/           # Example simulations
            developer_tests/    # Development tests
    ray_tracing_shapely_optiland/           # 3D verification satellite (planning stage)
        pyproject.toml
        ray_tracing_shapely_optiland/
        tests/
    optiland_sms/                           # Optiland sequential surface plugin (optiland-sms)
        pyproject.toml
        optiland_sms/
        tests/
dev_doc/architecture/       # Current-state component/port/contract catalogue
dev_doc/concepts/           # Why the code has the shape it has
```

## Coding Conventions

### Type annotations

Use full type annotations on all public functions and methods. Avoid `Any`
unless there is no practical alternative.

```python
def find_rays_inside_glass(segments: List[Ray], glass_obj: Glass) -> List[Ray]:
    ...
```

Use `TYPE_CHECKING` blocks for imports that are only needed by annotations,
to avoid circular imports at runtime:

```python
from __future__ import annotations
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..core.scene import Scene
```

### Method return conventions

- **Action methods** (methods that change state) return `bool` — `True` on
  success, `False` on failure.
- **Query methods** return the natural type for the data (a list, a dict, a
  float, etc.).

### Geometry conventions

- All glass polygons use **counter-clockwise (CCW) vertex ordering**, following
  the Shapely convention.
- Glass edges use a **dual-labeling system**: functional labels
  (rotation-invariant, e.g. `"entry_face"`) and cardinal labels
  (scene-orientation-dependent, e.g. `"N"`, `"SE"`).

### Floating-point safety

Always clamp the argument to `[-1.0, 1.0]` before calling `math.acos()`.
Floating-point dot products can produce values slightly outside that range
(e.g. `1.0000000000000002`), causing `ValueError: math domain error`:

```python
import math
angle = math.acos(max(-1.0, min(1.0, dot_product)))
```

## Agentic Tools — Conventions for LLM-Facing Code

The `analysis/agentic_tools.py` module provides wrappers that are designed
for use with LLM tool-use APIs (Claude API, claudette, langchain, etc.).
These wrappers sit between the LLM agent and the core analysis functions.

If you add or modify agentic tool functions, follow the conventions below.

### Structured error responses (mandatory)

Agentic tool functions **must not raise exceptions to the caller**. The
underlying analysis functions may raise freely — the agentic layer catches
and transforms exceptions into structured error dicts.

Every agentic tool returns a `dict` with a `"status"` key:

```python
# Success
{"status": "ok", "data": <result>}

# Failure
{"status": "error", "message": "No object named 'Prism1'. Available: ['Main Prism']"}
```

#### Pattern

```python
def some_agentic_tool(param: str) -> dict:
    """One-line description for the LLM agent."""
    try:
        result = underlying_analysis_function(param)
        return {"status": "ok", "data": result}
    except (ValueError, KeyError) as e:
        return {"status": "error", "message": str(e)}
    except RuntimeError as e:
        return {"status": "error", "message": str(e)}
```

#### Rationale

Different frameworks handle Python exceptions differently — claudette
returns the traceback to the LLM, raw API usage crashes the application,
langchain depends on its error handler. A structured dict is universally
safe and gives the agent enough information to recover (e.g. by listing
available object names in the error message).

#### What to catch

- `ValueError` — invalid parameter values (bad glass name, out-of-range
  angle, unknown edge label).
- `KeyError` — missing keys when resolving names or labels.
- `RuntimeError` — context not set, or other precondition failures.

Let unexpected errors (`TypeError`, `AttributeError`, etc.) propagate — they
indicate bugs, not user mistakes.

### JSON-serializable inputs and outputs

All parameters must be JSON-serializable types: `str`, `int`, `float`,
`bool`, or `list`/`dict` of these. No Python objects (Scene, Glass, Ray)
in the signature.

All return values must be JSON-serializable. Use `dict` or `list[dict]`
rather than dataclasses, XML strings, or custom objects.

### Context resolution

Agentic tools resolve live Python objects (scenes, segments) from the
module-level `_CONTEXT` dict, which is populated by `set_context()` or
`set_context_from_result()`. Tools should call `_require_context()` to get
the scene and segments, and return a structured error if the context is not
set.

### Discoverable parameter values

When an agentic tool fails because a parameter value is invalid, the error
message should include the valid alternatives when possible:

```python
# Good
{"status": "error", "message": "No object named 'Prism1'. Available: ['Main Prism', 'Lens A']"}

# Bad
{"status": "error", "message": "Object not found"}
```

This helps the LLM agent self-correct without needing a separate discovery
tool call.

## Commit Messages

Write concise commit messages that focus on the *why*, not the *what*. Use
the imperative mood ("add feature", not "added feature").

## License

By contributing, you agree that your contributions will be licensed under the
Apache License 2.0, consistent with the project license.
