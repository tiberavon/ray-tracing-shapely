"""
Python translation Copyright 2026 ray-tracing-shapely authors and contributors

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

    http://www.apache.org/licenses/LICENSE-2.0

===============================================================================
PYTHON-SPECIFIC MODULE: Run Persistence and Cross-Run Comparison (Layer 1/3)
===============================================================================
Minimal first slice of dev_doc/roadmap/done/15_p4_run_persistence_and_comparison.md:
persist a run's derived, already-serializable artifacts to disk under
<out_dir>/<design_id>/<run_id>/, and compare two persisted runs' summary.json
without needing a live kernel for either.

graph.json/signature_spectrum.json are written only when a BidirectionalResult
is passed in (analysis.signature_analysis: path_signature/signature_spectrum,
15_p5_nonimaging_optics_implementation_plan.md Phase 1 step 6). Nothing here
reconstructs a live Scene: replay for a historical run goes through the
notebook/papermill_parameters that built it, not a serialized Scene dump (see
15_p4_run_persistence_and_comparison.md §8.6).

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


def compare_runs(
    design_id_a: str,
    run_id_a: str,
    design_id_b: str,
    run_id_b: str,
    *,
    out_dir: Path,
) -> Dict[str, Any]:
    """
    Compare two persisted runs -- no live kernel, no SQLite connection, no
    _CONTEXT/_CONTEXTS entry required for either run.

    Always diffs summary.json (scalar statistics). Also adds a
    signature_diff (15_p2_bidirectional_ray_tracing_rational.md §3.5.1) when both
    runs have a signature_spectrum.json -- i.e. both were persisted with a
    bidirectional_result. Runs without one (plain forward-only sweeps) still
    compare fine on summary.json alone; signature_diff is then None.

    Args:
        design_id_a: design_id of the first run.
        run_id_a: run_id of the first run.
        design_id_b: design_id of the second run.
        run_id_b: run_id of the second run.
        out_dir: Root directory the runs were persisted under.

    Returns:
        Dict with 'params_a', 'params_b', 'summary_a', 'summary_b', and
        'signature_diff' (None if either run has no signature_spectrum.json).

    Raises:
        FileNotFoundError: If either run's params.json/summary.json is
            missing.
    """
    dir_a = Path(out_dir) / design_id_a / run_id_a
    dir_b = Path(out_dir) / design_id_b / run_id_b

    def _load(run_dir: Path, name: str) -> Dict[str, Any]:
        path = run_dir / name
        if not path.exists():
            raise FileNotFoundError(f"{name} not found for run at {run_dir}")
        return json.loads(path.read_text())

    result = {
        'params_a': _load(dir_a, 'params.json'),
        'params_b': _load(dir_b, 'params.json'),
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
