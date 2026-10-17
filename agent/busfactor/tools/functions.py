"""The eight tools — plain Python over FalkorDB.

Every tool returns the same envelope:

    {"tool", "ok", "outcome", "answer", "data", "citations"}

The console, the HTTP API, the CLI and the MCP server all call these exact
functions, so a question answered in the browser is provably the same code
path as one answered over MCP (invariant I9). `repo` is the graph to read:
`main` for the pinned demo, `repo:<slug>` for anything the user indexed.
"""

from __future__ import annotations

from collections import defaultdict

from .. import db, memory
from ..sim import engine, make_plan, metrics
from ..sim.people import get_person
from . import queries
from .base import K, cite, clean_ref, err, f2, ok, people_hint, resolve_modules


# ---------------------------------------------------------------------------
# 1. who_knows
# ---------------------------------------------------------------------------


def who_knows(ref: str, repo: str = "main") -> dict:
    tool = "who_knows"
    ref = clean_ref(ref)

    mods = resolve_modules(ref, repo)
    if mods:
        m = mods[0]
        rows = queries.run("who_knows", {"module": m["id"]}, world=repo)
        knowers = []
        for pid, pname, w, commits, reviews, last_at, prs in rows:
            prs = [int(n) for n in (prs or []) if n is not None][:3]
            knowers.append({
                "id": pid,
                "name": pname,
                "weight": round(float(w or 0), 4),
                "commits": int(commits or 0),
                "reviews": int(reviews or 0),
                "last_at": last_at or "",
                "prs": prs,
            })
        data = {
            "module": m,
            "coverage": len(knowers),
            "floor": K,
            "knowers": knowers,
            "other_matches": [x["name"] for x in mods[1:4]],
        }
        cites = [cite("module", m["id"], m["name"], f"{len(knowers)} active knower(s)")]
        if not knowers:
            return ok(
                tool, f"Nobody active knows {m['name']} — it is already stranded.",
                data, cites,
            )
        top = knowers[0]
        detail = f"{top['commits']} commits, {top['reviews']} reviews"
        if top["prs"]:
            detail += ", PRs " + ", ".join(f"#{n}" for n in top["prs"])
        cites.append(cite("person", top["id"], top["name"], detail))
        if len(knowers) > 1:
            second = knowers[1]
            tail = f"Next: {second['name']} (weight {f2(second['weight'])})."
        else:
            tail = "There is no second knower."
        answer = (
            f"{m['name']}: {top['name']} knows it best — weight {f2(top['weight'])}, "
            f"{top['commits']} commits, {top['reviews']} reviews. {tail}"
        )
        if len(knowers) == 1:
            answer += f" Coverage 1 — below the safety floor of {K}."
        return ok(tool, answer, data, cites)

    # maybe they asked about a person
    try:
        person = get_person(ref, repo)
    except ValueError:
        return err(
            tool,
            f"I don't know '{ref}' — it is neither a module nor a person in "
            f"this graph. {people_hint(repo)}",
        )
    rows = queries.run("person_modules", {"person": person["id"]}, world=repo)
    mods_x = [
        {
            "id": mid,
            "name": name,
            "weight": round(float(w or 0), 4),
            "commits": int(c or 0),
            "module_commits": int(cw or 0),
        }
        for mid, name, w, c, cw in rows
    ]
    data = {"person": person, "modules": mods_x, "count": len(mods_x)}
    cites = [cite("person", person["id"], person["name"], f"{person['commits']} commits")]
    if mods_x:
        cites += [cite("module", x["id"], x["name"]) for x in mods_x[:5]]
        top_names = ", ".join(f"{x['name']} ({f2(x['weight'])})" for x in mods_x[:5])
        answer = f"{person['name']} carries {len(mods_x)} modules — top: {top_names}."
    else:
        answer = f"{person['name']} has no recorded module knowledge."
    return ok(tool, answer, data, cites)


# ---------------------------------------------------------------------------
# 2. critical_people
# ---------------------------------------------------------------------------


def critical_people(repo: str = "main") -> dict:
    tool = "critical_people"
    rows = queries.run("critical_people", world=repo)
    snap = metrics.snapshot(repo)
    cov = snap["coverage"]

    sole: dict[str, list[tuple[str, str]]] = defaultdict(list)  # pid -> [(mid, name)]
    for mid, info in cov.items():
        if len(info["knowers"]) == 1:
            sole[info["knowers"][0]["id"]].append((mid, info["name"]))

    ranked = []
    for pid, pname, commits, mids, mass in rows:
        mids = [x for x in (mids or []) if x]
        s = sorted(sole.get(pid, []), key=lambda x: x[1])
        ranked.append({
            "id": pid,
            "name": pname,
            "commits": int(commits or 0),
            "modules": len(mids),
            "mass": round(float(mass or 0), 4),
            "sole_modules": [name for _mid, name in s],
            "sole_module_ids": [mid for mid, _name in s],
            "sole_count": len(s),
        })
    ranked.sort(key=lambda r: (-r["sole_count"], -r["mass"], r["name"]))

    total_modules = len(cov)
    top = ranked[0]
    data = {
        "ranked": ranked[:8],
        "modules_total": total_modules,
        "bus_factor": snap["bus_factor"],
        "floor": K,
    }
    cites = [
        cite(
            "person", top["id"], top["name"],
            f"sole knower of {top['sole_count']} module(s), {top['commits']} commits",
        )
    ]
    cites += [
        cite("module", mid, name)
        for mid, name in zip(top["sole_module_ids"][:6], top["sole_modules"][:6])
    ]
    answer = (
        f"{top['name']} is who you can least afford to lose: sole knower of "
        f"{top['sole_count']} of {total_modules} modules "
        f"(e.g. {', '.join(top['sole_modules'][:5])}), carrying "
        f"{f2(top['mass'])} knowledge mass."
    )
    if len(ranked) > 1:
        nxt = ranked[1]
        if nxt["sole_count"]:
            answer += f" Next: {nxt['name']} — sole on {nxt['sole_count']}."
        else:
            answer += f" Next: {nxt['name']} — carries {f2(nxt['mass'])} mass."
    answer += f" Team bus factor today: {snap['bus_factor']}."
    return ok(tool, answer, data, cites)


# ---------------------------------------------------------------------------
# 3. knowledge_islands
# ---------------------------------------------------------------------------


def knowledge_islands(repo: str = "main") -> dict:
    tool = "knowledge_islands"
    snap = metrics.snapshot(repo)
    zero = snap["zero_modules"]
    isl = snap["islands"]
    data = {
        "islands": [{"id": str(i["id"]), "members": i["members"]} for i in isl],
        "zero_modules": zero,
        "zero_module_names": [snap["coverage"][mid]["name"] for mid in zero],
        "modules_total": len(snap["coverage"]),
        "person_components": snap["active_person_components"],
    }
    cites: list[dict] = []
    if not isl and not zero:
        answer = (
            f"Right now: no stranded knowledge — all {len(snap['coverage'])} modules "
            f"are reachable from an active person. That's the healthy state. Run a "
            f"departure drill to see what could break."
        )
    else:
        answer = (
            f"{len(isl)} stranded component(s); {len(zero)} module(s) without any "
            f"active knower: {', '.join(data['zero_module_names'][:5])}."
        )
        cites += [
            cite("module", mid, snap["coverage"][mid]["name"]) for mid in zero[:6]
        ]
    return ok(tool, answer, data, cites)


# ---------------------------------------------------------------------------
# 4. module_risk
# ---------------------------------------------------------------------------


def module_risk(ref: str, repo: str = "main") -> dict:
    tool = "module_risk"
    mods = resolve_modules(ref, repo)
    if not mods:
        return err(tool, f"No module matches '{ref}'. Try e.g. src/udf or graph.")
    m = mods[0]
    rows = queries.run("module_risk", {"module": m["id"]}, world=repo)
    mid, name, path, cw, crit, _knowers = (
        rows[0] if rows else (m["id"], m["name"], m["path"], 0, 0, [])
    )

    krows = queries.run("who_knows", {"module": mid}, world=repo)
    knowers = [
        {
            "id": pid,
            "name": pn,
            "weight": round(float(w or 0), 4),
            "commits": int(c or 0),
            "prs": [int(n) for n in (prs or []) if n is not None][:3],
        }
        for pid, pn, w, c, _r, _la, prs in krows
    ]
    drows = queries.run("module_decisions", {"module": mid}, world=repo)
    decisions = [
        {
            "id": did,
            "title": t,
            "source_ref": sr or "",
            "deciders": [x for x in (dec or []) if x],
        }
        for did, t, sr, dec in drows
    ]

    cov = len(knowers)
    if cov == 0:
        state = "stranded — no active knower"
    elif cov == 1:
        state = f"single point of failure — {knowers[0]['name']} is the only knower"
    elif cov < K:
        state = "thin"
    else:
        state = "healthy"

    data = {
        "module": {"id": mid, "name": name, "path": path or ""},
        "coverage": cov,
        "floor": K,
        "state": state,
        "criticality": round(float(crit or 0), 4),
        "commits_window": int(cw or 0),
        "knowers": knowers,
        "decisions": decisions,
        "decisions_count": len(decisions),
    }
    cites = [cite("module", mid, name, state)]
    cites += [cite("person", k["id"], k["name"], f"weight {f2(k['weight'])}") for k in knowers[:3]]
    cites += [cite("decision", d["id"], d["title"], d["source_ref"]) for d in decisions[:3]]

    answer = f"{name}: {cov} active knower(s) — {state}."
    if decisions:
        answer += (
            f" {len(decisions)} recorded decision(s) touch it "
            f"(latest: “{decisions[0]['title'][:70]}”)."
        )
    return ok(tool, answer, data, cites)


# ---------------------------------------------------------------------------
# 5. simulate_departure
# ---------------------------------------------------------------------------


def simulate_departure(
    person_ref: str, label: str | None = None, repo: str = "main"
) -> dict:
    tool = "simulate_departure"
    try:
        person = get_person(person_ref, repo)
    except ValueError as e:
        return err(tool, f"{e}. {people_hint(repo)}")
    if person["status"] != "active":
        return err(tool, f"{person['name']} is already marked departed.")

    d = engine.run_drill(person["id"], label, repo)
    fs = d["findings"]
    kinds: dict[str, int] = defaultdict(int)
    for f in fs:
        kinds[f["kind"]] += 1
    sole_mods = [f for f in fs if f["kind"] == "sole_knower_lost"]
    thin = [f for f in fs if f["kind"] == "coverage_thin"]
    dec = [f for f in fs if f["kind"] == "orphaned_decision"]

    shown = min(4, len(sole_mods))
    data = {
        "sim_id": d["sim_id"],
        "world": d["world"],
        "person": person,
        "before": d["before"],
        "after": d["after"],
        "seconds": d["seconds"],
        "counts": dict(kinds),
        "sole_modules_shown": shown,
        "sole_more": max(0, len(sole_mods) - shown),
        "findings": fs,
    }
    cites = [cite("sim", d["sim_id"], d["world"], f"{len(fs)} finding(s)")]
    cites += [
        cite("module", f["module_id"], f["module_name"]) for f in sole_mods[:6]
        if f.get("module_id")
    ]
    cites += [
        cite(
            "decision",
            f["proof"].get("decision_id", ""),
            f["proof"].get("title", "decision"),
        )
        for f in dec
        if f["proof"].get("decision_id")
    ]

    if not fs:
        answer = (
            f"If {person['name']} leaves: no knowledge loss detected — every "
            f"module keeps at least {K} active knowers."
        )
    else:
        names = ", ".join(f["module_name"] for f in sole_mods[:shown])
        more = f" and {data['sole_more']} more" if data["sole_more"] else ""
        answer = (
            f"If {person['name']} leaves: {len(sole_mods)} module(s) go dark "
            f"({names}{more}), {len(thin)} drop below the floor of {K}, "
            f"{len(dec)} decision(s) lose their last owner. Stranded components "
            f"{d['before']['islands']} → {d['after']['islands']}. Drill ran in "
            f"{f2(d['seconds'])}s in world {d['world']}."
        )
    return ok(tool, answer, data, cites)


# ---------------------------------------------------------------------------
# 6. handover_plan
# ---------------------------------------------------------------------------


def handover_plan(
    sim_id: str | None = None, include_resilience: bool = True, repo: str = "main"
) -> dict:
    tool = "handover_plan"
    try:
        p = make_plan(sim_id, include_resilience, repo)
    except ValueError as e:
        return err(tool, str(e), outcome="missing_input")
    steps = p["steps"]
    c = p["counts"]
    teachers = sorted({s["teacher_name"] for s in steps})
    first = steps[0] if steps else None

    data = {
        "plan_id": p["plan_id"],
        "sim_id": p["sim_id"],
        "target": p["target"],
        "counts": c,
        "teachers": teachers,
        "steps": steps,
    }
    cites = [cite("plan", p["plan_id"], p["label"], f"{c['steps']} step(s)")]
    cites += [cite("person", p["target"]["id"], p["target"]["name"], "departing")]
    cites += [cite("module", s["module_id"], s["module_name"]) for s in steps[:6]]
    if not steps:
        answer = "No handover steps needed — nothing is at risk."
    else:
        answer = (
            f"Plan {p['plan_id']}: {c['steps']} handover step(s) across "
            f"{len(teachers)} teacher(s) — {c['critical']} critical, {c['thin']} "
            f"thin-coverage, {c['resilience']} standing fragility. First move: "
            f"{first['module_name']} → {first['teacher_name']} ({first['note']})."
        )
    return ok(tool, answer, data, cites)


# ---------------------------------------------------------------------------
# 7. heal_and_verify
# ---------------------------------------------------------------------------


def heal_and_verify(plan_id: str | None = None, repo: str = "main") -> dict:
    tool = "heal_and_verify"
    try:
        h = engine.run_heal(plan_id, repo)
    except ValueError as e:
        return err(tool, str(e), outcome="missing_input")

    res, rem = h["resolved"], h["remaining"]
    remaining_kinds: dict[str, int] = defaultdict(int)
    for f in rem:
        remaining_kinds[f["kind"]] += 1
    before, after = h["before"], h["after"]
    dsum = h.get("drill") or {}
    drill_findings_total = len(res) + len(rem)

    data = {
        "sim_id": h["sim_id"],
        "world": h["world"],
        "plan_id": h["plan_id"],
        "person": h["person"],
        "applied_steps": h["applied_steps"],
        "before": before,
        "drill": dsum,
        "after": after,
        "resolved": len(res),
        "remaining": len(rem),
        "drill_findings_total": drill_findings_total,
        "remaining_kinds": dict(remaining_kinds),
        "remaining_findings": rem,
        "seconds": h["seconds"],
    }
    cites = [
        cite("sim", h["sim_id"], h["world"], "heal world"),
        cite("plan", h["plan_id"], "handover plan", "applied"),
    ]
    answer = (
        f"Healed world {h['world']}: {h['applied_steps']} projected ownership "
        f"edge(s) applied. Stranded components "
        f"{dsum.get('islands', before['islands'])} → {after['islands']}; "
        f"zero-knower modules "
        f"{dsum.get('zero_modules', before['zero_modules'])} → {after['zero_modules']}; "
        f"bus factor {dsum.get('bus_factor', before['bus_factor'])} → "
        f"{after['bus_factor']}. {len(res)} of {drill_findings_total} drill "
        f"findings resolved."
    )
    if rem and set(remaining_kinds) == {"orphaned_decision"}:
        answer += (
            f" The {len(rem)} orphaned decision(s) remain — a projected edge "
            f"re-teaches knowledge, it cannot re-own a human decision."
        )
    elif rem:
        answer += f" {len(rem)} finding(s) still open."
    return ok(tool, answer, data, cites)


# ---------------------------------------------------------------------------
# 8. recall
# ---------------------------------------------------------------------------


def recall(question: str, repo: str = "main") -> dict:
    tool = "recall"
    hits = memory.search(repo, question)
    if not hits:
        return err(
            tool,
            "I can only answer from what is recorded in the graph — nothing "
            "matches that, and I won't guess. I know people, modules, decisions, "
            "and every drill ever run. Try: 'who can we least afford to lose?', "
            "'who knows src/udf?', 'what if Roi Lipman leaves?'.",
            outcome="not_in_graph",
            data={"stats": memory.stats(repo)},
        )

    top = hits[0]
    kind = top["kind"]
    cites: list[dict] = []
    if kind == "question":
        answer = f"From memory — I answered this before ({top['id']}): {top['answer']}"
        cites = [cite("question", top["id"], "earlier question", top.get("snippet", ""))]
    elif kind == "decision":
        deciders = ", ".join(top.get("deciders") or ["(no decider recorded)"])
        answer = (
            f"Decision {top['id']}: “{top['label']}” — recorded from "
            f"{top.get('detail') or 'the graph'}. Deciders: {deciders}."
        )
        cites = [cite("decision", top["id"], top["label"], top.get("detail", ""))]
    elif kind == "finding":
        answer = f"A previous run found: {top['label']}"
        cites = [cite("finding", top["id"], top["label"], top.get("detail", ""))]
    elif kind == "sim":
        answer = f"Run {top['id']}: {top['label']} ({top.get('detail', '')})."
        cites = [cite("sim", top["id"], top["label"], top.get("detail", ""))]
    elif kind == "person":
        answer = (
            f"{top['label']} is in the graph. Ask: 'what if {top['label']} "
            f"leaves?' or 'what does {top['label']} carry?'"
        )
        cites = [cite("person", top["id"], top["label"])]
    elif kind == "module":
        answer = (
            f"{top['label']} is a module in the graph. Ask: 'who knows "
            f"{top['label']}?' or 'risk for {top['label']}'."
        )
        cites = [cite("module", top["id"], top["label"])]
    else:
        answer = top.get("label") or "Found something."

    data = {"hits": hits, "top": top, "stats": memory.stats(repo)}
    return ok(tool, answer, data, cites, outcome="answered_from_memory")
