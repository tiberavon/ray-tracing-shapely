"""
Python-specific module: block chain
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
The chain's blocks: a rayfile to a risk group
===============================================================================
    slice_rayfile -> source_from_slice --+
    (a constructor block) ---------------+-> assemble -> trace -> detector_reading
                                                                     |
              classify_iec62471 <- hazard_weighted <- physical_reading

Each block is a function of this module, callable from a notebook with the
same arguments; the block surface adds the types (`blocks.types`). The
library functions underneath keep their floats; a quantity's live form here
is a float in its port's unit, the unit named in the port.

**Where the chain is physical and where it is not.**
- **`physical_reading`** makes a 2D reading an irradiance for an **extruded**
  scene: brightness times the calibration is power per metre of extrusion,
  and over the detector's length that is W/m², the height cancelling. A
  **revolved** reading (a TIR collimator spun about its axis) needs
  `RevolvedProjection`, which is a stub (`C-EYE-03`): the block refuses it.
- **`hazard_weighted`** weighs an irradiance by a hazard's function over the
  rayfile's spectrum (`weighted_fraction`).
- **`classify_iec62471`** checks each value's kind as the intake flow does
  (`checked_hazard_value`), so a radiance cannot pass for an irradiance.
===============================================================================
"""

from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

from .registry import Port, block
from .types import (
    BOOL, CLASSIFICATION, DETECTOR_READING, INTEGER, IRRADIANCE, POSITION, RADIANCE, RAYFILE,
    RAYFILE_SLICE, SCENE, SCENE_ENTRY, TEXT, TRACE, BlockTypeError, Choice, JSON, ListOf, Optional_, Quantity,
    Trace,
)

LENGTH = Quantity("mm")
DEGREES = Quantity("deg")
POWER_PER_LENGTH = Quantity("W/m")

#: The IEC 62471 hazards a block classifies, as `iec62471_flow`'s keys.
HAZARDS = ("actinic_uv", "near_uv", "blue_light", "retinal_thermal", "ir")


@block("slice_rayfile",
       inputs={"rayfile": (RAYFILE, "the path of an IES TM-25 rayfile (positions in mm, the LED's axis z)"),
               "position": (POSITION, "where the LED's origin goes in the scene: [x, y] in mm"),
               "direction_deg": (DEGREES, "the LED's axis in the scene, from +x, counter-clockwise"),
               "max_offset_mm": (LENGTH, "keep the rays whose line passes within this distance of the axis; "
                                         "the summary says the share of the flux kept"),
               "roll_deg": (DEGREES, "the LED's roll about its axis")},
       outputs={"slice": RAYFILE_SLICE})
def slice_rayfile_block(rayfile: Any, position: Any, direction_deg: float, max_offset_mm: float,
                        roll_deg: float = 0.0) -> Any:
    """A rayfile's near-meridional rays, turned into the 2D plane at a position and an axis."""
    from ..optical_elements.sources import slice_rayfile  # noqa: PLC0415
    try:
        return slice_rayfile(rayfile, position, direction_deg, max_offset_mm=max_offset_mm, roll_deg=roll_deg)
    except ValueError as exc:
        raise BlockTypeError(f"slice_rayfile: {exc}") from None


@block(inputs={"slice": RAYFILE_SLICE, "name": (TEXT, "the source's name in the scene"),
               "wavelength_nm": (Optional_(Quantity("nm")), "the rays' wavelength; default 532 nm")},
       outputs={"entry": SCENE_ENTRY})
def source_from_slice(slice: Any, name: str = "rayfile slice", wavelength_nm: Optional[float] = None) -> Dict[str, Any]:
    """A rayfile's slice as a RaySetSource's scene entry; brightness 1 carries the brightest ray's flux."""
    try:
        return slice.scene_entry(name, wavelength_nm)
    except ValueError as exc:
        raise BlockTypeError(f"source_from_slice: {exc}") from None


@block(inputs={"entries": ListOf(SCENE_ENTRY), "settings": Optional_(JSON)}, outputs={"scene": SCENE})
def assemble(entries: List[Dict[str, Any]], settings: Optional[Dict[str, Any]] = None) -> Any:
    """A scene from its entries, in order; names must be unique (C-LABEL-01)."""
    from ..analysis import scene_file as sf  # noqa: PLC0415
    try:
        return sf.assemble(entries, settings)
    except sf.SceneFileError as exc:
        raise BlockTypeError(f"assemble: {exc}") from None


def _detectors(scene: Any) -> List[Any]:
    return [o for o in scene.objs if getattr(o, "name", None) and hasattr(o, "get_hit_records")]


@block(inputs={"scene": SCENE,
               "max_rays": (INTEGER, "the most ray segments traced (each reflection or refraction makes more)"),
               "runs_dir": (Optional_(TEXT), "a folder to save the run to: only needed for a trace's JSON form "
                                             "(and to load it with load_run_context); a handle feeds the next "
                                             "block without it"),
               "run_id": (Optional_(TEXT), "the run's folder name under runs_dir/blocks")},
       outputs={"trace": TRACE})
def trace(scene: Any, max_rays: int = 100000, runs_dir: Optional[str] = None,
          run_id: Optional[str] = None) -> Trace:
    """Trace a scene and read every named detector; with runs_dir, save the run (its JSON form).

    Each reading is `read_detector`'s, with the profile where the detector
    keeps an irradiance map. Saved, the run is a run bundle
    (``<runs_dir>/blocks/<run_id>``) with ``scene.json`` and
    ``readings.json`` beside it.
    """
    from ..analysis import scene_file as sf  # noqa: PLC0415
    from ..analysis.parameter_study import read_detector  # noqa: PLC0415
    from ..analysis.run_registry import persist_run_artifacts  # noqa: PLC0415
    from ..core.simulator import Simulator  # noqa: PLC0415

    result = Simulator(scene, max_rays=max_rays).run_with_result()
    readings = {d.name: read_detector(scene, result, d.name, profile=bool(getattr(d, "irradMap", False)))
                for d in _detectors(scene)}
    folder = None
    if runs_dir is not None:
        folder = persist_run_artifacts(scene, result, out_dir=Path(runs_dir).expanduser(), design_id="blocks",
                                       run_id=run_id or uuid.uuid4().hex[:12], physical_params={},
                                       numerical_params={"max_rays": max_rays})
        sf.save_scene(scene, folder / "scene.json")
        (folder / "readings.json").write_text(json.dumps(readings, indent=2), encoding="utf-8")
    return Trace(scene, readings, result, folder)


@block(inputs={"trace": TRACE, "detector": (TEXT, "the detector's name"),
               "profile": (BOOL, "add the power in each bin (the detector needs irradMap on)")},
       outputs={"reading": DETECTOR_READING})
def detector_reading(trace: Trace, detector: str, profile: bool = False) -> Dict[str, Any]:
    """What one detector of a trace measured (`read_detector`)."""
    if detector not in trace.readings:
        raise BlockTypeError(f"detector_reading: no detector named {detector!r}; "
                             f"detectors: {', '.join(sorted(trace.readings)) or 'none'}")
    reading = dict(trace.readings[detector])
    if not profile:
        reading.pop("profile", None)
    elif "profile" not in reading:
        raise BlockTypeError(f"detector_reading: {detector!r} keeps no profile; turn on its irradMap")
    return reading


@block(inputs={"reading": (DETECTOR_READING, "power is in brightness, the 2D scene's unit"),
               "calibration": (POWER_PER_LENGTH, "the power per metre of extrusion that brightness 1 carries"),
               "detector_length": (LENGTH, "the detector's length in the scene (from p1 to p2)"),
               "symmetry": (Choice(["extrude", "revolve"]),
                            "how the 2D section becomes solid: extrude (swept along z, a trough) or revolve "
                            "(spun about the axis, refused until RevolvedProjection exists)")},
       outputs={"irradiance": IRRADIANCE, "profile": Optional_(ListOf(IRRADIANCE))})
def physical_reading(reading: Dict[str, Any], calibration: float, detector_length: float,
                     symmetry: str = "extrude") -> Dict[str, Any]:
    """A 2D reading as irradiance: power x calibration / detector_length (each bin's over its width).

    Args:
        reading: A detector's reading (its ``power`` and ``profile`` are in
            brightness, the 2D unit).
        calibration: W/m: the power per metre of extrusion that brightness 1
            carries (`PhysicalScene.set_calibration`).
        detector_length: The detector's length in the scene, mm.
        symmetry: How the 2D scene becomes solid (`C-UNITS-01`); only
            ``extrude`` is made physical yet.

    Raises:
        BlockTypeError: ``revolve`` (`RevolvedProjection` is a stub,
            `C-EYE-03`), or a length that is not positive.
    """
    from ..optical_elements.physical_scene import PhysicalScene  # noqa: PLC0415
    from ..optical_elements.units import ureg  # noqa: PLC0415
    if symmetry != "extrude":
        raise BlockTypeError("physical_reading: a revolved reading needs RevolvedProjection, which is a stub "
                             "(C-EYE-03); only an extruded scene is made physical yet")
    if detector_length <= 0.0:
        raise BlockTypeError(f"physical_reading: detector_length must be positive, got {detector_length} mm")
    phys = PhysicalScene(scene_unit="mm")
    phys.set_calibration(1.0, ureg.Quantity(calibration, "W/m"))

    def over(power: float, length_mm: float) -> float:
        return (power * phys.calibration_factor / ureg.Quantity(phys.to_m(length_mm), "m")).to("W/m^2").magnitude

    out: Dict[str, Any] = {"irradiance": over(reading["power"], detector_length), "profile": None}
    prof = reading.get("profile")
    if prof and prof.get("bin_size", 0) > 0:
        out["profile"] = [over(p, prof["bin_size"]) for p in prof["power"]]
    return out


@block(inputs={"irradiance": (IRRADIANCE, "an unweighted irradiance, over the whole spectrum"),
               "rayfile": (RAYFILE, "the path of the rayfile whose spectrum weighs it (read from the file)"),
               "hazard": (Choice(list(HAZARDS)), "the IEC 62471 weighting: actinic_uv S(λ), blue_light B(λ), "
                                                 "retinal_thermal R(λ); near_uv 315-400 nm, ir 780-3000 nm")},
       outputs={"weighted": IRRADIANCE})
def hazard_weighted(irradiance: float, rayfile: Any, hazard: str) -> float:
    """A hazard-weighted irradiance (E_B for blue_light): irradiance x ∫S(λ)W(λ)dλ / ∫S(λ)dλ, S the rayfile's spectrum."""
    from ..optical_elements.eye_safety import weighted_fraction  # noqa: PLC0415
    if rayfile.spectrum_nm is None:
        raise BlockTypeError("hazard_weighted: the rayfile has no spectrum to weigh by")
    try:
        return irradiance * weighted_fraction(rayfile.spectrum_nm, hazard)
    except ValueError as exc:
        raise BlockTypeError(f"hazard_weighted: {exc}") from None


_CLASSIFY_INPUTS = {
    "alpha": Port("alpha", Quantity("rad"), doc="the apparent source's angular subtense; it decides whether "
                                                 "blue light is given as a radiance (>= 0.011 rad) or an irradiance"),
    "actinic_uv": Port("actinic_uv", Optional_(IRRADIANCE), required=False, doc="E_eff, S(λ)-weighted"),
    "near_uv": Port("near_uv", Optional_(IRRADIANCE), required=False, doc="E_UVA"),
    "blue_light_radiance": Port("blue_light_radiance", Optional_(RADIANCE), required=False,
                                doc="L_B, B(λ)-weighted: for alpha >= 0.011 rad"),
    "blue_light_irradiance": Port("blue_light_irradiance", Optional_(IRRADIANCE), required=False,
                                  doc="E_B, B(λ)-weighted: for alpha < 0.011 rad"),
    "retinal_thermal": Port("retinal_thermal", Optional_(RADIANCE), required=False, doc="L_R, R(λ)-weighted"),
    "ir": Port("ir", Optional_(IRRADIANCE), required=False, doc="E_IR, 780-3000 nm"),
}


@block(inputs=_CLASSIFY_INPUTS, outputs={"classification": CLASSIFICATION})
def classify_iec62471(alpha: float, actinic_uv: Optional[float] = None, near_uv: Optional[float] = None,
                      blue_light_radiance: Optional[float] = None, blue_light_irradiance: Optional[float] = None,
                      retinal_thermal: Optional[float] = None, ir: Optional[float] = None) -> Dict[str, Any]:
    """The IEC 62471 risk group of the hazards given (only those), and each limit it was checked against.

    A hazard left out is one the source does not emit in
    (`classify_measurement`'s contract). Blue light is a radiance or an
    irradiance by ``alpha``, as `mpe_blue_light` dispatches: the other is
    refused. Each value is checked by `checked_hazard_value`, the intake
    flow's own check.
    """
    from ..optical_elements.eye_safety import iec62471  # noqa: PLC0415
    from ..optical_elements.eye_safety_classification_flow.dimensional_checks import (  # noqa: PLC0415
        checked_hazard_value, expected_dimensionality_for_hazard,
    )
    from ..optical_elements.eye_safety_classification_flow.iec62471_flow import (  # noqa: PLC0415
        _HAZARD_TO_KWARG, _compute_limit,
    )
    if blue_light_radiance is not None and blue_light_irradiance is not None:
        raise BlockTypeError("classify_iec62471: give blue light as a radiance or an irradiance, not both")
    given = {"actinic_uv": (actinic_uv, IRRADIANCE), "near_uv": (near_uv, IRRADIANCE),
             "blue_light": ((blue_light_radiance, RADIANCE) if blue_light_radiance is not None
                            else (blue_light_irradiance, IRRADIANCE)),
             "retinal_thermal": (retinal_thermal, RADIANCE), "ir": (ir, IRRADIANCE)}
    values: Dict[str, float] = {}
    for hazard, (value, t) in given.items():
        if value is None:
            continue
        try:
            values[hazard] = checked_hazard_value(hazard, f"{value!r} {t.unit}", alpha, name=hazard)
        except ValueError as exc:
            expected = expected_dimensionality_for_hazard(hazard, alpha)
            raise BlockTypeError(f"classify_iec62471: {hazard} at alpha {alpha} rad is a quantity in {expected}: "
                                 f"{exc}") from None
    group = iec62471.classify_measurement(alpha, **{_HAZARD_TO_KWARG[h]: v for h, v in values.items()})
    limits = []
    for hazard, value in values.items():
        for g in ("exempt", "rg1", "rg2"):
            lim = _compute_limit(hazard, g, alpha)
            limits.append({"hazard": hazard, "group": g, "value": value, "limit": lim.value, "unit": lim.unit,
                           "within": value <= lim.value})
    return {"group": group, "assessed": sorted(values), "not_assessed": [h for h in HAZARDS if h not in values],
            "limits": limits,
            "note": "RG3: above RG2's limit" if group == "RG3" else f"{group}: the first group whose limits all hold"}


__all__ = ["HAZARDS", "assemble", "classify_iec62471", "detector_reading", "hazard_weighted", "physical_reading",
           "slice_rayfile_block", "source_from_slice", "trace"]
