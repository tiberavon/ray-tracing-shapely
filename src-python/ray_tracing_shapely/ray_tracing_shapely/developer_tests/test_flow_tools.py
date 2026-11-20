"""
Python-specific module: test flow tools
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
Questions as data, one verb to answer them, and one set of tools for every flow
===============================================================================
Every box that asks has a `FlowField` and exactly one `provide_*` trigger, so
`answer(value)` answers any of them. A refused answer leaves the flow where it
was, with the reason recorded. Through the generic tools, and through the MCP
server itself, the rayfile slicing flow is driven from start to its table
with nothing but JSON, and its table equals the one its Python methods give.
===============================================================================
"""

from __future__ import annotations

import asyncio
import importlib
import importlib.util
import json
import sys

import numpy as np
import pytest

pytest.importorskip("transitions")
pytest.importorskip("pint")

from ray_tracing_shapely.flows import agentic as tools  # noqa: E402
from ray_tracing_shapely.flows import kinds, persistence  # noqa: E402
from ray_tracing_shapely.flows.fields import REQUIRED, FlowField  # noqa: E402
from ray_tracing_shapely.optical_elements.sources import write_tm25  # noqa: E402
from ray_tracing_shapely.optical_elements.sources.rayfile_slicing_flow import RayfileSlicingFlow  # noqa: E402


def _four_dies(path, n=6000, seed=7):
    rng = np.random.default_rng(seed)
    die = rng.integers(0, 4, n)
    cx, cy = np.where(die % 2 == 0, -0.6, 0.6), np.where(die < 2, -0.6, 0.6)
    pos = np.c_[cx + 0.8 * (rng.random(n) - 0.5), cy + 0.8 * (rng.random(n) - 0.5), np.zeros(n)]
    s, phi = np.sqrt(rng.random(n)), 2 * np.pi * rng.random(n)
    write_tm25(path, pos, np.c_[s * np.cos(phi), s * np.sin(phi), np.sqrt(1.0 - s ** 2)], np.full(n, 1.0 / n),
               name="four dies")
    return str(path)


def test_a_field_shapes_answers_and_reads_as_json():
    f = FlowField("kept_range", "share_range", "Which range?", "the table marks it", "[0.5, 0.75]",
                  default=(0.5, 0.75))
    assert f.coerce([0.4, 0.6]) == (0.4, 0.6) and not f.required
    assert f.to_dict()["default"] == [0.5, 0.75] and json.dumps(f.to_dict())
    n = FlowField("n", "integer", "How many?", "rows", "10")
    assert n.coerce(10.0) == 10 and n.required and n.default is REQUIRED and "default" not in n.to_dict()
    for field, bad in ((n, True), (n, "10"), (f, [0.5]), (FlowField("b", "bool", "?", "", ""), "true"),
                       (FlowField("p", "path", "?", "", ""), 3)):
        with pytest.raises(ValueError):
            field.coerce(bad)
    c = FlowField("c", "choice", "?", "", "", choices=("a", "b"))
    assert c.coerce("a") == "a" and c.to_dict()["choices"] == ["a", "b"]
    with pytest.raises(ValueError, match="one of"):
        c.coerce("z")
    with pytest.raises(ValueError, match="kind must be"):
        FlowField("x", "colour", "?", "", "")


@pytest.mark.parametrize("kind", ["rayfile_slicing", "iec62471_intake", "iec60825_1_intake",
                                  "targeted_resimulation"])
def test_every_asking_box_has_a_field_and_one_trigger(kind, tmp_path):
    flow = kinds.get_flow_kind(kind).start(tmp_path)
    states = [s for s in flow.machine.states if s.startswith("awaiting_")]
    assert states and set(states) == set(flow.FIELDS)
    for state in states:
        provide = [t for t in flow.machine.get_triggers(state) if t.startswith("provide_")]
        assert len(provide) == 1, (state, provide)
    assert list(flow.FIELDS) == states          # the questions in the diagram's order
    assert flow.pending_field().name == flow.FIELDS[flow.state].name


def test_answer_refuses_shapes_and_checks_and_keeps_the_flow_in_place(tmp_path):
    path = _four_dies(tmp_path / "dies.TM25RAY")
    flow = RayfileSlicingFlow(tmp_path / "runs", render_svg=False)
    assert flow.answer(3)["reason"].startswith("rayfile takes a path")
    example = flow.FIELDS["awaiting_rayfile"].example
    assert flow.answer()["reason"] == f"rayfile: no answer given -- {example}"
    assert flow.answer_default()["reason"] == f"rayfile has no default: it must be answered -- {example}"
    # a path the reader cannot read is accepted, and sent back to the same question, saying why
    missing = flow.answer(str(tmp_path / "missing.TM25RAY"))
    assert missing["accepted"] and missing["sent_back"]["from"] == missing["sent_back"]["to"] == "rayfile"
    assert "could not be read" in missing["sent_back"]["reason"]
    assert flow.answer(path)["question"]["name"] == "package_width"
    bare = flow.answer(3)
    assert not bare["accepted"] and "bare number" in bare["reason"] and flow.state == "awaiting_package_width"
    assert bare["reason"].endswith('-- e.g. "7 mm"') and "sent_back" not in bare
    assert bare["last_refusal"] == {"field": "package_width", "value": 3, "reason": bare["reason"]}
    assert "refused" in flow.explain_current_state()
    events = persistence.read_events(tmp_path / "runs", flow.run_id)
    assert events[-1]["refused"] and events[-1]["field"] == "package_width"
    # an accepted answer the next check rejects sends the flow back, saying why
    assert "sent_back" not in flow.answer("0.5 mm")
    back = flow.answer("0.5 mm")
    assert back["accepted"] and back["state"] == "awaiting_package_width" and "outside" in back["explanation"]
    assert back["last_refusal"] is None
    assert back["sent_back"]["from"] == "package_length" and back["sent_back"]["to"] == "package_width"
    assert "outside a 0.5 x 0.5 mm package" in back["sent_back"]["reason"]
    events = persistence.read_events(tmp_path / "runs", flow.run_id)
    assert events[-1]["sent_back"] and events[-1]["to"] == "package_width"
    flow.answer("3 mm")
    flow.answer("3 mm")
    zero = flow.answer(0)["reason"]
    assert zero.startswith("n_slices must be a positive integer") and zero.endswith("e.g. 10 (the default)")
    assert flow.answer_default()["question"]["name"] == "kept_range"
    assert flow.answer([0.5, 0.75])["question"]["name"] == "choice"
    assert flow.answer(0.6)["question"]["name"] == "profile"
    done = flow.answer_default()
    assert done["state"] == "done" and done["finished"] and done["question"] is None
    assert flow.answer(1)["reason"] == "done: nothing is being asked"

    by_methods = RayfileSlicingFlow(tmp_path / "runs", render_svg=False)
    for call in (lambda: by_methods.provide_rayfile(path), lambda: by_methods.provide_package_width("3 mm"),
                 lambda: by_methods.provide_package_length("3 mm"), by_methods.provide_n_slices,
                 by_methods.provide_kept_range, lambda: by_methods.provide_choice(0.6),
                 by_methods.provide_profile):
        call()
    assert by_methods.result["rows"] == flow.result["rows"]


def test_a_hazard_value_asks_in_the_unit_alpha_implies(tmp_path):
    flow = kinds.get_flow_kind("iec62471_intake").start(tmp_path)
    flow.answer("30 deg")
    for _ in range(2):                       # actinic_uv, near_uv: not applicable, so no value asked
        q = flow.answer(False)["question"]
    assert q["name"] == "blue_light_applicable"
    q = flow.answer(True)["question"]
    assert q["name"] == "blue_light_value" and q["unit"] == "W/(m^2 * sr)" and "55 W/(m^2 * sr)" in q["example"]
    assert not flow.answer("55 W/m^2")["accepted"]          # an irradiance where a radiance is due
    flow.answer("55 W/(m^2 * sr)")
    for _ in range(2):
        flow.answer(False)
    assert flow.state == "done" and flow.launched_result == "Exempt"


def _drive_slicing(call, path):
    """The slicing flow, start to table, with JSON only: ``call(tool, args) -> envelope``."""
    kinds_out = call("flow_kinds", {})
    assert kinds_out["status"] == "ok"
    slicing = next(k for k in kinds_out["data"]["kinds"] if k["kind"] == "rayfile_slicing")
    assert [q["name"] for q in slicing["questions"]] == ["rayfile", "package_width", "package_length",
                                                         "n_slices", "kept_range", "choice", "profile"]
    run = call("flow_start", {"kind": "rayfile_slicing"})["data"]
    run_id = run["run_id"]
    assert run["question"]["name"] == "rayfile" and run["question"]["kind"] == "path"
    assert call("flow_answer", {"run_id": run_id, "value": path})["data"]["accepted"]
    refused = call("flow_answer", {"run_id": run_id, "value": 3})["data"]
    assert not refused["accepted"] and refused["question"]["name"] == "package_width"
    for value in ("3 mm", "3 mm"):
        assert call("flow_answer", {"run_id": run_id, "value": value})["data"]["accepted"]
    assert call("flow_question", {"run_id": run_id})["data"]["question"]["default"] == 10
    call("flow_answer", {"run_id": run_id, "use_default": True})
    choose = call("flow_answer", {"run_id": run_id, "value": [0.5, 0.75]})["data"]
    assert choose["question"]["name"] == "choice" and "| Limit on h (mm) |" in choose["context"]["table"]
    assert call("flow_answer", {"run_id": run_id, "value": "1 mm"})["data"]["question"]["name"] == "profile"
    end = call("flow_answer", {"run_id": run_id, "value": False})["data"]
    assert end["finished"] and end["state"] == "done"
    result = call("flow_result", {"run_id": run_id})["data"]
    assert result["finished"] and len(result["result"]["result"]["rows"]) == 10
    assert result["result"]["result"]["choice"]["max_offset_mm"] == 1.0
    assert any(e.get("refused") for e in result["events"])
    again = call("flow_reset", {"run_id": run_id})["data"]
    assert again["attempt"] == 2 and again["question"]["name"] == "rayfile"
    assert call("flow_question", {"run_id": run_id})["data"]["last_refusal"] is None
    return result["result"]["result"]


def test_the_generic_tools_drive_the_slicing_flow(tmp_path):
    path = _four_dies(tmp_path / "dies.TM25RAY")
    tools.set_runs_root(tmp_path / "flow_runs")
    try:
        table = _drive_slicing(lambda name, args: getattr(tools, name)(**args), path)
    finally:
        tools.set_runs_root(None)
    assert tools.runs_root().name == "flow_runs"
    direct = RayfileSlicingFlow(tmp_path / "direct", render_svg=False)
    for v in (path, "3 mm", "3 mm", 10, [0.5, 0.75], "1 mm", False):
        direct.answer(v)
    assert table["rows"] == json.loads(json.dumps(direct.result["rows"]))
    assert tools.flow_start("nope")["status"] == "error" and "known" in tools.flow_start("nope")["message"]
    assert tools.flow_answer("nope", 1)["status"] == "error"
    assert tools.flow_result("nope", base_dir=str(tmp_path))["status"] == "error"


@pytest.mark.skipif(importlib.util.find_spec("mcp") is None, reason="mcp not installed (the agentic extra)")
def test_the_mcp_server_publishes_the_nine_tools_and_drives_the_flow(tmp_path, monkeypatch):
    from ray_tracing_shapely import analysis
    from ray_tracing_shapely.analysis import tool_registry
    monkeypatch.setattr(tool_registry, "_REGISTRY", list(tool_registry._REGISTRY))
    monkeypatch.setattr(tool_registry, "_EXTERNAL_TOOLS", [])
    monkeypatch.setattr(tools, "_RUNS_ROOT", tmp_path / "flow_runs")
    # a fresh server, built from the lists as they now are; whatever server module was
    # imported before (or none) is put back afterwards, so no later test sees this one
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

        table = _drive_slicing(call, _four_dies(tmp_path / "dies.TM25RAY"))
        assert table["half_diagonal_mm"] == pytest.approx(1.5 * 2 ** 0.5)
    finally:
        sys.modules.pop(name, None)
        analysis.__dict__.pop("mcp_server", None)
        if prior_module is not None:
            sys.modules[name] = prior_module
        if prior_attr is not None:
            analysis.mcp_server = prior_attr
