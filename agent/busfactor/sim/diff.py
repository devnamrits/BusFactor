"""Turn two metric snapshots into findings — claims with proof and severity.

Findings are pure data; the engine attaches PR evidence and writes them
to main as audit nodes. Pre-existing blindness is always reported as such
and never attributed to the departure (the honesty rule).
"""

from __future__ import annotations

K = 2  # coverage floor: below this a module is at risk

SEVERITY = {
    "sole_knower_lost": 3,
    "module_blind": 3,
    "knowledge_island": 3,
    "bridge_lost": 3,
    "orphaned_decision": 2,
    "coverage_thin": 1,
    "was_already_blind": 0,
}


def _world_slug(world: str) -> str:
    return world.split(":", 1)[1] if ":" in world else world


def _F(
    kind: str,
    severity: int,
    claim: str,
    proof: dict,
    *,
    module_id: str | None = None,
    module_name: str | None = None,
    slug: str | None = None,
    world: str = "",
) -> dict:
    if slug is None:
        slug = (module_id or "global").replace("m:", "").replace("/", "-")
    return {
        "id": f"fnd:{_world_slug(world)}:{kind}:{slug}",
        "kind": kind,
        "severity": severity,
        "claim": claim,
        "module_id": module_id,
        "module_name": module_name,
        "proof": proof,
        "world": world,
    }


def findings(main_snap: dict, sim_snap: dict, world: str, departed: dict) -> list[dict]:
    dep_name = departed["name"]
    out: list[dict] = []
    m_cov, s_cov = main_snap["coverage"], sim_snap["coverage"]

    # ---- module coverage ----------------------------------------------------
    for mid in sorted(m_cov):
        m = m_cov[mid]
        s = s_cov.get(mid) or {"knowers": []}
        k0, k1 = len(m["knowers"]), len(s["knowers"])
        if k0 == 0:
            if k1 == 0:
                out.append(
                    _F(
                        "was_already_blind", 0,
                        f"{m['name']} had no active knower before this drill — "
                        f"pre-existing, not caused by {dep_name}'s departure",
                        {"knowers_before": 0},
                        module_id=mid, module_name=m["name"], world=world,
                    )
                )
            continue
        if k1 == 0 and k0 == 1:
            out.append(
                _F(
                    "sole_knower_lost", 3,
                    f"{m['name']} had exactly one knower ({m['knowers'][0]['name']}); "
                    f"after {dep_name} leaves, none remain",
                    {
                        "knowers_before": m["knowers"],
                        "commits_window": m["commits"],
                    },
                    module_id=mid, module_name=m["name"], world=world,
                )
            )
        elif k1 == 0:
            out.append(
                _F(
                    "module_blind", 3,
                    f"{m['name']} lost all {k0} of its knowers with this departure",
                    {"knowers_before": m["knowers"]},
                    module_id=mid, module_name=m["name"], world=world,
                )
            )
        elif k1 < K <= k0:
            out.append(
                _F(
                    "coverage_thin", 1,
                    f"{m['name']} drops from {k0} knowers to {k1} — below the "
                    f"safety floor of {K}",
                    {
                        "knowers_before": m["knowers"],
                        "knowers_after": s["knowers"],
                    },
                    module_id=mid, module_name=m["name"], world=world,
                )
            )

    # ---- islands (structural) ----------------------------------------------
    # Islands that consist only of modules already claimed by coverage
    # findings are the same problem seen structurally — don't double-report.
    covered_names = {
        f["module_name"]
        for f in out
        if f["kind"] in ("sole_knower_lost", "module_blind", "coverage_thin")
    }
    main_keys = {"|".join(i["members"]) for i in main_snap["islands"]}
    for isl in sim_snap["islands"]:
        key = "|".join(isl["members"])
        if key in main_keys:
            continue
        members = isl["members"]
        if members and all(m in covered_names for m in members):
            continue
        shown = ", ".join(members[:5]) + (" …" if len(members) > 5 else "")
        out.append(
            _F(
                "knowledge_island", 3,
                f"stranded: {len(members)} node(s) with no active owner — {shown}",
                {"members": members},
                slug=str(isl["id"]), world=world,
            )
        )

    # ---- decisions ----------------------------------------------------------
    main_dec = {d["id"]: d for d in main_snap["decisions"]}
    for d in sim_snap["decisions"]:
        before = main_dec.get(d["id"])
        if not d["deciders"] or not before:
            continue
        if not d["active"] and before["active"]:
            out.append(
                _F(
                    "orphaned_decision", 2,
                    f"decision '{d['title']}' lost its last owner — the reasoning "
                    f"lives only in the PR now",
                    {
                        "decision_id": d["id"],
                        "title": d["title"],
                        "deciders_before": before["deciders"],
                    },
                    slug=d["id"].replace(":", "-").replace("/", "-"), world=world,
                )
            )

    # ---- bridges ------------------------------------------------------------
    before_c = main_snap["active_person_components"]
    after_c = sim_snap["active_person_components"]
    if after_c > before_c:
        out.append(
            _F(
                "bridge_lost", 3,
                f"{dep_name} held {after_c - before_c + 1} groups of people together; "
                f"without them the graph splits into {after_c} separate groups",
                {"groups_before": before_c, "groups_after": after_c},
                slug="bridge", world=world,
            )
        )

    out.sort(key=lambda f: (-f["severity"], f["kind"], f.get("module_name") or "", f["claim"]))
    return out
