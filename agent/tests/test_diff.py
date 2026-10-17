"""Findings are pure data — the whole diff can be exercised without a graph."""

from busfactor.sim.diff import findings

DEP = {"id": "p:roi", "name": "Roi"}


def knower(name):
    return {"id": f"p:{name.lower()}", "name": name}


def snap(modules=None, islands=None, decisions=None, comps=1):
    """modules: {mid: (display_name, [knower names])}"""
    coverage = {
        mid: {"name": name, "commits": 5, "knowers": [knower(n) for n in names]}
        for mid, (name, names) in (modules or {}).items()
    }
    return {
        "coverage": coverage,
        "islands": [{"id": i, "members": members} for i, members in (islands or [])],
        "decisions": decisions or [],
        "active_person_components": comps,
    }


def by_kind(fs):
    out = {}
    for f in fs:
        out.setdefault(f["kind"], []).append(f)
    return out


def test_sole_knower_lost_is_severe_and_world_scoped():
    main = snap({"m:x": ("x", ["Roi"])})
    sim = snap({"m:x": ("x", [])})
    fs = findings(main, sim, "sim:drill-aaaa", DEP)
    sole = by_kind(fs)["sole_knower_lost"][0]
    assert sole["severity"] == 3
    assert "drill-aaaa" in sole["id"]
    assert sole["proof"]["knowers_before"][0]["name"] == "Roi"


def test_zero_knowers_after_from_many_is_blind():
    main = snap({"m:x": ("x", ["Roi", "Dvir"])})
    sim = snap({"m:x": ("x", [])})
    fs = by_kind(findings(main, sim, "sim:drill-a", DEP))
    assert "module_blind" in fs
    assert "sole_knower_lost" not in fs


def test_drop_below_floor_is_thin():
    main = snap({"m:x": ("x", ["Roi", "Dvir", "Guy"])})
    sim = snap({"m:x": ("x", ["Guy"])})  # 3 -> 1, crosses the floor K=2
    fs = by_kind(findings(main, sim, "sim:drill-a", DEP))
    assert fs["coverage_thin"][0]["severity"] == 1


def test_drop_to_floor_is_not_a_finding():
    main = snap({"m:x": ("x", ["Roi", "Dvir", "Guy"])})
    sim = snap({"m:x": ("x", ["Guy", "Dvir"])})  # 3 -> 2, at the floor
    fs = findings(main, sim, "sim:drill-a", DEP)
    assert not [f for f in fs if f["kind"] in ("coverage_thin", "module_blind", "sole_knower_lost")]


def test_island_suppressed_when_already_covered():
    main = snap({"m:x": ("x", ["Roi"])})
    sim = snap({"m:x": ("x", [])}, islands=[(0, ["x"])])
    fs = by_kind(findings(main, sim, "sim:drill-a", DEP))
    assert "sole_knower_lost" in fs
    assert "knowledge_island" not in fs  # same problem, not double-reported


def test_new_island_with_unclaimed_members_is_reported():
    main = snap()
    sim = snap(islands=[(3, ["y", "z"])])
    fs = by_kind(findings(main, sim, "sim:drill-b", DEP))
    island = fs["knowledge_island"][0]
    assert island["proof"]["members"] == ["y", "z"]


def test_orphaned_decision_carries_its_id():
    d = {"id": "dec:1", "title": "use graphblas", "deciders": ["p:roi"], "active": True}
    # the departed person's node stays in the world; only their activity lapses
    d_after = {"id": "dec:1", "title": "use graphblas", "deciders": ["p:roi"], "active": False}
    fs = by_kind(findings(snap(decisions=[d]), snap(decisions=[d_after]), "sim:drill-c", DEP))
    orphan = fs["orphaned_decision"][0]
    assert orphan["proof"]["decision_id"] == "dec:1"
    assert orphan["severity"] == 2


def test_pre_existing_blindness_is_not_attributed_to_the_departure():
    main = snap({"m:z": ("z", [])})
    sim = snap({"m:z": ("z", [])})
    fs = by_kind(findings(main, sim, "sim:drill-d", DEP))
    already = fs["was_already_blind"][0]
    assert already["severity"] == 0
    assert "not caused by" in already["claim"]


def test_bridge_loss_when_people_split():
    fs = by_kind(findings(snap(comps=1), snap(comps=3), "sim:drill-e", DEP))
    bridge = fs["bridge_lost"][0]
    assert bridge["severity"] == 3
    assert bridge["proof"] == {"groups_before": 1, "groups_after": 3}
