"""
Python-specific module: rayfile slicing flow
Copyright 2026 ray-tracing-shapely authors and contributors

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
RAYFILE SLICING FLOW -- choosing the limit on h for a 2D section, as a table
===============================================================================
A slice of a rayfile keeps the rays whose line passes within ``max_offset_mm``
of the axis (``slice_rayfile``). Choosing that limit is a design decision:
how much of the LED's light a 2D design may leave out. For a multi-die
package most of the light is skew, so the choice matters, and it is made
from a table: for a series of limits, how much flux each keeps.

This flow builds that table. It asks for what it needs, one question at a
time, checks the answers against the rayfile, and slices:

    start -> awaiting_rayfile -> reading_rayfile
          -> awaiting_package_width -> awaiting_package_length
          -> checking_dimensions -> awaiting_n_slices -> awaiting_kept_range
          -> slicing -> awaiting_choice -> awaiting_profile -> writing_profile
          -> done

- **reading_rayfile** parses the file (``read_rayfile``). A file that does
  not parse goes back to ``awaiting_rayfile``, with the reason.
- **The package's footprint** decides the limits. No ray of the package
  can pass the axis further than the footprint's half diagonal, so the
  limits are that half diagonal in ``n_slices`` equal steps (10 by
  default). Lengths come as quantities (``"7 mm"``), never bare numbers,
  as in the eye-safety intake.
- **checking_dimensions** refuses a footprint the rays' start points do not
  fit in: a wrong size, or a file not in mm. It goes back to
  ``awaiting_package_width``, with the extent the rays span. It warns, and
  goes on, when the start points cover little of the footprint or their
  flux centroid sits off the axis.
- **The kept range** (50% to 75% of the flux by default) is the band the
  decision is usually made in. The flow reports the limit at each end of it
  exactly (the flux-weighted quantiles of |h|) and marks the rows inside it;
  it does not choose.
- **slicing** slices at every limit and tabulates: rays kept, flux kept,
  kept and skew share, and the share of the kept flux within 30 degrees of
  the axis beside the LED's own, the check that the kept rays leave as the
  LED's light does.
- **awaiting_choice** asks for the choice, made from the table (which the
  question's context carries): a kept share (``0.6``), whose limit is then
  the exact flux-weighted quantile of |h|, or a limit on h (``"0.8 mm"``).
  The flow records the limit and the share it keeps.
- **awaiting_profile** asks where the source goes: ``false`` (the default)
  for nowhere, or a ``profile.json`` (schema 1.4 or later) and the source's
  name and placement in the 2D scene. **writing_profile** writes the
  ``rayfile`` source spec (``source_spec``) into the profile's ``sources``,
  replacing one of the same name, the rayfile's path relative to the
  profile's folder. It is always entered, and says when there is nothing to
  write; a profile it cannot write sends the flow back, with the reason.

The machine is ``flows.ObservableFlow``, the one the eye-safety flows use:
every move is an event in ``events.jsonl``, ``state.svg`` shows the current
box, ``reset`` restarts from ``start``, and ``explain_current_state()`` says
what each box is asking. It needs the ``flows`` extra (``transitions``) and
``radiometry`` (pint, for the checked lengths), which is why ``sources`` does
not import it.

The axis is the rayfile's z axis through its origin, as for
``slice_rayfile``; the table does not depend on where the slice is placed
in the 2D scene.
===============================================================================
"""

from __future__ import annotations

import json
import math
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np

from ...flows.fields import FlowField, explain_field
from ...flows.flow_base import ObservableFlow
from ..units import checked_scalar
from ..units import LENGTH
from .rayfile import Rayfile, read_rayfile
from .rayfile_slice import slice_rayfile
from .source_spec import profile_sources

#: Start points may lie this far outside the footprint (rounding, a rim): mm, and share of the half width.
FOOTPRINT_TOLERANCE_MM = 0.05
FOOTPRINT_TOLERANCE_SHARE = 0.02
#: Start points spanning less than this share of the footprint draw a warning.
SMALL_SPAN_SHARE = 0.25
#: A flux centroid further than this share of the half diagonal from the axis draws a warning.
OFF_AXIS_SHARE = 0.05
#: The angle the kept rays' spread is checked at.
WITHIN_DEG = 30.0

#: The question each asking box puts, in order.
RAYFILE_SLICING_FIELDS: Dict[str, FlowField] = {
    "awaiting_rayfile": FlowField(
        "rayfile", "path",
        "Which rayfile? (IES TM-25, positions in mm, the LED's axis along z)",
        "parsed by read_rayfile; the axis is the file's z axis through its origin",
        'e.g. "rayfile_LED_100k.TM25RAY"'),
    "awaiting_package_width": FlowField(
        "package_width", "quantity",
        "What is the package's width, along the rayfile's x?",
        "with the length, the footprint: its half diagonal is the largest limit on h",
        'e.g. "7 mm"', unit="mm"),
    "awaiting_package_length": FlowField(
        "package_length", "quantity",
        "What is the package's length, along the rayfile's y?",
        "with the width, the footprint: its half diagonal is the largest limit on h",
        'e.g. "7 mm"', unit="mm"),
    "awaiting_n_slices": FlowField(
        "n_slices", "integer",
        "How many limits on h, in equal steps up to the half diagonal?",
        "one row of the table each",
        "e.g. 10 (the default)", default=10),
    "awaiting_kept_range": FlowField(
        "kept_range", "share_range",
        "Within what range of kept flux will the limit be chosen?",
        "the flow reports the limit at each end and marks the rows inside; it does not choose",
        "e.g. [0.5, 0.75] (the default)", default=(0.5, 0.75)),
    "awaiting_choice": FlowField(
        "choice", "json",
        "Which limit on h? A kept share (a number, 0 < share <= 1), or a limit as a length (a string with "
        "its unit). The table is in the question's context.",
        "a share's limit is the exact flux-weighted quantile of |h|; the limit is what a 2D section keeps",
        'e.g. 0.6 (keep 60% of the flux), or "0.8 mm"'),
    "awaiting_profile": FlowField(
        "profile", "json",
        "Write the source into a profile.json? false for no; or {\"path\": the profile.json (schema 1.4 or "
        "later), \"name\": the source's name, \"position\": [a, b] in mm in the 2D scene, \"direction_deg\": "
        "the LED's axis, from +a towards +b, optionally \"roll_deg\"}.",
        "the profile hands the source, with its slice, to the 2D and 3D builds (source_spec)",
        'e.g. false, or {"path": "collimator/profile.json", "name": "LED", "position": [0, 0], '
        '"direction_deg": 90}', default=False),
}

#: The fields a profile answer takes: required, and optional with their defaults.
_PROFILE_KEYS = ("path", "name", "position", "direction_deg")
_PROFILE_OPTIONAL = {"roll_deg": 0.0}
#: The first profile schema with the ``rayfile`` source kind.
_RAYFILE_SCHEMA = (1, 4)


RAYFILE_SLICING_STATES = [
    "start",
    "awaiting_rayfile",
    "reading_rayfile",
    "awaiting_package_width",
    "awaiting_package_length",
    "checking_dimensions",
    "awaiting_n_slices",
    "awaiting_kept_range",
    "slicing",
    "awaiting_choice",
    "awaiting_profile",
    "writing_profile",
    "done",
]

RAYFILE_SLICING_TRANSITIONS = [
    {"trigger": "begin", "source": "start", "dest": "awaiting_rayfile"},
    {"trigger": "provide_rayfile", "source": "awaiting_rayfile", "dest": "reading_rayfile",
     "before": "_provide_rayfile"},
    {"trigger": "_advance", "source": "reading_rayfile", "dest": "awaiting_package_width",
     "conditions": "_rayfile_read"},
    {"trigger": "_advance", "source": "reading_rayfile", "dest": "awaiting_rayfile"},
    {"trigger": "provide_package_width", "source": "awaiting_package_width", "dest": "awaiting_package_length",
     "before": "_provide_package_width"},
    {"trigger": "provide_package_length", "source": "awaiting_package_length", "dest": "checking_dimensions",
     "before": "_provide_package_length"},
    {"trigger": "_advance", "source": "checking_dimensions", "dest": "awaiting_n_slices",
     "conditions": "_dimensions_fit"},
    {"trigger": "_advance", "source": "checking_dimensions", "dest": "awaiting_package_width"},
    {"trigger": "provide_n_slices", "source": "awaiting_n_slices", "dest": "awaiting_kept_range",
     "before": "_provide_n_slices"},
    {"trigger": "provide_kept_range", "source": "awaiting_kept_range", "dest": "slicing",
     "before": "_provide_kept_range"},
    {"trigger": "_advance", "source": "slicing", "dest": "awaiting_choice"},
    {"trigger": "provide_choice", "source": "awaiting_choice", "dest": "awaiting_profile",
     "before": "_provide_choice"},
    {"trigger": "provide_profile", "source": "awaiting_profile", "dest": "writing_profile",
     "before": "_provide_profile"},
    {"trigger": "_advance", "source": "writing_profile", "dest": "done", "conditions": "_profile_written"},
    {"trigger": "_advance", "source": "writing_profile", "dest": "awaiting_profile"},
    {"trigger": "reset", "source": "*", "dest": "start", "before": "_on_reset"},
]


def _write_atomic(path: Path, text: str) -> None:
    """Write ``text`` to ``path`` whole or not at all."""
    tmp = path.with_name(path.name + ".tmp")
    try:
        tmp.write_text(text, encoding="utf-8")
        os.replace(tmp, path)
    finally:
        if tmp.exists():
            tmp.unlink()


def _mm(value: Any, name: str) -> float:
    mm = 1000.0 * checked_scalar(value, LENGTH, name=name)
    if not mm > 0.0:
        raise ValueError(f"{name} must be positive, got {value!r}")
    return mm


class RayfileSlicingFlow(ObservableFlow):
    """Asks for a rayfile and its package's footprint, slices it at a series of limits on h, and tabulates.

    Construct it (``begin()`` is called), then answer each question in turn,
    following ``explain_current_state()``: ``provide_rayfile(path)``,
    ``provide_package_width("7 mm")``, ``provide_package_length("7 mm")``,
    ``provide_n_slices()``, ``provide_kept_range()``, ``provide_choice(0.6)``,
    ``provide_profile()``; or, for any of them,
    ``answer(value)`` and ``answer_default()``, with ``pending_field()`` the
    question (``RAYFILE_SLICING_FIELDS``). After ``reset()``, call ``begin()``
    again. A file that does not
    parse, or a footprint the rays do not fit in, sends the flow back to the
    question, with ``self.problem`` saying why. Once sliced, ``self.result``
    holds the table and ``table_markdown()`` prints it; at ``done`` it also
    holds the choice and the profile written, if any.

    Args:
        base_dir: Where the run's directory (events, state diagram, result) is written.
        run_id: An explicit run id, or None for a generated one.
        render_svg: Re-render ``state.svg`` on every move (needs Graphviz's ``dot``).
    """

    FIELDS = RAYFILE_SLICING_FIELDS
    PURPOSE = ("Choose how far from the axis a rayfile slice keeps rays: given a rayfile and its "
               "package's footprint, tabulates the flux kept at a series of limits on the skew offset h.")

    def __init__(self, base_dir: Path, run_id: Optional[str] = None, render_svg: bool = True) -> None:
        self._clear()
        super().__init__(name="rayfile_slicing", states=RAYFILE_SLICING_STATES,
                         transitions_list=RAYFILE_SLICING_TRANSITIONS, initial="start",
                         base_dir=base_dir, run_id=run_id, render_svg=render_svg)
        self.begin()

    def _clear(self) -> None:
        self._path: Optional[Path] = None
        self.rayfile: Optional[Rayfile] = None
        self.width_mm: Optional[float] = None
        self.length_mm: Optional[float] = None
        self.n_slices = 10
        self.kept_range: Tuple[float, float] = (0.5, 0.75)
        self.warnings: List[str] = []
        self.problem: Optional[str] = None
        self.choice: Optional[Dict[str, Any]] = None
        self._profile: Optional[Dict[str, Any]] = None
        self.profile_written: Optional[Dict[str, Any]] = None
        self.result: Optional[Dict[str, Any]] = None

    def _on_reset(self, *args: Any, **kwargs: Any) -> None:
        super()._on_reset(*args, **kwargs)
        self._clear()

    def send_back_reason(self) -> Optional[str]:
        return self.problem

    def flow_field(self, state: str) -> Optional[FlowField]:
        """The choice's example names this table's limits."""
        field = self.FIELDS.get(state)
        if state != "awaiting_choice" or self.result is None:
            return field
        lo, hi = self.result["kept_range"]
        limits = self.result["limit_for_kept_share_mm"]
        example = (f'e.g. {lo:g} (keep {lo:.0%} of the flux: h <= {limits[f"{lo:.0%}"]:.3g} mm), or '
                   f'"{limits[f"{hi:.0%}"]:.3g} mm" (keeps {hi:.0%})')
        return FlowField(field.name, field.kind, field.question, field.why, example)

    def question_context(self) -> Optional[Dict[str, Any]]:
        """At the choice and the profile, the table the choice is made from."""
        if self.state not in ("awaiting_choice", "awaiting_profile") or self.result is None:
            return None
        r = self.result
        return {"table": self.table_markdown(), "half_diagonal_mm": r["half_diagonal_mm"],
                "limit_for_kept_share_mm": r["limit_for_kept_share_mm"], "choice": self.choice}

    def _ask(self) -> None:
        field = self.flow_field(self.state)
        explanation = field.explanation()
        if self.problem:
            explanation.message = f"{self.problem} -- {explanation.message}"
        self.set_explanation(explanation)
        self.emit_event(field=field.name, message=explanation.message)
        self.update_detail(waiting_on=field.name)

    # -- the rayfile -------------------------------------------------------

    def on_enter_awaiting_rayfile(self, *_args, **_kwargs) -> None:
        self._ask()

    def _provide_rayfile(self, path: Any) -> None:
        if not isinstance(path, (str, Path)):
            raise ValueError(f"rayfile must be a path, got {type(path).__name__}: {path!r}")
        self._path = Path(path)

    def on_enter_reading_rayfile(self, *_args, **_kwargs) -> None:
        try:
            self.rayfile = read_rayfile(self._path)
            self.problem = None
        except (OSError, ValueError) as e:
            self.rayfile = None
            self.problem = f"{self._path} could not be read: {e}"
            self.emit_event(message=self.problem)
            self._advance()
            return
        rf = self.rayfile
        lo, hi = rf.positions.min(axis=0), rf.positions.max(axis=0)
        self.emit_event(message=f"read {rf.n_rays} rays, {rf.total_flux:.4g} {rf.flux_unit}; start points "
                                f"x {lo[0]:.3g}..{hi[0]:.3g}, y {lo[1]:.3g}..{hi[1]:.3g}, "
                                f"z {lo[2]:.3g}..{hi[2]:.3g} mm",
                        n_rays=rf.n_rays, total_flux=rf.total_flux, flux_unit=rf.flux_unit, name=rf.name)
        self._advance()

    def _rayfile_read(self, *_args, **_kwargs) -> bool:
        return self.rayfile is not None

    # -- the footprint -----------------------------------------------------

    def on_enter_awaiting_package_width(self, *_args, **_kwargs) -> None:
        self._ask()

    def _provide_package_width(self, value: Any) -> None:
        self.width_mm = _mm(value, "package_width")

    def on_enter_awaiting_package_length(self, *_args, **_kwargs) -> None:
        self._ask()

    def _provide_package_length(self, value: Any) -> None:
        self.length_mm = _mm(value, "package_length")

    @property
    def half_diagonal_mm(self) -> float:
        return 0.5 * math.hypot(self.width_mm, self.length_mm)

    def on_enter_checking_dimensions(self, *_args, **_kwargs) -> None:
        rf, half = self.rayfile, np.array([0.5 * self.width_mm, 0.5 * self.length_mm])
        reach = np.abs(rf.positions[:, :2]).max(axis=0)
        allowed = half * (1.0 + FOOTPRINT_TOLERANCE_SHARE) + FOOTPRINT_TOLERANCE_MM
        self.warnings = []
        if np.any(reach > allowed):
            self.problem = (f"the rays start up to {reach[0]:.3g} mm from the axis in x and {reach[1]:.3g} mm in y, "
                            f"outside a {self.width_mm:g} x {self.length_mm:g} mm package: a wrong size, "
                            f"or a file not in mm")
            self.emit_event(message=self.problem)
            self._advance()
            return
        self.problem = None
        if np.any(reach < SMALL_SPAN_SHARE * half):
            self.warnings.append(f"the rays start within {reach[0]:.3g} x {reach[1]:.3g} mm of the axis, a small "
                                 f"part of a {self.width_mm:g} x {self.length_mm:g} mm package: the upper limits "
                                 f"will keep everything")
        centroid = (rf.positions[:, :2] * rf.flux[:, None]).sum(axis=0) / rf.total_flux
        if math.hypot(*centroid) > OFF_AXIS_SHARE * self.half_diagonal_mm:
            self.warnings.append(f"the flux centroid of the start points is at ({centroid[0]:.3g}, "
                                 f"{centroid[1]:.3g}) mm, off the axis the slice turns about")
        self.emit_event(message=f"the rays fit the package; limits up to its half diagonal, "
                                f"{self.half_diagonal_mm:.3g} mm", warnings=list(self.warnings))
        self._advance()

    def _dimensions_fit(self, *_args, **_kwargs) -> bool:
        return self.problem is None

    # -- the table's shape ---------------------------------------------------

    def on_enter_awaiting_n_slices(self, *_args, **_kwargs) -> None:
        self._ask()

    def _provide_n_slices(self, n: Any = 10) -> None:
        if isinstance(n, bool) or not isinstance(n, int) or n < 1:
            raise ValueError(f"n_slices must be a positive integer, got {n!r}")
        self.n_slices = n

    def on_enter_awaiting_kept_range(self, *_args, **_kwargs) -> None:
        self._ask()

    def _provide_kept_range(self, kept_range: Sequence[float] = (0.5, 0.75)) -> None:
        lo, hi = (float(v) for v in kept_range)
        if not 0.0 < lo < hi <= 1.0:
            raise ValueError(f"kept_range must be two shares 0 < low < high <= 1, got {kept_range!r}")
        self.kept_range = (lo, hi)

    # -- slicing ---------------------------------------------------------------

    def on_enter_slicing(self, *_args, **_kwargs) -> None:
        rf, lo, hi = self.rayfile, *self.kept_range
        theta = np.degrees(np.arccos(np.clip(rf.directions[:, 2], -1.0, 1.0)))
        led_within = float(rf.flux[theta <= WITHIN_DEG].sum() / rf.total_flux)
        rows = []
        for k in range(1, self.n_slices + 1):
            limit = self.half_diagonal_mm * k / self.n_slices
            slc = slice_rayfile(rf, (0.0, 0.0), 0.0, max_offset_mm=limit)
            kept = 1.0 - slc.skew_share
            within = (float(slc.flux[np.abs(slc.angles_deg()) <= WITHIN_DEG].sum() / slc.kept_flux)
                      if slc.kept_flux > 0 else None)
            rows.append({"max_offset_mm": limit, "rays_kept": int(len(slc.flux)), "kept_flux": slc.kept_flux,
                         "kept_share": kept, "skew_share": slc.skew_share, "within_30deg": within,
                         "in_kept_range": lo <= kept <= hi})
        quantiles = slc.offset_quantiles(rf.flux, (lo, hi))
        self.result = {
            "rayfile": str(self._path), "name": rf.name, "n_rays": rf.n_rays, "total_flux": rf.total_flux,
            "flux_unit": rf.flux_unit, "package_mm": [self.width_mm, self.length_mm],
            "half_diagonal_mm": self.half_diagonal_mm, "kept_range": [lo, hi],
            "limit_for_kept_share_mm": {f"{lo:.0%}": quantiles[lo], f"{hi:.0%}": quantiles[hi]},
            "led_within_30deg": led_within, "median_offset_mm": slc.offset_quantiles(rf.flux, (0.5,))[0.5],
            "rows": rows, "warnings": list(self.warnings),
        }
        self.emit_event(message=f"{len(rows)} slices; {lo:.0%} of the flux kept at h <= {quantiles[lo]:.3g} mm, "
                                f"{hi:.0%} at h <= {quantiles[hi]:.3g} mm")
        self._advance()

    # -- the choice and the profile -------------------------------------------

    def on_enter_awaiting_choice(self, *_args, **_kwargs) -> None:
        self._ask()

    def _provide_choice(self, value: Any) -> None:
        rf = self.rayfile
        if isinstance(value, bool) or value is None:
            raise ValueError(f"choice takes a kept share or a limit on h, got {value!r}")
        if isinstance(value, (int, float)):
            share = float(value)
            if not 0.0 < share <= 1.0:
                raise ValueError(f"a kept share must be in (0, 1], got {value!r}")
            limit = slice_rayfile(rf, (0.0, 0.0), 0.0, max_offset_mm=0.0).offset_quantiles(rf.flux, (share,))[share]
            by = {"kept_share_asked": share}
        elif isinstance(value, str):
            try:
                limit = _mm(value, "choice")
            except ValueError as e:
                raise ValueError(f"choice: a limit is a length with its unit (a share is a number, not a "
                                 f"string): {e}") from None
            by = {"max_offset_mm_asked": value}
        else:
            raise ValueError(f"choice takes a kept share (a number) or a limit (a string with its unit), "
                             f"got {type(value).__name__}: {value!r}")
        slc = slice_rayfile(rf, (0.0, 0.0), 0.0, max_offset_mm=limit)
        self.choice = {**by, "max_offset_mm": float(limit), "kept_share": 1.0 - slc.skew_share,
                       "rays_kept": int(len(slc.flux))}
        self.emit_event(message=f"chosen: h <= {limit:.4g} mm, keeping {self.choice['kept_share']:.1%} of the "
                                f"flux in {self.choice['rays_kept']} rays", choice=self.choice)

    def on_enter_awaiting_profile(self, *_args, **_kwargs) -> None:
        self._ask()

    def _provide_profile(self, value: Any = False) -> None:
        if value is False:
            self._profile = None
            return
        if not isinstance(value, dict):
            raise ValueError(f"profile takes false or an object with {list(_PROFILE_KEYS)}, "
                             f"got {type(value).__name__}: {value!r}")
        missing = [k for k in _PROFILE_KEYS if k not in value]
        unknown = sorted(set(value) - set(_PROFILE_KEYS) - set(_PROFILE_OPTIONAL))
        if missing or unknown:
            raise ValueError(f"profile: missing {missing}, unknown {unknown}; it takes {list(_PROFILE_KEYS)} "
                             f"and optionally {list(_PROFILE_OPTIONAL)}")
        path = Path(value["path"])
        if not path.is_file():
            raise ValueError(f"profile: no file {path}; export the optic's profile.json first")
        try:
            profile = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as e:
            raise ValueError(f"profile: {path} is not readable JSON: {e}") from None
        version = str(profile.get("schema_version", "0"))
        try:
            known = tuple(int(v) for v in version.split(".")[:2]) >= _RAYFILE_SCHEMA
        except ValueError:
            known = False
        if not known:
            raise ValueError(f"profile: {path} is schema {version}; a rayfile source needs 1.4 or later: "
                             f"export the profile again")
        name = value["name"]
        if not isinstance(name, str) or not name:
            raise ValueError(f"profile: name must be a non-empty string, got {name!r}")
        position = value["position"]
        if (not isinstance(position, (list, tuple)) or len(position) not in (2, 3)
                or not all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in position)):
            raise ValueError(f"profile: position must be [a, b] or [a, b, c] in mm, got {position!r}")
        angles = {}
        for key in ("direction_deg", "roll_deg"):
            angle = value.get(key, _PROFILE_OPTIONAL.get(key))
            if isinstance(angle, bool) or not isinstance(angle, (int, float)):
                raise ValueError(f"profile: {key} must be a number of degrees, got {angle!r}")
            angles[key] = float(angle)
        self._profile = {"path": path, "name": name, "position": [float(v) for v in position], **angles}

    def on_enter_writing_profile(self, *_args, **_kwargs) -> None:
        self.problem = None
        if self._profile is None:
            self.profile_written = None
            self.emit_event(message="no profile asked for: nothing to write")
            self._advance()
            return
        p = self._profile
        folder = p["path"].resolve().parent
        try:
            rel = os.path.relpath(self._path.resolve(), folder)
        except ValueError:                                   # another drive: the path stays absolute
            rel = str(self._path.resolve())
        try:
            spec = self.source_spec(p["name"], p["position"], p["direction_deg"], roll_deg=p["roll_deg"],
                                    max_offset_mm=self.choice["max_offset_mm"], path=rel, base_dir=folder)
            profile = json.loads(p["path"].read_text(encoding="utf-8"))
            sources = [s for s in (profile.get("sources") or []) if s.get("name") != p["name"]]
            replaced = len(sources) != len(profile.get("sources") or [])
            profile["sources"] = profile_sources({"sources": [*sources, spec]})
            _write_atomic(p["path"], json.dumps(profile, indent=2))
        except (OSError, ValueError) as e:
            self.problem = f"{p['path']} could not be written: {e}"
            self.emit_event(message=self.problem)
            self._advance()
            return
        self.profile_written = {"path": str(p["path"]), "source": spec, "replaced": replaced}
        self.emit_event(message=f"source {p['name']!r} {'replaced in' if replaced else 'written to'} {p['path']}",
                        profile=str(p["path"]), source=p["name"], replaced=replaced)
        self._advance()

    def _profile_written(self, *_args, **_kwargs) -> bool:
        return self.problem is None

    def on_enter_done(self, *_args, **_kwargs) -> None:
        self.result = {**self.result, "choice": self.choice, "profile": self.profile_written}
        self.finish(self.result)
        self.set_explanation(explain_field("done", "The table is ready.", "result, table_markdown()", ""))
        self.emit_event(message="done")

    def source_spec(self, name: str, position: Sequence[float], direction_deg: float, *,
                    kept_share: Optional[float] = None, max_offset_mm: Optional[float] = None,
                    roll_deg: float = 0.0, path: Optional[str] = None, base_dir: Any = None) -> Dict[str, Any]:
        """The ``rayfile`` source spec for the limit chosen from the table, for a profile's ``sources``.

        Give the choice as ``kept_share`` (the limit is then the exact
        flux-weighted quantile of |h|) or as ``max_offset_mm``, not both.

        Args:
            name, position, direction_deg, roll_deg: The source's name and
                placement in the 2D scene (``rayfile_source_spec``).
            path: The file's path as it is to be written into the profile
                (relative to ``base_dir``, the profile's folder); the path
                given to the flow by default.

        Raises:
            RuntimeError: Before the table is made.
            ValueError: Unless exactly one of ``kept_share``, ``max_offset_mm`` is given.
        """
        from .source_spec import rayfile_source_spec  # noqa: PLC0415  (source_spec imports nothing of this)

        if self.result is None:
            raise RuntimeError(f"no table yet: the flow is at {self.state}")
        if (kept_share is None) == (max_offset_mm is None):
            raise ValueError("give exactly one of kept_share, max_offset_mm")
        if kept_share is not None:
            if not 0.0 < kept_share <= 1.0:
                raise ValueError(f"kept_share must be in (0, 1], got {kept_share}")
            slc = slice_rayfile(self.rayfile, (0.0, 0.0), 0.0, max_offset_mm=0.0)
            max_offset_mm = slc.offset_quantiles(self.rayfile.flux, (kept_share,))[kept_share]
        spec = rayfile_source_spec(name, path if path is not None else str(self._path), position, direction_deg,
                                   roll_deg=roll_deg, max_offset_mm=max_offset_mm, base_dir=base_dir)
        self.emit_event(message=f"source spec {name!r}: h <= {max_offset_mm:.4g} mm keeps "
                                f"{spec['slice']['kept_share']:.1%} of the flux", slice=spec["slice"])
        return spec

    def table_markdown(self) -> str:
        """The table, with the limits at the ends of the kept range and any warnings."""
        if self.result is None:
            raise RuntimeError(f"no table yet: the flow is at {self.state}")
        r = self.result
        unit = r["flux_unit"]
        lines = [f"{r['name'] or r['rayfile']}: {r['n_rays']} rays, {r['total_flux']:.4g} {unit}, package "
                 f"{r['package_mm'][0]:g} x {r['package_mm'][1]:g} mm (half diagonal {r['half_diagonal_mm']:.3g} mm)",
                 "",
                 f"| Limit on h (mm) | Rays kept | Flux kept ({unit}) | Kept | Skew share | Within 30 deg |",
                 "|---|---|---|---|---|---|"]
        for row in r["rows"]:
            mark = " *" if row["in_kept_range"] else ""
            within = "-" if row["within_30deg"] is None else f"{row['within_30deg']:.1%}"
            lines.append(f"| {row['max_offset_mm']:.3g}{mark} | {row['rays_kept']} | {row['kept_flux']:.4g} | "
                         f"{row['kept_share']:.1%} | {row['skew_share']:.1%} | {within} |")
        lo, hi = r["kept_range"]
        limits = r["limit_for_kept_share_mm"]
        lines += ["",
                  f"* inside the kept range, {lo:.0%} to {hi:.0%}. The LED: {r['led_within_30deg']:.1%} within 30 deg.",
                  f"{lo:.0%} of the flux is kept at h <= {limits[f'{lo:.0%}']:.3g} mm; "
                  f"{hi:.0%} at h <= {limits[f'{hi:.0%}']:.3g} mm."]
        lines += [f"Warning: {w}" for w in r["warnings"]]
        return "\n".join(lines)


__all__ = ["RAYFILE_SLICING_FIELDS", "RAYFILE_SLICING_STATES", "RAYFILE_SLICING_TRANSITIONS",
           "RayfileSlicingFlow"]
