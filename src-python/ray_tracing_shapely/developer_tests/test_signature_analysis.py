"""
===============================================================================
SIGNATURE ANALYSIS TESTS -- Nonimaging Optics Phase 1, Step 6
===============================================================================
Tests analysis.signature_analysis (path_signature/signature_spectrum/
diff_signature_spectra) and the edge_index/arc_position node-attribute fix in
analysis.bidirectional._add_tree_to_graph, exercised against a real
DTIRCPrism run_bidirectional() pass. Also covers persist_run_artifacts'/
compare_runs' extension for graph.json/signature_spectrum.json/signature_diff
(analysis.run_registry).

Run with:
    python developer_tests/test_signature_analysis.py
Or with pytest:
    pytest developer_tests/test_signature_analysis.py -v
===============================================================================
"""

import json
import sys
import tempfile
from pathlib import Path

src_path = Path(__file__).parent.parent
if str(src_path) not in sys.path:
    sys.path.insert(0, str(src_path))


def _build_and_run_dtirc_bidirectional(n_prism, ray_density=8):
    """Build a DTIRCPrism scene with a detector at the exit aperture, run
    it bidirectionally, return (scene, sim, BidirectionalResult)."""
    from ray_tracing_shapely.core.scene import Scene
    from ray_tracing_shapely.core.scene_objs.light_source.angle_source import AngleSource
    from ray_tracing_shapely.core.scene_objs.other.detector import Detector
    from ray_tracing_shapely.core.simulator import Simulator
    from ray_tracing_shapely.optical_elements.prisms.dtirc import DTIRCPrism

    scene = Scene()
    scene.ray_density = ray_density

    prism = DTIRCPrism(scene, theta_deg=10.0, n=n_prism, size=30.0, position=(0, 0))
    prism.name = 'dtirc'
    scene.add_object(prism)

    # R1/R2 (exit aperture corners) are path[0]/path[1] -- place the
    # detector spanning them, offset slightly below into the air.
    r1 = prism.path[0]
    r2 = prism.path[1]
    offset = 2.0
    det = Detector(scene, {
        'type': 'Detector',
        'p1': {'x': r1['x'], 'y': r1['y'] - offset},
        'p2': {'x': r2['x'], 'y': r2['y'] - offset},
        'irrad_map': True,
        'bin_size': 1.0,
    })
    det.name = 'exit_detector'
    scene.add_object(det)

    source = AngleSource(scene)
    source.p1 = {'x': 0, 'y': 60}
    source.p2 = {'x': 0, 'y': 40}
    source.emis_angle = 40.0
    source.symmetric = True
    source.brightness = 1.0
    source.name = 'src'
    scene.add_object(source)

    sim = Simulator(scene, max_rays=5000, record_surface_hits=True)
    result = sim.run_bidirectional(
        det, acceptance_angle_deg=30, origin_samples=10, direction_samples=8,
        spatial_tolerance=1.0, angular_tolerance_deg=5.0,
    )
    return scene, sim, result


def test_edge_index_present_on_graph_nodes():
    """The bidirectional.py fix: nodes on a named surface carry a real
    edge_index, not just connection edges (test_combined_graph_is_attributed
    already covers connection edges; this covers nodes)."""
    scene, sim, result = _build_and_run_dtirc_bidirectional(n_prism=1.5)
    assert result.combined is not None, "expected a combined graph"

    dtirc_nodes_with_edge_index = [
        (n, d) for n, d in result.combined.nodes(data=True)
        if d.get('surface_name') == 'dtirc' and d.get('edge_index') is not None
    ]
    assert dtirc_nodes_with_edge_index, (
        "expected at least one 'dtirc'-surface node with a real edge_index"
    )
    # arc_position should be a finite, non-negative arc-length.
    for _, d in dtirc_nodes_with_edge_index:
        assert d['arc_position'] is not None and d['arc_position'] >= 0.0
    print(f"  PASS: {len(dtirc_nodes_with_edge_index)} nodes on 'dtirc' carry edge_index/arc_position")
    return True


def test_path_signature_and_spectrum():
    """path_signature/signature_spectrum produce well-formed, energy-bounded output."""
    from ray_tracing_shapely.analysis.bidirectional import extract_ranked_paths
    from ray_tracing_shapely.analysis.signature_analysis import path_signature, signature_spectrum

    scene, sim, result = _build_and_run_dtirc_bidirectional(n_prism=1.5)
    paths = extract_ranked_paths(result.combined, top_n=50)
    assert paths, "expected at least one source->detector path"

    sig = path_signature(paths[0], result.combined)
    assert isinstance(sig, tuple) and len(sig) == len(paths[0]['path_uuids'])
    for surface_name, edge_index, interaction_type in sig:
        assert interaction_type in ('source', 'reflect', 'refract', 'tir', None)

    spectrum = signature_spectrum(result, top_n=50)
    assert spectrum, "expected a non-empty signature spectrum"
    total_energy = sum(v['energy'] for v in spectrum.values())
    assert 0.0 < total_energy <= len(paths) + 1e-6, (
        f"total spectrum energy {total_energy} out of plausible range"
    )
    print(f"  PASS: {len(spectrum)} distinct signatures, total energy {total_energy:.4f}")
    return True


def test_path_surfaces_hop_pairing():
    """path_surfaces (15_p8 item 2) correctly re-pairs each hop's location
    with the interaction_type that happened there, unlike path_types'
    off-by-one node-own-attribute reading -- verified on a real path with
    interior hops on BOTH sides of the surface connection (forward_len>=2,
    backward_len>=3), so both the 'look-ahead' (forward tree) and
    'look-behind' (backward tree) resolution branches are exercised."""
    from ray_tracing_shapely.analysis.bidirectional import extract_ranked_paths
    from ray_tracing_shapely.analysis.signature_analysis import path_surfaces

    scene, sim, result = _build_and_run_dtirc_bidirectional(n_prism=1.5)
    paths = extract_ranked_paths(result.combined, top_n=500)
    candidate = next(
        (p for p in paths if p['forward_len'] >= 2 and p['backward_len'] >= 3),
        None,
    )
    assert candidate is not None, (
        "expected some ranked path with forward_len>=2 and backward_len>=3 "
        "among the top 500 -- fixture/ranking may have changed"
    )

    hops = path_surfaces(candidate, result.combined)
    path_uuids = candidate['path_uuids']
    n = len(path_uuids)
    assert len(hops) == n == len(candidate['path_types'])

    fwd_len = candidate['forward_len']
    # Endpoints keep their own sentinel type (emission point, not a hit).
    assert hops[0]['interaction_type'] == result.combined.nodes[path_uuids[0]]['interaction_type']
    assert hops[-1]['interaction_type'] == result.combined.nodes[path_uuids[-1]]['interaction_type']

    # The two hops straddling the surface connection are structurally
    # unresolvable from the graph alone (see path_surfaces' docstring).
    conn_idx_a, conn_idx_b = fwd_len - 1, fwd_len
    assert hops[conn_idx_a]['interaction_type'] is None
    assert hops[conn_idx_b]['interaction_type'] is None

    # Every other interior hop IS resolved (a real interaction_type, not None).
    for i in range(1, n - 1):
        if i in (conn_idx_a, conn_idx_b):
            continue
        assert hops[i]['interaction_type'] in ('reflect', 'refract', 'tir'), (
            f"hop {i} unexpectedly unresolved: {hops[i]}"
        )

    # Location fields are always populated for real surface hits.
    for i, hop in enumerate(hops):
        assert hop['surface_name'] == 'dtirc'
        assert hop['edge_index'] is not None
        assert hop['hit_point_x'] is not None and hop['hit_point_y'] is not None
        assert hop['tree'] == ('forward' if i < fwd_len else 'backward')

    print(f"  PASS: {n}-hop path (forward_len={fwd_len}, backward_len={candidate['backward_len']}) "
          f"correctly paired, only the 2 connection-adjacent hops unresolved")
    return True


def test_audit_paths_flags_max_hops_and_edges():
    """audit_paths (15_p8 item 3) flags paths by hop-count and by touching
    edges outside an allow-list, and leaves everything unflagged when given
    neither constraint."""
    from ray_tracing_shapely.analysis.signature_analysis import audit_paths

    scene, sim, result = _build_and_run_dtirc_bidirectional(n_prism=1.5)

    # No constraints -- nothing flagged, but totals still populated.
    report_none = audit_paths(result, top_n=50)
    assert report_none['total_paths'] > 0
    assert report_none['flagged_paths'] == []
    assert report_none['flagged_energy'] == 0.0
    assert report_none['flagged_energy_fraction'] == 0.0

    # top_n=500 mixes minimal 3-hop (single-bounce) paths with longer ones
    # (verified: 298 at exactly 3 hops, 180 longer, out of 478 total) --
    # expected_max_hops=3 must flag a real, strict subset, not all-or-nothing.
    report_hops = audit_paths(result, top_n=500, expected_max_hops=3)
    assert 0 < len(report_hops['flagged_paths']) < report_hops['total_paths']
    assert 0.0 < report_hops['flagged_energy'] < report_hops['total_energy'] + 1e-9
    for entry in report_hops['flagged_paths']:
        assert entry['path_length'] > 3
        assert any('expected_max_hops' in r for r in entry['flag_reasons'])

    # allowed_edges naming an edge_index that doesn't exist on 'dtirc' --
    # every path has an interior hop on 'dtirc', so every path is flagged.
    report_edges = audit_paths(result, top_n=50, allowed_edges=[('dtirc', 999)])
    assert len(report_edges['flagged_paths']) == report_edges['total_paths']
    assert abs(report_edges['flagged_energy_fraction'] - 1.0) < 1e-9

    # allowed_edges with edge_index=None ("any edge on this surface") --
    # 'dtirc' is the only surface touched, so nothing is flagged.
    report_any_edge = audit_paths(result, top_n=50, allowed_edges=[('dtirc', None)])
    assert report_any_edge['flagged_paths'] == []

    print(f"  PASS: max_hops flags {len(report_hops['flagged_paths'])}/{report_hops['total_paths']}, "
          f"disallowed edge flags all, edge_index=None allows all")
    return True


def test_path_physical_summary_reciprocity():
    """path_physical_summary (15_p8 item 4) reconstructs plausible
    brightness/polarization/length at the detector, and raises ValueError
    for a path_dict with no surface connection."""
    from ray_tracing_shapely.analysis.bidirectional import extract_ranked_paths
    from ray_tracing_shapely.analysis.signature_analysis import path_physical_summary

    scene, sim, result = _build_and_run_dtirc_bidirectional(n_prism=1.5)
    paths = extract_ranked_paths(result.combined, top_n=10)
    assert paths, "expected at least one source->detector path"

    summary = path_physical_summary(paths[0], result)
    for key in ('total_length', 'brightness_s_at_detector', 'brightness_p_at_detector',
                'degree_of_polarization_at_detector', 'polarization_ratio_at_detector',
                'adaptive_sampling_warning'):
        assert key in summary, f"missing key {key!r} in {summary}"

    assert summary['total_length'] > 0.0
    assert 0.0 <= summary['brightness_s_at_detector'] <= 1.0 + 1e-9
    assert 0.0 <= summary['brightness_p_at_detector'] <= 1.0 + 1e-9
    assert 0.0 <= summary['degree_of_polarization_at_detector'] <= 1.0 + 1e-9
    assert summary['polarization_ratio_at_detector'] >= 0.0
    assert isinstance(summary['adaptive_sampling_warning'], str) and summary['adaptive_sampling_warning']

    # A path_dict with no connection edge (a single detached node) -> ValueError.
    lone_uuid = paths[0]['path_uuids'][0]
    try:
        path_physical_summary({'path_uuids': [lone_uuid]}, result)
        raise AssertionError("expected ValueError for a path with no connection edge")
    except ValueError:
        pass

    print(f"  PASS: total_length={summary['total_length']:.2f}, "
          f"dop={summary['degree_of_polarization_at_detector']:.3f}, "
          f"pol_ratio={summary['polarization_ratio_at_detector']:.3f}")
    return True


def test_diff_signature_spectra():
    """diff_signature_spectra distinguishes two structurally different runs
    (n=1.5 vs n=1.8 changes the TIR-bounce topology per rationale doc §7.1)."""
    from ray_tracing_shapely.analysis.signature_analysis import (
        signature_spectrum, diff_signature_spectra,
        signature_spectrum_to_records, signature_spectrum_from_records,
    )

    _, _, result_a = _build_and_run_dtirc_bidirectional(n_prism=1.5)
    _, _, result_b = _build_and_run_dtirc_bidirectional(n_prism=1.8)

    spec_a = signature_spectrum(result_a, top_n=50)
    spec_b = signature_spectrum(result_b, top_n=50)
    assert spec_a and spec_b, "expected non-empty spectra for both runs"

    diff = diff_signature_spectra(spec_a, spec_b)
    assert diff, "expected a non-empty diff"
    assert any(v['only_in'] is not None for v in diff.values()) or any(
        abs(v['energy_a'] - v['energy_b']) > 1e-9 for v in diff.values()
    ), "expected some real difference between n=1.5 and n=1.8 spectra"

    # Records round-trip: tuple keys -> JSON-safe records -> back to tuple keys.
    records = signature_spectrum_to_records(spec_a)
    json.dumps(records)  # must not raise -- this is the JSON-serializability contract
    restored = signature_spectrum_from_records(records)
    assert restored == spec_a
    print("  PASS: diff_signature_spectra finds a real n=1.5-vs-n=1.8 difference; records round-trip")
    return True


def test_persist_and_compare_with_bidirectional_result():
    """persist_run_artifacts/compare_runs extended for graph.json/
    signature_spectrum.json/signature_diff, using a real bidirectional pass."""
    from ray_tracing_shapely.analysis.run_registry import persist_run_artifacts, compare_runs

    with tempfile.TemporaryDirectory() as tmp:
        out_dir = Path(tmp)
        for n_prism, run_id in [(1.5, 'n1.5'), (1.8, 'n1.8')]:
            scene, sim, result = _build_and_run_dtirc_bidirectional(n_prism=n_prism)
            sim_result = sim.run_with_result(name=f'dtirc_n{n_prism}')
            run_dir = persist_run_artifacts(
                scene, sim_result,
                out_dir=out_dir, design_id='dtirc_bidir', run_id=run_id,
                physical_params={'n_prism': n_prism, 'theta_deg': 10.0},
                numerical_params={'ray_density': scene.ray_density},
                bidirectional_result=result,
            )
            assert (run_dir / 'graph.json').exists()
            assert (run_dir / 'signature_spectrum.json').exists()

        diff = compare_runs('dtirc_bidir', 'n1.5', 'dtirc_bidir', 'n1.8', out_dir=out_dir)
        assert diff['signature_diff'] is not None, "expected a signature_diff for two bidirectional runs"
        assert len(diff['signature_diff']) > 0
    print("  PASS: persist_run_artifacts/compare_runs extended for graph/signature_spectrum")
    return True


def _make_fake_lineage_and_scene():
    """Hand-built RayLineage + duck-typed scene, decoupled from any real
    Simulator run or prism class -- Phase 2 Step 4's test-first slice
    (15_p6_nonimaging_optics_phase2_plan.md step 4 / mesh_refinement_and_
    convergence.md §9.5). Surface 'surf1' is a straight 4-edge polyline;
    hits on edges 0-1 refract, edges 2-3 tir -- a known transition at
    edge_index=2, arc_position=2.0 (unit-length edges)."""
    from types import SimpleNamespace
    from ray_tracing_shapely.core.ray_lineage import RayLineage

    surface = SimpleNamespace(uuid='surf1', name='surf1', path=[
        {'x': 0.0, 'y': 0.0}, {'x': 1.0, 'y': 0.0}, {'x': 2.0, 'y': 0.0},
        {'x': 3.0, 'y': 0.0}, {'x': 4.0, 'y': 0.0}, {'x': 4.0, 'y': -1.0},
    ])
    scene = SimpleNamespace(objs=[surface])

    lineage = RayLineage()
    counter = [0]

    def _new_uuid():
        counter[0] += 1
        return f'seg{counter[0]}'

    def _add(parent_uuid, interaction_type, hit_surface_uuid=None, hit_point=None, brightness=1.0):
        seg = SimpleNamespace(
            uuid=_new_uuid(), parent_uuid=parent_uuid, interaction_type=interaction_type,
            hit_surface_uuid=hit_surface_uuid, hit_point=hit_point, total_brightness=brightness,
        )
        lineage.register(seg)
        return seg.uuid

    for x_mid, child_type in [(0.5, 'refract'), (1.5, 'refract'), (2.5, 'tir'), (3.5, 'tir')]:
        parent = _add(None, 'source', hit_surface_uuid='surf1', hit_point={'x': x_mid, 'y': 0.0})
        _add(parent, child_type, brightness=1.0)

    return lineage, scene


def test_estimate_role_transition_pure_function():
    """Pure-function unit test: known transition, no tracing/RXIOptic
    involved -- decouples the reduction logic from the fixture's existence
    (15_p7_mesh_refinement_and_convergence.md §9.5)."""
    from ray_tracing_shapely.analysis.signature_analysis import estimate_role_transition

    lineage, scene = _make_fake_lineage_and_scene()
    result = estimate_role_transition([lineage], scene, 'surf1', 'refract', 'tir')
    assert result['edge_index'] == 2, result
    assert result['from_edge_index'] == 1, result
    assert abs(result['arc_position'] - 2.0) < 1e-9, result
    # uncertainty spans both straddling edges (1 and 2), not just the "to" edge:
    # the true crossover could lie anywhere in either, not just the second one.
    assert abs(result['uncertainty'] - 2.0) < 1e-9, result
    print(f"  PASS: found refract->tir transition at edge_index=2, arc_position=2.0 exactly")
    return True


def test_estimate_role_transition_search_range_isolates_one_of_two():
    """When a surface has more than one from_type->to_type transition (e.g.
    RXIOptic's symmetric dome), search_range locks onto the intended one --
    the fix for the exact instability 15_p7_mesh_refinement_and_convergence.md §6
    flagged (edge_index renumbers across refinement levels)."""
    from types import SimpleNamespace
    from ray_tracing_shapely.core.ray_lineage import RayLineage
    from ray_tracing_shapely.analysis.signature_analysis import estimate_role_transition

    surface = SimpleNamespace(uuid='surf1', name='surf1', path=[
        {'x': 0.0, 'y': 0.0}, {'x': 1.0, 'y': 0.0}, {'x': 2.0, 'y': 0.0},
        {'x': 3.0, 'y': 0.0}, {'x': 4.0, 'y': 0.0}, {'x': 5.0, 'y': 0.0},
        {'x': 6.0, 'y': 0.0}, {'x': 6.0, 'y': -1.0},
    ])
    scene = SimpleNamespace(objs=[surface])
    lineage = RayLineage()
    counter = [0]

    def _add(parent_uuid, interaction_type, hit_surface_uuid=None, hit_point=None, brightness=1.0):
        counter[0] += 1
        seg = SimpleNamespace(
            uuid=f'seg{counter[0]}', parent_uuid=parent_uuid, interaction_type=interaction_type,
            hit_surface_uuid=hit_surface_uuid, hit_point=hit_point, total_brightness=brightness,
        )
        lineage.register(seg)
        return seg.uuid

    # Two refract->tir flips: edges 0-1 refract / 2-3 tir (first), and
    # edges 4-... wait: 5 edges total (0..4), reuse a second flip at 3->4? use edges 0,1 refract, 2 tir (flip@2),
    # then edge 3 refract again, edge 4 tir (flip@4, a second, distinct transition).
    for x_mid, child_type in [(0.5, 'refract'), (1.5, 'refract'), (2.5, 'tir'),
                               (3.5, 'refract'), (4.5, 'tir'), (5.5, 'tir')]:
        parent = _add(None, 'source', hit_surface_uuid='surf1', hit_point={'x': x_mid, 'y': 0.0})
        _add(parent, child_type, brightness=1.0)

    # Unconstrained: finds the FIRST (leftmost) transition, at edge_index=2.
    unconstrained = estimate_role_transition([lineage], scene, 'surf1', 'refract', 'tir')
    assert unconstrained['edge_index'] == 2, unconstrained

    # search_range around the SECOND transition (arc_position ~4.0) finds that one instead.
    constrained = estimate_role_transition(
        [lineage], scene, 'surf1', 'refract', 'tir', search_range=(3.0, 5.0),
    )
    assert constrained['edge_index'] == 4, constrained
    print("  PASS: search_range isolates the intended transition among two candidates")
    return True


def test_estimate_role_transition_no_transition_raises():
    """No from_type->to_type transition present -> ValueError, not a silent
    wrong answer."""
    from ray_tracing_shapely.analysis.signature_analysis import estimate_role_transition

    lineage, scene = _make_fake_lineage_and_scene()
    try:
        estimate_role_transition([lineage], scene, 'surf1', 'tir', 'refract')  # wrong order
        raise AssertionError("expected ValueError")
    except ValueError:
        pass
    print("  PASS: raises ValueError when the requested transition isn't present")
    return True


def test_estimate_role_transition_on_real_rxi():
    """Integration test: a real RXIOptic naturally produces a refract->tir
    (and tir->refract, symmetric) transition on s1 -- the parent-hit/
    child-interaction pairing this function relies on, validated end to end."""
    from ray_tracing_shapely.core.scene import Scene
    from ray_tracing_shapely.core.scene_objs.light_source.angle_source import AngleSource
    from ray_tracing_shapely.core.simulator import Simulator
    from ray_tracing_shapely.optical_elements.prisms.rxi import RXIOptic
    from ray_tracing_shapely.analysis.signature_analysis import estimate_role_transition

    scene = Scene()
    scene.ray_density = 20
    rxi = RXIOptic(scene, n=1.5, phi_edge_deg=50.0, size=30.0, depth=45.0, s1_segments=16)
    rxi.name = 'rxi'
    scene.add_object(rxi)

    source = AngleSource(scene)
    source.p1 = {'x': 0, 'y': 40}
    source.p2 = {'x': 0, 'y': 20}
    source.emis_angle = 60.0
    source.symmetric = True
    source.brightness = 1.0
    source.name = 'src'
    scene.add_object(source)

    sim = Simulator(scene, max_rays=8000, record_surface_hits=True)
    sim.run()

    result = estimate_role_transition([sim.lineage], scene, 'rxi', 'refract', 'tir')
    assert 2 <= result['edge_index'] <= 17, result  # within s1's edge range (2..17)
    assert result['uncertainty'] > 0.0
    print(f"  PASS: real RXIOptic transition at edge_index={result['edge_index']}, "
          f"arc_position={result['arc_position']:.2f}, uncertainty={result['uncertainty']:.2f}")
    return True


def run_all_tests():
    tests = [
        ("edge_index present on graph nodes", test_edge_index_present_on_graph_nodes),
        ("path_signature / signature_spectrum", test_path_signature_and_spectrum),
        ("path_surfaces: corrected hop pairing", test_path_surfaces_hop_pairing),
        ("audit_paths: max_hops and allowed_edges flagging", test_audit_paths_flags_max_hops_and_edges),
        ("path_physical_summary: reciprocity + ValueError", test_path_physical_summary_reciprocity),
        ("diff_signature_spectra n=1.5 vs n=1.8", test_diff_signature_spectra),
        ("persist_run_artifacts/compare_runs w/ bidirectional_result", test_persist_and_compare_with_bidirectional_result),
        ("estimate_role_transition: pure function", test_estimate_role_transition_pure_function),
        ("estimate_role_transition: search_range isolates one of two", test_estimate_role_transition_search_range_isolates_one_of_two),
        ("estimate_role_transition: no transition raises", test_estimate_role_transition_no_transition_raises),
        ("estimate_role_transition: real RXIOptic", test_estimate_role_transition_on_real_rxi),
    ]

    passed = 0
    failed = 0
    errors = []

    for name, test_func in tests:
        print(f"\nTEST: {name}")
        try:
            test_func()
            passed += 1
        except Exception as e:
            failed += 1
            errors.append((name, str(e)))
            print(f"  FAILED: {name}")
            print(f"    Error: {e}")

    print("\n" + "=" * 78)
    print(f"SUMMARY: {passed}/{len(tests)} tests passed")
    print("=" * 78)

    if errors:
        print("\nFailed tests:")
        for name, error in errors:
            print(f"  - {name}: {error}")
        return False

    print("\nAll tests passed!")
    return True


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)
