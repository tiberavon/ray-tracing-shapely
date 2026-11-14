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
          -> slicing -> done

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

The machine is the eye-safety flows' ``ObservableFlow``: every move is an
event in ``events.jsonl``, ``state.svg`` shows the current box, ``reset``
restarts from ``start``, and ``explain_current_state()`` says what each
box is asking. It needs the ``eye-safety`` extra (``transitions``, pint),
which is why ``sources`` does not import it.

The axis is the rayfile's z axis through its origin, as for
``slice_rayfile``; the table does not depend on where the slice is placed
in the 2D scene.
===============================================================================
"""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np

from ..eye_safety_classification_flow.dimensional_checks import checked_scalar
from ..eye_safety_classification_flow.explanations import explain_field
from ..eye_safety_classification_flow.flow_base import ObservableFlow
from ..units import LENGTH
from .rayfile import Rayfile, read_rayfile
from .rayfile_slice import slice_rayfile

#: Start points may lie this far outside the footprint (rounding, a rim): mm, and share of the half width.
FOOTPRINT_TOLERANCE_MM = 0.05
FOOTPRINT_TOLERANCE_SHARE = 0.02
#: Start points spanning less than this share of the footprint draw a warning.
SMALL_SPAN_SHARE = 0.25
#: A flux centroid further than this share of the half diagonal from the axis draws a warning.
OFF_AXIS_SHARE = 0.05
#: The angle the kept rays' spread is checked at.
WITHIN_DEG = 30.0

_INFO: Dict[str, Dict[str, str]] = {
    "rayfile": {
        "question": "Which rayfile? (IES TM-25, positions in mm, the LED's axis along z)",
        "citation": "parsed by read_rayfile; the axis is the file's z axis through its origin",
        "example": 'e.g. "rayfile_LED_100k.TM25RAY"',
    },
    "package_width": {
        "question": "What is the package's width, along the rayfile's x?",
        "citation": "with the length, the footprint: its half diagonal is the largest limit on h",
        "example": 'e.g. "7 mm"',
    },
    "package_length": {
        "question": "What is the package's length, along the rayfile's y?",
        "citation": "with the width, the footprint: its half diagonal is the largest limit on h",
        "example": 'e.g. "7 mm"',
    },
    "n_slices": {
        "question": "How many limits on h, in equal steps up to the half diagonal?",
        "citation": "one row of the table each",
        "example": "e.g. 10 (the default: call provide_n_slices())",
    },
    "kept_range": {
        "question": "Within what range of kept flux will the limit be chosen?",
        "citation": "the flow reports the limit at each end and marks the rows inside; it does not choose",
        "example": "e.g. (0.5, 0.75) (the default: call provide_kept_range())",
    },
}

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
    {"trigger": "_advance", "source": "slicing", "dest": "done"},
    {"trigger": "reset", "source": "*", "dest": "start", "before": "_on_reset"},
]


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
    ``provide_n_slices()``, ``provide_kept_range()``. After ``reset()``, call
    ``begin()`` again. A file that does not
    parse, or a footprint the rays do not fit in, sends the flow back to the
    question, with ``self.problem`` saying why. At ``done``, ``self.result``
    holds the table and ``table_markdown()`` prints it.

    Args:
        base_dir: Where the run's directory (events, state diagram, result) is written.
        run_id: An explicit run id, or None for a generated one.
        render_svg: Re-render ``state.svg`` on every move (needs Graphviz's ``dot``).
    """

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
        self.result: Optional[Dict[str, Any]] = None

    def _on_reset(self, *args: Any, **kwargs: Any) -> None:
        super()._on_reset(*args, **kwargs)
        self._clear()

    def _ask(self, field: str) -> None:
        info = _INFO[field]
        explanation = explain_field(field, info["question"], info["citation"], info["example"])
        if self.problem:
            explanation.message = f"{self.problem} -- {explanation.message}"
        self.set_explanation(explanation)
        self.emit_event(field=field, message=explanation.message)
        self.update_detail(waiting_on=field)

    # -- the rayfile -------------------------------------------------------

    def on_enter_awaiting_rayfile(self, *_args, **_kwargs) -> None:
        self._ask("rayfile")

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
        self._ask("package_width")

    def _provide_package_width(self, value: Any) -> None:
        self.width_mm = _mm(value, "package_width")

    def on_enter_awaiting_package_length(self, *_args, **_kwargs) -> None:
        self._ask("package_length")

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
        self._ask("n_slices")

    def _provide_n_slices(self, n: Any = 10) -> None:
        if isinstance(n, bool) or not isinstance(n, int) or n < 1:
            raise ValueError(f"n_slices must be a positive integer, got {n!r}")
        self.n_slices = n

    def on_enter_awaiting_kept_range(self, *_args, **_kwargs) -> None:
        self._ask("kept_range")

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

    def on_enter_done(self, *_args, **_kwargs) -> None:
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


__all__ = ["RAYFILE_SLICING_STATES", "RAYFILE_SLICING_TRANSITIONS", "RayfileSlicingFlow"]
