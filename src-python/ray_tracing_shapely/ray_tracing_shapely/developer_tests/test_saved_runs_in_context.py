"""
Python-specific module: test saved runs in context
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
Saved runs in the agentic context registry: saved, loaded by reference, compared
===============================================================================
A live bidirectional DTIRC run is saved with save_context_tool and loaded back
with load_run_context into a second named context: the loaded one answers the
database and path questions as the live one did, with no live scene, and the
tools that need the scene say why they cannot. Two saved runs (n=1.5 and
n=1.8) are compared from disk, by folder or by context name.
===============================================================================
"""
import sqlite3
from pathlib import Path

import pytest

from ray_tracing_shapely.analysis import agentic_tools
from ray_tracing_shapely.analysis.agentic_tools import (
    compare_persisted_runs_tool,
    drop_context,
    get_context,
    get_extension_context,
    list_contexts,
    list_detectors,
    load_run_context,
    path_physical_summary_tool,
    query_rays,
    rank_bidirectional_paths,
    rank_paths_by_energy,
    register_run_file_loader,
    save_context_tool,
    set_active_context,
    set_bidirectional_context,
    set_context,
    set_context_from_result,
)
from ray_tracing_shapely.analysis.tool_registry import check_tool_lists, get_agentic_tools, get_exposed_tools
from ray_tracing_shapely.core.scene import Scene
from ray_tracing_shapely.core.scene_objs.glass.glass import Glass
from ray_tracing_shapely.core.scene_objs.light_source.single_ray import SingleRay
from ray_tracing_shapely.core.simulator import Simulator

from test_signature_analysis import _build_and_run_dtirc_bidirectional


def _live(n_prism):
    scene, sim, bidir = _build_and_run_dtirc_bidirectional(n_prism=n_prism)
    return scene, sim.run_with_result(name=f'dtirc_n{n_prism}'), bidir


@pytest.fixture(scope="module")
def runs():
    return {1.5: _live(1.5), 1.8: _live(1.8)}


@pytest.fixture(scope="module")
def saved(runs, tmp_path_factory):
    """Both runs saved under one out_dir, through the tool."""
    out_dir = tmp_path_factory.mktemp("runs")
    dirs = {}
    for n, (scene, result, bidir) in runs.items():
        set_context_from_result(scene, result)
        set_bidirectional_context(bidir)
        out = save_context_tool(str(out_dir), 'dtirc', f'n{n}', physical_params={'n_prism': n},
                                numerical_params={'ray_density': 8})
        assert out["status"] == "ok", out
        dirs[n] = Path(out["data"]["run_dir"])
    agentic_tools.clear_context()
    return out_dir, dirs


def _count(sql):
    out = query_rays(sql)
    assert out["status"] == "ok", out
    return out["data"]["rows"][0][0]


def _energies():
    out = rank_bidirectional_paths(top_n=5)
    assert out["status"] == "ok", out
    return [round(p["energy"], 12) for p in out["data"]]


def test_a_saved_run_loads_by_reference_and_answers_as_the_live_one_did(runs, saved):
    scene, result, bidir = runs[1.5]
    set_context_from_result(scene, result)
    set_bidirectional_context(bidir)
    live = (_count("SELECT COUNT(*) FROM rays"), _count("SELECT COUNT(*) FROM rays WHERE tree = 'backward'"),
            _count("SELECT COUNT(*) FROM connections"), _energies())
    assert live[1] > 0 and live[2] > 0 and live[3]

    out = load_run_context(str(saved[1][1.5]), "saved")
    assert out["status"] == "ok", out
    assert out["data"]["loaded"] == ["rays.sqlite", "graph.json"]
    assert out["data"]["params"]["physical_params"] == {"n_prism": 1.5}
    assert list_contexts()["data"]["active"] == "default"                    # loading never switches

    set_active_context("saved")
    assert (_count("SELECT COUNT(*) FROM rays"), _count("SELECT COUNT(*) FROM rays WHERE tree = 'backward'"),
            _count("SELECT COUNT(*) FROM connections"), _energies()) == live
    (summary,) = [c for c in list_contexts()["data"]["contexts"] if c["name"] == "saved"]
    assert summary["origin"] == "saved run" and not summary["has_scene"] and summary["has_bidirectional"]
    assert summary["run_dir"] == str(saved[1][1.5]) and summary["n_segments"] == result.segment_count


def test_the_tools_that_need_the_scene_say_the_run_was_loaded(saved):
    load_run_context(str(saved[1][1.5]), "saved")
    set_active_context("saved")
    for out in (list_detectors(), rank_paths_by_energy()):
        assert out["status"] == "error" and "loaded from the saved run" in out["message"], out
    path = rank_bidirectional_paths(top_n=1)["data"][0]["path_uuids"]
    out = path_physical_summary_tool(path)
    assert out["status"] == "error" and "lineages" in out["message"]


def test_a_loaded_database_is_read_only(saved):
    load_run_context(str(saved[1][1.5]), "saved")
    with pytest.raises(sqlite3.OperationalError, match="readonly"):
        get_context("saved")["db"].execute("DELETE FROM rays")


def test_a_name_in_use_or_a_folder_with_no_run_is_refused(saved, tmp_path):
    assert load_run_context(str(saved[1][1.5]), "saved")["status"] == "ok"
    out = load_run_context(str(saved[1][1.8]), "saved")
    assert out["status"] == "error" and "already loaded" in out["message"]
    (tmp_path / "result.json").write_text("{}")
    out = load_run_context(str(tmp_path), "empty")
    assert out["status"] == "error" and "result.json" in out["message"]
    assert load_run_context(str(tmp_path / "nope"), "nope")["status"] == "error"
    assert [c["name"] for c in list_contexts()["data"]["contexts"]] == ["default", "saved"]


def test_saving_never_overwrites_and_needs_a_result(runs, saved, tmp_path):
    out_dir, dirs = saved
    scene, result, _ = runs[1.5]
    set_context_from_result(scene, result)
    out = save_context_tool(str(out_dir), 'dtirc', 'n1.5')
    assert out["status"] == "error" and "never overwritten" in out["message"]
    assert save_context_tool(str(out_dir), 'dtirc', '../x')["status"] == "error"
    set_context(scene, result.segments)                                       # segments only: no result
    out = save_context_tool(str(tmp_path), 'dtirc', 'segments_only')
    assert out["status"] == "error" and "set_context_from_result" in out["message"]
    load_run_context(str(dirs[1.5]), "saved")
    out = save_context_tool(str(tmp_path), 'dtirc', 'again', context_name="saved")
    assert out["status"] == "error" and "saved run already" in out["message"]


def test_two_saved_runs_compare_by_folder_and_by_context_name(saved):
    _, dirs = saved
    out = compare_persisted_runs_tool(str(dirs[1.5]), str(dirs[1.8]), top_n=3)
    assert out["status"] == "ok", out
    data = out["data"]
    assert (data["params_a"]["physical_params"], data["params_b"]["physical_params"]) == \
        ({"n_prism": 1.5}, {"n_prism": 1.8})
    diff = data["signature_diff"]
    assert diff["signatures"] > 0 and len(diff["listed"]) <= 3
    changes = [abs(r["energy_a"] - r["energy_b"]) for r in diff["listed"]]
    assert changes == sorted(changes, reverse=True) and changes[0] > 0

    load_run_context(str(dirs[1.5]), "a")
    by_name = compare_persisted_runs_tool("a", str(dirs[1.8]), top_n=3)
    assert by_name["data"]["signature_diff"] == diff
    out = compare_persisted_runs_tool("default", str(dirs[1.8]))
    assert out["status"] == "error"


def _named_prism_run(name):
    scene = Scene()
    prism = Glass(scene)
    prism.path = [{'x': 200, 'y': 50, 'arc': False}, {'x': 250, 'y': 100, 'arc': False},
                  {'x': 150, 'y': 100, 'arc': False}]
    prism.refIndex = 1.5
    prism.name = name
    scene.add_object(prism)
    ray = SingleRay(scene)
    ray.p1, ray.p2, ray.brightness = {'x': 100, 'y': 90}, {'x': 250, 'y': 90}, 1.0
    ray.name = 'ray'
    scene.add_object(ray)
    return scene, Simulator(scene).run_with_result()


def test_runs_naming_different_objects_are_not_compared(tmp_path):
    for name in ('prism', 'prism_n1.6'):
        set_context_from_result(*_named_prism_run(name))
        assert save_context_tool(str(tmp_path), 'p', name)["status"] == "ok"
    out = compare_persisted_runs_tool(str(tmp_path / 'p' / 'prism'), str(tmp_path / 'p' / 'prism_n1.6'))
    assert out["status"] == "error" and "C-LABEL-01" in out["message"]
    out = compare_persisted_runs_tool(str(tmp_path / 'p' / 'prism'), str(tmp_path / 'p' / 'prism_n1.6'),
                                      check_name_topology=False)
    assert out["status"] == "ok" and out["data"]["signature_diff"] is None


def test_a_file_a_package_knows_is_loaded_into_the_same_context(saved, monkeypatch):
    monkeypatch.setattr(agentic_tools, "_RUN_FILE_LOADERS", {})
    _, dirs = saved
    (dirs[1.8] / "extra.sqlite").write_bytes(b"")
    try:
        register_run_file_loader(
            "extra.sqlite",
            lambda path, name: agentic_tools.set_extension_context("pkg.extra", {"path": path}, context_name=name))
        out = load_run_context(str(dirs[1.8]), "both")
        assert out["data"]["loaded"] == ["rays.sqlite", "graph.json", "extra.sqlite"]
        set_active_context("both")
        assert get_extension_context("pkg.extra", "missing")["path"].name == "extra.sqlite"
    finally:
        (dirs[1.8] / "extra.sqlite").unlink()


def test_only_a_saved_inactive_context_is_dropped_and_it_reloads(runs, saved, tmp_path):
    scene, result, bidir = runs[1.5]
    set_context_from_result(scene, result, context_name="live")             # never saved
    assert load_run_context(str(saved[1][1.5]), "loaded")["status"] == "ok"
    set_active_context("loaded")

    refused = drop_context("live")
    assert refused["status"] == "error" and "save_context_tool" in refused["message"]
    refused = drop_context("loaded")
    assert refused["status"] == "error" and "active" in refused["message"]
    assert drop_context("nope")["status"] == "error"

    set_active_context("live")
    before = _count("SELECT COUNT(*) FROM rays")
    set_active_context("loaded")
    n = _count("SELECT COUNT(*) FROM rays")
    set_active_context("live")
    out = drop_context("loaded")
    assert out["status"] == "ok" and out["data"]["reload_from"] == str(saved[1][1.5])
    assert "loaded" not in [c["name"] for c in list_contexts()["data"]["contexts"]] and get_context("live")
    assert _count("SELECT COUNT(*) FROM rays") == before                     # the active one untouched

    assert load_run_context(out["data"]["reload_from"], "loaded")["status"] == "ok"
    set_active_context("loaded")
    assert _count("SELECT COUNT(*) FROM rays") == n                          # back as it was

    set_active_context("live")
    assert save_context_tool(str(tmp_path), "dtirc", "live")["status"] == "ok"
    set_active_context("loaded")
    assert drop_context("live")["status"] == "ok"                            # saved now: droppable


def test_the_tools_are_in_the_lists():
    names = {t["name"] for t in get_agentic_tools()}
    exposed = {f.__name__ for f in get_exposed_tools()}
    assert {"load_run_context", "save_context_tool", "compare_persisted_runs_tool", "drop_context"} <= \
        names & exposed
    assert check_tool_lists() == []
