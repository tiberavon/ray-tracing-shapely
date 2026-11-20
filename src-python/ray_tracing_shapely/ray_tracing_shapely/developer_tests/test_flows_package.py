"""
Python-specific module: test flows package
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
The flow machine as its own package
===============================================================================
The machine, a run's record, the question record and the dashboard moved out
of the eye-safety package into `flows`. The old paths must give the same
objects, not copies. A run's record must be readable without the machine's
dependencies, and the rayfile slicing flow must not load the eye-safety flows.
===============================================================================
"""

from __future__ import annotations

import subprocess
import sys
import textwrap

import pytest

pytest.importorskip("transitions")


def test_the_old_paths_are_the_same_objects():
    from ray_tracing_shapely import flows
    from ray_tracing_shapely.flows import dashboard, flow_base, persistence
    from ray_tracing_shapely.optical_elements import eye_safety_classification_flow as old
    from ray_tracing_shapely.optical_elements import units
    from ray_tracing_shapely.optical_elements.eye_safety_classification_flow import dashboard as old_dashboard
    from ray_tracing_shapely.optical_elements.eye_safety_classification_flow import dimensional_checks, explanations
    from ray_tracing_shapely.optical_elements.eye_safety_classification_flow import flow_base as old_flow_base
    from ray_tracing_shapely.optical_elements.eye_safety_classification_flow import persistence as old_persistence

    assert (old_persistence, old_flow_base, old_dashboard) == (persistence, flow_base, dashboard)
    assert old.ObservableFlow is flows.ObservableFlow is flow_base.ObservableFlow
    assert old.FieldExplanation is explanations.FieldExplanation is flows.FieldExplanation
    assert old.read_events is flows.read_events is persistence.read_events
    assert old.checked_scalar is dimensional_checks.checked_scalar is units.checked_scalar


def _run(code: str) -> str:
    out = subprocess.run([sys.executable, "-c", textwrap.dedent(code)], capture_output=True, text=True)
    assert out.returncode == 0, out.stderr
    return out.stdout.strip()


def test_a_run_record_is_read_without_the_machine():
    # transitions, graphviz and pint blocked: the record and the question are standard library only
    out = _run("""
        import builtins
        real = builtins.__import__
        def guarded(name, *a, **kw):
            if name.split(".")[0] in {"transitions", "graphviz", "pint"}:
                raise ModuleNotFoundError(name)
            return real(name, *a, **kw)
        builtins.__import__ = guarded
        from ray_tracing_shapely.flows import persistence, explain_field, read_heartbeats
        from ray_tracing_shapely.flows import dashboard
        try:
            from ray_tracing_shapely.flows import ObservableFlow
        except ModuleNotFoundError as e:
            print("machine needs", e)
    """)
    assert out == "machine needs transitions"


def test_the_slicing_flow_does_not_load_the_eye_safety_flows():
    # `optical_elements` itself loads the standards' formulas (`eye_safety`); the flows are another package
    out = _run("""
        import sys
        from ray_tracing_shapely.optical_elements.sources.rayfile_slicing_flow import RayfileSlicingFlow
        print(sorted(m for m in sys.modules if "eye_safety_classification_flow" in m))
    """)
    assert out == "[]"


def test_flows_imports_nothing_of_ours_but_the_tool_registry():
    # flows sits under every flow (eye safety, sources, the satellite's): it may
    # reach only the tool registry, and only to register its own tools
    from ray_tracing_shapely.developer_tests.test_architecture_layering import _subpackage_imports
    crossings = {(p.name, imp) for p, imp in _subpackage_imports("flows")}
    assert crossings <= {("agentic.py", "analysis")}, crossings
