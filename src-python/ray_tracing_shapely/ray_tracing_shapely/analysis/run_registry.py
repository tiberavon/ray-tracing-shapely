"""
Python translation Copyright 2026 ray-tracing-shapely authors and contributors

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

    http://www.apache.org/licenses/LICENSE-2.0

===============================================================================
PYTHON-SPECIFIC MODULE: Run Persistence and Cross-Run Comparison (Layer 1/3)
===============================================================================
Persists a run's derived, already-serializable artifacts to disk under
<out_dir>/<design_id>/<run_id>/, and compares two persisted runs' summary.json
without needing a live kernel for either -- P-RUN-BUNDLE, see
dev_doc/architecture/components/analysis_run_registry.md, C-RUN-01, and
C-RUN-02. Design rationale:
dev_doc/architecture/components/analysis_run_registry.md.

graph.json/signature_spectrum.json are written only when a BidirectionalResult
is passed in (analysis.signature_analysis: path_signature/signature_spectrum,
dev_doc/architecture/components/nonimaging_design.md). Nothing here
reconstructs a live Scene: replay for a historical run goes through the
notebook/papermill_parameters that built it, not a serialized Scene dump (see
dev_doc/architecture/components/analysis_run_registry.md).

Layout:
    out_dir/
      manifest.jsonl                # one row per run, append-only
      <design_id>/
        <run_id>/
          params.json                # {"physical_params": {...}, "numerical_params": {...}}
          rays.sqlite                # file-backed create_database() output
          summary.json                # scalar rollup from SimulationResult's own statistics
          graph.json                  # nx.node_link_data(combined) -- only if bidirectional was run
          signature_spectrum.json     # signature_spectrum_to_records() -- only if bidirectional was run
===============================================================================
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Optional, TYPE_CHECKING

from .agentic_db import create_database
from .signature_analysis import (
    signature_spectrum,
    signature_spectrum_to_records,
    signature_spectrum_from_records,
    diff_signature_spectra,
)

if TYPE_CHECKING:
    from ..core.scene import Scene
    from .simulation_result import SimulationResult
    from .bidirectional import BidirectionalResult


def _summary_from_result(result: 'SimulationResult') -> Dict[str, Any]:
    """Scalar rollup from a SimulationResult's own statistics methods --
    no new statistics code needed, these are already plain, JSON-ready dicts."""
    return {
        'tir': result.get_tir_statistics(),
        'grazing': result.get_grazing_statistics(),
        'wavelength': result.get_wavelength_statistics(),
        'source': result.get_source_statistics(),
        'processed_ray_count': result.processed_ray_count,
        'segment_count': result.segment_count,
        'success': result.success,
    }


def _name_topology_fingerprint(scene: 'Scene') -> Dict[str, Any]:
    """C-LABEL-01's {name: topology} fingerprint -- the check that turns "names
    are stable across runs" from a remembered rule into an automatic one.

    Records, for every named object in `scene`, a stable-across-a-sweep
    summary of what it *is* (`type`, `role`), keyed by `name` -- the same
    join key every cross-run comparison in this codebase actually uses.
    Also records unnamed objects by type, since C-LABEL-01's second failure
    mode (several objects all defaulting to `name=None`) has no name to key
    on at all.

    Args:
        scene: The live Scene a run was built from.

    Returns:
        {"named": {name: {"type": str, "role": Optional[str]}, ...},
         "unnamed_by_type": {type: count, ...}}

    Raises:
        ValueError: If two objects in `scene` share the same non-None
            `name`. This is a defect within a single run, not just across
            runs -- caught here, at persist time, rather than surfacing
            later as a confusing cross-run diff or a silently-collapsed key.
    """
    named: Dict[str, Dict[str, Optional[str]]] = {}
    unnamed_by_type: Dict[str, int] = {}
    for obj in scene.objs:
        name = getattr(obj, 'name', None)
        obj_type = getattr(obj, 'type', None) or obj.__class__.__name__
        role = getattr(obj, 'role', None)
        role_value = role.value if role is not None else None
        if name is None:
            unnamed_by_type[obj_type] = unnamed_by_type.get(obj_type, 0) + 1
            continue
        if name in named:
            raise ValueError(
                f"Duplicate scene-object name {name!r}: at least two "
                f"objects share this name (types {named[name]['type']!r} "
                f"and {obj_type!r}). C-LABEL-01 requires name to be a "
                "unique join key within a scene, not just stable across "
                "runs -- give one of them a distinct literal name."
            )
        named[name] = {"type": obj_type, "role": role_value}
    return {"named": named, "unnamed_by_type": unnamed_by_type}


def persist_run_artifacts(
    scene: 'Scene',
    result: 'SimulationResult',
    *,
    out_dir: Path,
    design_id: str,
    run_id: str,
    physical_params: Dict[str, Any],
    numerical_params: Dict[str, Any],
    bidirectional_result: Optional['BidirectionalResult'] = None,
) -> Path:
    """
    Write one run's derived artifacts to out_dir/<design_id>/<run_id>/ and
    append a manifest row.

    Args:
        scene: The live Scene the run was built from (used only to populate
            rays.sqlite's glass/detector tables via create_database).
        result: The SimulationResult from Simulator.run_with_result().
        out_dir: Root directory for all persisted runs.
        design_id: Identifies the design/builder family this run belongs to
            (e.g. 'dtirc_n15') -- the two-level grouping this module exists
            for; many runs group into a design.
        run_id: Identifies this specific run within the design (e.g.
            'n_sample_1.34').
        physical_params: Parameters that describe a physical design/sweep
            choice (expect signatures to differ across values).
        numerical_params: Parameters that describe a numerical/resolution
            choice (expect signatures to converge as resolution increases).
        bidirectional_result: Optional BidirectionalResult (from
            Simulator.run_bidirectional()). When given and its .combined
            graph is populated, also writes graph.json and
            signature_spectrum.json.

    Returns:
        The run's artifact directory (out_dir/design_id/run_id).
    """
    run_dir = Path(out_dir) / design_id / run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    (run_dir / 'params.json').write_text(json.dumps({
        'physical_params': physical_params,
        'numerical_params': numerical_params,
        'name_topology': _name_topology_fingerprint(scene),
    }, indent=2))

    db_path = run_dir / 'rays.sqlite'
    if db_path.exists():
        db_path.unlink()
    create_database(scene, result.segments, db_path=db_path).close()

    (run_dir / 'summary.json').write_text(
        json.dumps(_summary_from_result(result), indent=2)
    )

    if bidirectional_result is not None and bidirectional_result.combined is not None:
        import networkx as nx

        (run_dir / 'graph.json').write_text(
            json.dumps(nx.node_link_data(bidirectional_result.combined))
        )
        spectrum = signature_spectrum(bidirectional_result)
        (run_dir / 'signature_spectrum.json').write_text(
            json.dumps(signature_spectrum_to_records(spectrum))
        )

    manifest_path = Path(out_dir) / 'manifest.jsonl'
    with open(manifest_path, 'a', encoding='utf-8') as f:
        f.write(json.dumps({
            'design_id': design_id,
            'run_id': run_id,
            'run_dir': str(run_dir),
        }) + '\n')

    return run_dir


def _check_name_topology(
    fp_a: Dict[str, Any], fp_b: Dict[str, Any], run_a: str, run_b: str,
) -> None:
    """C-LABEL-01's enforcement half: fail loudly, before any other
    comparison happens, on exactly the two ways this contract has actually
    broken -- a swept parameter absorbed into the name
    (different key sets) and objects left unnamed (a `None` key, silently
    collapsing several objects into one indistinguishable bucket).

    Raises:
        ValueError: If the two runs' named-object key sets differ, if a
            name shared by both runs maps to a different `type`/`role`, or
            if either run has any unnamed object at all.
    """
    named_a, named_b = fp_a['named'], fp_b['named']
    keys_a, keys_b = set(named_a), set(named_b)

    only_in_a = keys_a - keys_b
    only_in_b = keys_b - keys_a
    if only_in_a or only_in_b:
        raise ValueError(
            f"compare_runs: {run_a} and {run_b} name different scene "
            f"objects -- C-LABEL-01 requires identical names for the "
            f"comparison to mean anything. Only in {run_a}: "
            f"{sorted(only_in_a)}. Only in {run_b}: {sorted(only_in_b)}. "
            "A common cause: a swept parameter absorbed into the name "
            "itself (e.g. f'source_{angle}') instead of kept as a literal."
        )

    mismatched = {
        name: (named_a[name], named_b[name])
        for name in keys_a
        if named_a[name] != named_b[name]
    }
    if mismatched:
        raise ValueError(
            f"compare_runs: {run_a} and {run_b} use the same names for "
            f"structurally different objects -- {mismatched}. The same "
            "name must refer to the same kind of object in both runs "
            "(C-LABEL-01)."
        )

    unnamed_a, unnamed_b = fp_a['unnamed_by_type'], fp_b['unnamed_by_type']
    if unnamed_a or unnamed_b:
        raise ValueError(
            f"compare_runs: at least one run has unnamed scene objects -- "
            f"{run_a}: {unnamed_a or 'none'}, {run_b}: {unnamed_b or 'none'}. "
            "An unnamed object's name defaults to None, so several unnamed "
            "objects collapse into one indistinguishable bucket and any "
            "comparison keyed on name silently stops meaning anything for "
            "them (C-LABEL-01). Give every object being compared a stable, "
            "literal name."
        )


def compare_runs(
    design_id_a: str,
    run_id_a: str,
    design_id_b: str,
    run_id_b: str,
    *,
    out_dir: Path,
    check_name_topology: bool = True,
) -> Dict[str, Any]:
    """
    Compare two persisted runs -- no live kernel, no SQLite connection, no
    _CONTEXT/_CONTEXTS entry required for either run.

    Checks the two runs' {name: topology} fingerprints first (C-LABEL-01,
    `check_name_topology=True` by default) and raises immediately on a
    mismatch, before comparing anything else -- a diff computed on
    mismatched names is not wrong, it is meaningless, and this project has
    two real cases of exactly that going unnoticed [KD3: a meaningless diff
    that looks like a result is the failure worth a check]. Then always diffs summary.json (scalar statistics), and adds
    a signature_diff (dev_doc/architecture/components/analysis_bidirectional.md)
    when both runs have a signature_spectrum.json -- i.e. both were
    persisted with a bidirectional_result. Runs without one (plain
    forward-only sweeps) still compare fine on summary.json alone;
    signature_diff is then None.

    Args:
        design_id_a: design_id of the first run.
        run_id_a: run_id of the first run.
        design_id_b: design_id of the second run.
        run_id_b: run_id of the second run.
        out_dir: Root directory the runs were persisted under.
        check_name_topology: If True (default), raise ValueError when the
            two runs' name fingerprints don't match rather than silently
            comparing anyway. Set False only for a deliberate, known
            apples-to-oranges comparison, or when comparing a run persisted
            before this field existed (its fingerprint is absent, not
            empty, and is treated as "not checked" either way, never as a
            match).

    Returns:
        Dict with 'params_a', 'params_b', 'summary_a', 'summary_b', and
        'signature_diff' (None if either run has no signature_spectrum.json).

    Raises:
        FileNotFoundError: If either run's params.json/summary.json is
            missing.
        ValueError: If `check_name_topology` and the two runs' name
            fingerprints disagree (see `_check_name_topology`).
    """
    dir_a = Path(out_dir) / design_id_a / run_id_a
    dir_b = Path(out_dir) / design_id_b / run_id_b

    def _load(run_dir: Path, name: str) -> Dict[str, Any]:
        path = run_dir / name
        if not path.exists():
            raise FileNotFoundError(f"{name} not found for run at {run_dir}")
        return json.loads(path.read_text())

    params_a = _load(dir_a, 'params.json')
    params_b = _load(dir_b, 'params.json')

    if check_name_topology:
        fp_a = params_a.get('name_topology')
        fp_b = params_b.get('name_topology')
        if fp_a is not None and fp_b is not None:
            _check_name_topology(
                fp_a, fp_b,
                f"{design_id_a}/{run_id_a}", f"{design_id_b}/{run_id_b}",
            )

    result = {
        'params_a': params_a,
        'params_b': params_b,
        'summary_a': _load(dir_a, 'summary.json'),
        'summary_b': _load(dir_b, 'summary.json'),
        'signature_diff': None,
    }

    spectrum_path_a = dir_a / 'signature_spectrum.json'
    spectrum_path_b = dir_b / 'signature_spectrum.json'
    if spectrum_path_a.exists() and spectrum_path_b.exists():
        spec_a = signature_spectrum_from_records(json.loads(spectrum_path_a.read_text()))
        spec_b = signature_spectrum_from_records(json.loads(spectrum_path_b.read_text()))
        result['signature_diff'] = diff_signature_spectra(spec_a, spec_b)

    return result


__all__ = ['persist_run_artifacts', 'compare_runs']
