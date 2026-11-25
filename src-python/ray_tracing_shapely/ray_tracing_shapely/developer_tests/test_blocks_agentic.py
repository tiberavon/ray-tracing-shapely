"""
Python-specific module: test block tools
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
The agent's construction tools (24_p8d)
===============================================================================
- the example chain built through the block tools alone, wired by handle,
  gives the numbers the blocks give run directly;
- a handle inside a list; an unsaved trace fed on by handle; null outputs
  not kept; a long value summarised, not inlined;
- refused, with the reason and never raised: a handle of the wrong type, an
  unknown handle, an unknown block or input, a bare number for a quantity;
- a kept scene written to a file is a scene file;
- register() adds the block tools to the three lists once, in agreement
  (C-AGENT-02), and the MCP server publishes and runs them.
===============================================================================
"""

import asyncio
import importlib
import json
import sys

import numpy as np
import pytest

pytest.importorskip("pint")

from ray_tracing_shapely.blocks import agentic as tools  # noqa: E402
from ray_tracing_shapely.blocks import run_block  # noqa: E402

SPECTRUM = [(400.0, 0.0), (450.0, 1.0), (500.0, 0.2), (550.0, 0.6), (650.0, 0.3), (750.0, 0.0)]
DETECTOR = {"p1": [80, -40], "p2": [80, 40], "irradMap": True, "binSize": "10 mm", "name": "det"}


@pytest.fixture(scope="module")
def rayfile_path(tmp_path_factory):
    from ray_tracing_shapely.optical_elements.sources.rayfile import write_tm25
    rng = np.random.default_rng(1)
    n = 300
    th, ph = rng.uniform(-1.3, 1.3, n), rng.uniform(-0.05, 0.05, n)
    dirs = np.c_[np.sin(th) * np.cos(ph), np.sin(th) * np.sin(ph), np.cos(th)]
    pos = np.c_[rng.uniform(-0.4, 0.4, n), rng.uniform(-0.4, 0.4, n), np.zeros(n)]
    return str(write_tm25(tmp_path_factory.mktemp("led") / "led.tm25", pos, dirs, np.cos(th) * 1e-3,
                          spectrum_nm=SPECTRUM))


@pytest.fixture(autouse=True)
def fresh_store():
    tools.clear_values()
    yield
    tools.clear_values()


def _ok(reply):
    assert reply["status"] == "ok", reply
    return reply["data"]


def _out(call, name, inputs, port):
    return _ok(call("block_run", {"name": name, "inputs": inputs}))["outputs"][port]


def _drive_chain(call, rayfile_path):
    """The chain as an agent would build it: each step's handle into the next."""
    sl = _out(call, "slice_rayfile", {"rayfile": rayfile_path, "position": [0, 0], "direction_deg": "0 deg",
                                      "max_offset_mm": "0.5 mm"}, "slice")["ref"]
    src = _out(call, "source_from_slice", {"slice": {"ref": sl}, "name": "led"}, "entry")
    tir = _out(call, "TIRCollimator", {"name": "tir"}, "entry")["ref"]
    det = _out(call, "Detector", DETECTOR, "entry")["ref"]
    scene = _out(call, "assemble", {"entries": [{"ref": src["ref"]}, {"ref": tir}, {"ref": det}]}, "scene")
    trace = _out(call, "trace", {"scene": {"ref": scene["ref"]}}, "trace")
    reading = _out(call, "detector_reading", {"trace": {"ref": trace["ref"]}, "detector": "det"}, "reading")
    irr = _out(call, "physical_reading", {"reading": {"ref": reading["ref"]}, "calibration": "1 W/m",
                                          "detector_length": "80 mm"}, "irradiance")
    weighted = _out(call, "hazard_weighted", {"irradiance": {"ref": irr["ref"]}, "rayfile": rayfile_path,
                                              "hazard": "blue_light"}, "weighted")
    group = _out(call, "classify_iec62471", {"alpha": "5 mrad", "blue_light_irradiance": {"ref": weighted["ref"]}},
                 "classification")
    return {"source": src, "scene": scene, "trace": trace, "reading": reading, "irradiance": irr,
            "weighted": weighted, "classification": group}


def _direct(name, args):
    return getattr(tools, name)(**args)


def test_the_chain_through_the_tools_equals_the_blocks(rayfile_path, tmp_path):
    got = _drive_chain(_direct, rayfile_path)
    sl = run_block("slice_rayfile", {"rayfile": rayfile_path, "position": [0, 0], "direction_deg": "0 deg",
                                     "max_offset_mm": "0.5 mm"})["slice"]
    entries = [run_block("source_from_slice", {"slice": sl, "name": "led"})["entry"],
               run_block("TIRCollimator", {"name": "tir"})["entry"], run_block("Detector", DETECTOR)["entry"]]
    trace = run_block("trace", {"scene": run_block("assemble", {"entries": entries})["scene"],
                                "runs_dir": str(tmp_path)})["trace"]
    reading = run_block("detector_reading", {"trace": trace, "detector": "det"})["reading"]
    irr = run_block("physical_reading", {"reading": reading, "calibration": "1 W/m",
                                         "detector_length": "80 mm"})["irradiance"]
    assert got["reading"]["value"] == reading
    assert got["irradiance"]["value"] == irr
    weighted = run_block("hazard_weighted", {"irradiance": irr, "rayfile": rayfile_path,
                                             "hazard": "blue_light"})["weighted"]
    assert got["weighted"]["value"] == weighted
    group = run_block("classify_iec62471", {"alpha": "5 mrad", "blue_light_irradiance": weighted})
    assert got["classification"]["value"] == group["classification"]


def test_long_values_are_summarised_and_unsaved_traces_kept(rayfile_path):
    got = _drive_chain(_direct, rayfile_path)
    assert "value" not in got["source"] and got["source"]["summary"] == {"name": "led", "type": "RaySetSource",
                                                                         "rays": 300}
    assert [o["name"] for o in got["scene"]["summary"]["objects"]] == ["led", "tir", "det"]
    assert "value" not in got["trace"] and got["trace"]["summary"]["folder"] is None
    assert set(got["trace"]["summary"]["detectors"]) == {"det"}
    kept = _ok(tools.block_values())["values"]
    assert [v["ref"] for v in kept] == [f"v{k}" for k in range(1, len(kept) + 1)]
    assert "profile" not in json.dumps(got["reading"])          # no profile asked; a null output is not kept
    assert tools.block_value(got["trace"]["ref"])["status"] == "error"


def test_a_kept_scene_written_is_a_scene_file(rayfile_path, tmp_path):
    from ray_tracing_shapely.analysis import scene_file as sf
    got = _drive_chain(_direct, rayfile_path)
    assert _ok(tools.block_value(got["scene"]["ref"]))["truncated"] is True
    path = tmp_path / "chain.scene.json"
    _ok(tools.block_value(got["scene"]["ref"], str(path)))
    assert [o.name for o in sf.load_scene(path).objs] == ["led", "tir", "det"]


def test_refusals_answer_and_never_raise(rayfile_path):
    det = _ok(tools.block_run("Detector", DETECTOR))["outputs"]["entry"]["ref"]
    cases = [
        (tools.block_run("assemble", {"entries": [{"ref": "v99"}]}), "no kept value 'v99'"),
        (tools.block_run("physical_reading", {"reading": {"ref": det}, "calibration": "1 W/m",
                                              "detector_length": "80 mm"}), "cannot feed"),
        (tools.block_run("nope", {}), "no block 'nope'"),
        (tools.block_run("Detector", {"p1": [0, 0], "p2": [1, 0], "wrong": 1}), "no input 'wrong'"),
        (tools.block_run("Detector", {"p1": [0, 0], "p2": [1, 0], "binSize": 2}), "unit"),
        (tools.block_run("assemble", {"entries": [{"ref": det}, {"ref": det}]}), "C-LABEL-01"),
        (tools.block_run("assemble", "entries"), "must be an object"),
        (tools.block_describe("nope"), "no block 'nope'"),
        (tools.block_list("nope"), "no block of kind"),
        (tools.block_value("v99"), "no kept value"),
    ]
    for reply, reason in cases:
        assert reply["status"] == "error" and reason in reply["message"], reply


def test_list_and_describe():
    blocks = {b["name"]: b for b in _ok(tools.block_list())["blocks"]}
    assert {"TIRCollimator", "Detector", "slice_rayfile", "trace", "classify_iec62471"} <= set(blocks)
    assert {b["kind"] for b in _ok(tools.block_list("function"))["blocks"]} == {"function"}
    ports = {p["name"]: p for p in _ok(tools.block_describe("physical_reading"))["inputs"]}
    assert ports["calibration"]["type"]["unit"] == "W/m"
    assert ports["symmetry"]["type"] == {"type": "choice", "options": ["extrude", "revolve"]}


def test_register_adds_the_block_tools_once_in_agreement(monkeypatch):
    from ray_tracing_shapely.analysis import tool_registry
    # the lists are process-wide, and a loaded server is given each new tool: restore and hide both
    monkeypatch.setattr(tool_registry, "_REGISTRY", list(tool_registry._REGISTRY))
    monkeypatch.setattr(tool_registry, "_EXTERNAL_TOOLS", [])
    monkeypatch.delitem(sys.modules, "ray_tracing_shapely.analysis.mcp_server", raising=False)
    assert tools.register() is True
    assert tools.register() is False
    names = {t["name"] for t in tool_registry.get_agentic_tools()}
    assert {fn.__name__ for fn, _, _ in tools.TOOLS} <= names
    assert tool_registry.check_tool_lists() == []


@pytest.mark.skipif(importlib.util.find_spec("mcp") is None, reason="mcp not installed (the agentic extra)")
def test_the_mcp_server_publishes_the_tools_and_builds_the_chain(rayfile_path, monkeypatch):
    from ray_tracing_shapely import analysis
    from ray_tracing_shapely.analysis import tool_registry
    monkeypatch.setattr(tool_registry, "_REGISTRY", list(tool_registry._REGISTRY))
    monkeypatch.setattr(tool_registry, "_EXTERNAL_TOOLS", [])
    name = "ray_tracing_shapely.analysis.mcp_server"
    prior_module, prior_attr = sys.modules.pop(name, None), analysis.__dict__.pop("mcp_server", None)
    try:
        assert tools.register()
        mcp_server = importlib.import_module(name)
        published = {t.name for t in asyncio.run(mcp_server.mcp.list_tools())}
        assert {fn.__name__ for fn, _, _ in tools.TOOLS} <= published

        def call(tool, args):
            out = asyncio.run(mcp_server.mcp.call_tool(tool, args))
            content = out[0] if isinstance(out, tuple) else out
            return json.loads(content[0].text)

        got = _drive_chain(call, rayfile_path)
        assert got["classification"]["value"]["group"] in ("Exempt", "RG1", "RG2", "RG3")
    finally:
        sys.modules.pop(name, None)
        analysis.__dict__.pop("mcp_server", None)
        if prior_module is not None:
            sys.modules[name] = prior_module
        if prior_attr is not None:
            analysis.mcp_server = prior_attr
