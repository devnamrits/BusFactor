"""The nine tools — plain Python over FalkorDB.

Every tool returns the same envelope:

    {"tool", "ok", "outcome", "answer", "data", "citations"}

The console, the HTTP API, the CLI and the MCP server all call these exact
functions, so a question answered in the browser is provably the same code
path as one answered over MCP (invariant I9). `repo` is the graph to read:
`main` for the pinned demo, `repo:<slug>` for anything the user indexed.
"""

from __future__ import annotations

import re
from collections import defaultdict

from .. import memory
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
        if top["commits"] == 0 and top["reviews"] == 0:
            # only plan-projected edges lack commit/review evidence by design
            detail = "projected successor (from the heal plan)"
            head = (
                f"{m['name']}: {top['name']} is the projected successor — the "
                f"heal plan assigned them this module (weight {f2(top['weight'])}), "
                f"no commits yet."
            )
        else:
            detail = f"{top['commits']} commits, {top['reviews']} reviews"
            if top["prs"]:
                detail += ", PRs " + ", ".join(f"#{n}" for n in top["prs"])
            head = (
                f"{m['name']}: {top['name']} knows it best — weight {f2(top['weight'])}, "
                f"{top['commits']} commits, {top['reviews']} reviews."
            )
        cites.append(cite("person", top["id"], top["name"], detail))
        if len(knowers) > 1:
            second = knowers[1]
            tail = f"Next: {second['name']} (weight {f2(second['weight'])})."
        else:
            tail = "There is no second knower."
        answer = f"{head} {tail}"
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
    data = {
        "person": person, "modules": mods_x, "count": len(mods_x),
        "docs": [], "docs_count": 0,
    }
    cites = [cite("person", person["id"], person["name"], f"{person['commits']} commits")]
    if mods_x:
        cites += [cite("module", x["id"], x["name"]) for x in mods_x[:5]]
        top_names = ", ".join(f"{x['name']} ({f2(x['weight'])})" for x in mods_x[:5])
        answer = f"{person['name']} carries {len(mods_x)} modules — top: {top_names}."
    else:
        # A person can be on the roster through docs or sub-threshold work
        # (e.g. hundreds of commits under docs/) — say that plainly instead
        # of leaving a bare "no module knowledge" that reads like a bug.
        docs_w = [
            {"id": did, "title": title or did}
            for did, title in queries.run("person_docs", {"person": person["id"]}, world=repo)
        ]
        data["docs"] = docs_w
        data["docs_count"] = len(docs_w)
        answer = f"{person['name']} has no recorded module knowledge."
        if docs_w:
            cites += [cite("doc", d["id"], d["title"]) for d in docs_w[:3]]
            answer += (
                f" What the graph does hold: {len(docs_w)} doc page(s) they wrote"
                f" (e.g. “{docs_w[0]['title']}”). Docs and build trees are plumbing"
                " in this index, not knowledge modules; scattered code touches stay"
                " below the significance floor."
            )
        elif int(person.get("commits") or 0):
            answer += (
                f" {int(person['commits'])} commit(s) are on record, but none"
                " register as module knowledge — docs/build trees are plumbing"
                " in this index, and scattered touches stay below the floor."
            )
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
    if top["sole_count"]:
        top_detail = (
            f"sole knower of {top['sole_count']} module(s), {top['commits']} commits"
        )
        answer = (
            f"{top['name']} is who you can least afford to lose: sole knower of "
            f"{top['sole_count']} of {total_modules} modules "
            f"(e.g. {', '.join(top['sole_modules'][:5])}), carrying "
            f"{f2(top['mass'])} knowledge mass."
        )
    else:
        # a healed world can rank a successor first: they hold the most mass
        # but no module depends on them alone anymore
        top_detail = f"carries the most knowledge mass ({f2(top['mass'])})"
        answer = (
            f"{top['name']} carries the most knowledge mass "
            f"({f2(top['mass'])}) — no module depends on them alone, "
            f"but they remain the heaviest single carrier."
        )
    cites = [cite("person", top["id"], top["name"], top_detail)]
    cites += [
        cite("module", mid, name)
        for mid, name in zip(top["sole_module_ids"][:6], top["sole_modules"][:6])
    ]
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
        try:
            p = get_person(clean_ref(ref), repo)
        except ValueError:
            p = None
        if p:
            return err(
                tool,
                f"'{p['name']}' is a person here, not a module — ask 'what "
                f"does {p['name']} carry?' or 'what if {p['name']} leaves?'.",
            )
        examples = ", ".join(m[1] for m in queries.run("modules_all", world=repo)[:2])
        return err(tool, f"No module matches '{ref}'. Try e.g. {examples}.")
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


_OVERVIEW_RE = re.compile(
    r"(how many|number of|counts? of|overview|summary|what'?s in|what is in|"
    r"what do you know|what can you (?:tell|answer|do)|"
    r"tell me about (?:this|the)\s+(?:repo|graph|team|project)|"
    r"list\s+(?:all\s+|the\s+)?(?:people|persons|team|modules|decisions|"
    r"docs|documentation|prs|pull\s+requests|runs|questions|drills|sims|"
    r"findings))",
    re.IGNORECASE,
)


def _short_title(title: str) -> str:
    s = (title or "").split("[")[0].strip().rstrip("—·").strip()
    return s or (title or "(untitled)")


def _dossier_person(top: dict, hits: list[dict], repo: str, tool: str) -> dict:
    try:
        person = get_person(top["label"], repo)
    except ValueError:
        return err(
            tool,
            f"I don't have a person matching “{top['label']}”. {people_hint(repo)}",
        )
    mods_x = [
        {
            "id": mid, "name": name, "weight": round(float(w or 0), 4),
            "commits": int(c or 0),
        }
        for mid, name, w, c, _mw in queries.run(
            "person_modules", {"person": person["id"]}, world=repo
        )
    ]
    docs_w = [
        {"id": did, "title": _short_title(t or did)}
        for did, t in queries.run("person_docs", {"person": person["id"]}, world=repo)
    ]
    decs = [
        {"id": did, "title": _short_title(t or did)}
        for did, t in queries.run("person_decisions", {"person": person["id"]}, world=repo)
    ]
    data = {
        "hits": hits, "top": top, "stats": memory.stats(repo), "person": person,
        "modules": mods_x, "modules_count": len(mods_x),
        "docs": docs_w, "docs_count": len(docs_w),
        "decisions": decs, "decisions_count": len(decs),
    }
    cites = [cite("person", person["id"], person["name"], f"{person['commits']} commits")]
    cites += [cite("module", m["id"], m["name"]) for m in mods_x[:3]]
    cites += [cite("doc", d["id"], d["title"]) for d in docs_w[:3]]
    cites += [cite("decision", d["id"], d["title"]) for d in decs[:3]]

    bits = [f"{int(person['commits'] or 0)} commits"]
    if mods_x:
        bits.append(
            f"carries {len(mods_x)} module(s) "
            f"(top: {mods_x[0]['name']} {f2(mods_x[0]['weight'])})"
        )
    else:
        bits.append("no recorded module knowledge")
    if docs_w:
        bits.append(f"wrote {len(docs_w)} doc page(s)")
    if decs:
        bits.append(f"decided {len(decs)} recorded decision(s)")
    answer = (
        f"{person['name']} — " + ", ".join(bits) + ". "
        f"Ask: 'what if {person['name']} leaves?' or 'what does "
        f"{person['name']} carry?'."
    )
    return ok(tool, answer, data, cites)


def _dossier_module(top: dict, hits: list[dict], repo: str, tool: str) -> dict:
    mid = top["id"]
    rows = queries.run("module_risk", {"module": mid}, world=repo)
    name = rows[0][1] if rows else top["label"]
    knowers = [x for x in ((rows[0][5] or []) if rows else []) if x]
    decs = [
        {
            "id": did, "title": _short_title(t or did),
            "deciders": [x for x in (dec or []) if x],
        }
        for did, t, _ref, dec in queries.run(
            "module_decisions", {"module": mid}, world=repo
        )
    ]
    data = {
        "hits": hits, "top": top, "stats": memory.stats(repo),
        "knowers": knowers, "knowers_count": len(knowers),
        "decisions": decs, "decisions_count": len(decs),
    }
    cites = [cite("module", mid, name)]
    cites += [cite("decision", d["id"], d["title"]) for d in decs[:3]]
    if knowers:
        head = f"{name} — {len(knowers)} recorded knower(s): {', '.join(knowers[:4])}"
    else:
        head = f"{name} — no active knower right now"
    if decs:
        head += f" · {len(decs)} decision(s) reference it"
    return ok(tool, head + f". Ask: 'who knows {name}?' or 'risk for {name}'.", data, cites)


def _dossier_doc(top: dict, hits: list[dict], repo: str, tool: str) -> dict:
    authors = [
        {"id": pid, "name": name}
        for pid, name in queries.run("doc_authors", {"doc": top["id"]}, world=repo)
    ]
    data = {
        "hits": hits, "top": top, "stats": memory.stats(repo),
        "authors": authors, "authors_count": len(authors),
    }
    title = _short_title(top["label"])
    cites = [cite("doc", top["id"], title, top.get("detail", ""))]
    cites += [cite("person", a["id"], a["name"]) for a in authors[:3]]
    by = f" — written by {', '.join(a['name'] for a in authors)}" if authors else ""
    return ok(tool, f"Doc “{title}”{by}.", data, cites)


def _dossier_pr(top: dict, hits: list[dict], repo: str, tool: str) -> dict:
    rows = queries.run("pr_detail", {"pr": top["id"]}, world=repo)
    num, title, merged, authors, mods = (
        rows[0] if rows else (None, "", "", [], [])
    )
    authors = [x for x in (authors or []) if x]
    mods = [x for x in (mods or []) if x]
    pr = {
        "id": top["id"], "number": num, "title": title or "",
        "merged_at": merged or "", "authors": authors, "modules": mods,
    }
    data = {"hits": hits, "top": top, "stats": memory.stats(repo), "pr": pr}
    cites = [cite("pr", top["id"], f"PR #{num}", title or "")]
    answer = f"PR #{num} “{title or '…'}”"
    if authors:
        answer += f" — authored by {', '.join(authors)}"
    if mods:
        answer += f"; touches {', '.join(mods)}"
    return ok(tool, answer + ".", data, cites)


def _overview(question: str, repo: str, tool: str) -> dict:
    q = (question or "").lower()
    stats = memory.stats(repo)
    bf = metrics.bus_factor(repo)
    crit = critical_people(repo=repo)
    ranked = [r for r in (crit["data"].get("ranked") or []) if r.get("name")]
    top = ranked[0] if ranked else None
    counts = (
        f"{stats['people']} people, {stats['modules']} modules, "
        f"{stats['decisions']} decisions, {stats['docs']} docs, {stats['prs']} PRs"
    )
    data = {"stats": stats, "bus_factor": bf, "top": top}

    if re.search(r"\bmodules?\b", q):
        mods = [
            {"id": mid, "name": n, "commits": int(c or 0)}
            for mid, n, c in queries.run("modules_top", world=repo)
        ]
        data["modules"] = mods
        # cite what the answer names — the map should point at the same things
        cites = [
            cite("module", m["id"], m["name"], f"{m['commits']} commits")
            for m in mods[:4]
        ]
        answer = (
            f"This graph holds {counts}. Biggest modules by commit volume: "
            f"{', '.join(m['name'] for m in mods[:5])}. Bus factor {bf}."
        )
    elif re.search(r"\b(people|persons|team|engineers)\b", q):
        data["people"] = ranked[:6]
        cites = [
            cite("person", r["id"], r["name"], f"mass {f2(r['mass'])}")
            for r in ranked[:4]
        ]
        answer = (
            f"This graph holds {counts}. Most depended-on: "
            f"{', '.join(r['name'] for r in ranked[:5])}. Bus factor {bf}."
        )
    elif re.search(r"decid|decis", q):
        decs = [
            {"id": did, "title": _short_title(t or did)}
            for did, t, *_rest in queries.run("decisions", world=repo)
        ][:6]
        data["decisions"] = decs
        cites = [cite("decision", d["id"], d["title"]) for d in decs[:4]]
        answer = (
            f"This graph holds {counts}. Recent decisions: "
            + "; ".join(d["title"] for d in decs[:3]) + f". Bus factor {bf}."
        )
    else:
        cites = list((crit.get("citations") or [])[:4])
        answer = (
            f"This graph holds {counts} — plus {stats['questions']} remembered "
            f"questions and {stats['runs']} runs. Bus factor {bf}."
        )
        if top:
            if top["sole_count"]:
                answer += (
                    f" Most depended-on: {top['name']} (sole knower of "
                    f"{top['sole_count']} module(s), mass {f2(top['mass'])})."
                )
            else:
                answer += f" Most depended-on: {top['name']} (mass {f2(top['mass'])})."
        answer += " Ask about any person, module, decision, doc or PR by name."

    return ok(tool, answer, data, cites)


def recall(question: str, repo: str = "main") -> dict:
    tool = "recall"
    hits = memory.search(repo, question)
    # "how many / what's in / list …" questions are about the repo itself:
    # answer them from counts even when a stray record token-matched some
    # words — but never when the question names a person or module, because
    # those deserve a dossier instead.
    if _OVERVIEW_RE.search(question or "") and not any(
        h["kind"] in ("person", "module") for h in hits
    ):
        return _overview(question, repo, tool)
    if not hits:
        return err(
            tool,
            "I can only answer from what is recorded in the graph — nothing "
            "matches that, and I won't guess. I know people, modules, decisions, "
            "docs, PRs and every drill ever run — ask about any of them, or ask "
            "'what's in this repo?'. Try: 'who can we least afford to lose?', "
            "'who knows src/udf?', 'what if Roi Lipman leaves?'.",
            outcome="not_in_graph",
            data={"stats": memory.stats(repo)},
        )

    top = hits[0]
    kind = top["kind"]

    # a named entity deserves a live dossier, not a pointer
    if kind == "person":
        return _dossier_person(top, hits, repo, tool)
    if kind == "module":
        return _dossier_module(top, hits, repo, tool)
    if kind == "doc":
        return _dossier_doc(top, hits, repo, tool)
    if kind == "pr":
        return _dossier_pr(top, hits, repo, tool)

    cites: list[dict] = []
    if kind == "question":
        answer = (
            "From memory — I answered this before "
            f"({top['id']}): {memory.canonical_answer(top['answer'])}"
        )
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
    else:
        answer = top.get("label") or "Found something."

    data = {"hits": hits, "top": top, "stats": memory.stats(repo)}
    return ok(tool, answer, data, cites, outcome="answered_from_memory")


# ---------------------------------------------------------------------------
# 9. relations
# ---------------------------------------------------------------------------

_SPLIT_RE = re.compile(
    r"\s*(?:,|;|&|\band\b|\bvs\.?|\bversus\b|\bb/w\b)\s*", re.IGNORECASE
)
_LEAD_RE = re.compile(
    r"^(?:the\s+)?(?:relation(?:ship)?s?|connections?|links?)\s+"
    r"(?:between|among|b/w)\s+",
    re.IGNORECASE,
)


def _person_refs(ref: str) -> list[str]:
    """Split a multi-name reference ("Dvir, Avi and Guy?") into name parts."""
    out = _LEAD_RE.sub("", clean_ref(ref))
    out = re.sub(r"^(?:between|among|b/w)\s+", "", out, flags=re.IGNORECASE)
    return [p for p in (clean_ref(x) for x in _SPLIT_RE.split(out.strip())) if p]


def relations(ref: str, repo: str = "main") -> dict:
    tool = "relations"
    resolved: list[dict] = []
    unknown: list[str] = []
    for name in _person_refs(ref):
        try:
            person = get_person(name, repo)
        except ValueError:
            unknown.append(name)
            continue
        if person["id"] not in {p["id"] for p in resolved}:
            resolved.append(person)
    resolved = resolved[:4]
    if len(resolved) < 2:
        detail = ""
        if resolved:
            detail += " Resolved: " + ", ".join(p["name"] for p in resolved) + "."
        if unknown:
            detail += " No such person: " + ", ".join(unknown) + "."
        return err(
            tool,
            f"I need at least two known people to describe how they relate."
            f"{detail} {people_hint(repo)}",
        )

    pairs: list[dict] = []
    for i, a in enumerate(resolved):
        for b in resolved[i + 1:]:
            mods: dict[str, dict] = {}
            for mid, mname, wa, wb in queries.run(
                "shared_modules", {"a": a["id"], "b": b["id"]}, world=repo
            ):
                joint = round(min(float(wa or 0), float(wb or 0)), 4)
                cur = mods.get(mid)
                if cur is None or joint > cur["joint"]:
                    mods[mid] = {"id": mid, "name": mname, "joint": joint}
            mods_list = sorted(mods.values(), key=lambda m: (-m["joint"], m["name"]))
            prs = [
                {"number": int(n), "title": t or "", "merged_at": at or ""}
                for n, t, at in queries.run(
                    "shared_prs", {"a": a["id"], "b": b["id"]}, world=repo
                )
            ]
            decisions = [
                {"id": did, "title": t or ""}
                for did, t, _at in queries.run(
                    "shared_decisions", {"a": a["id"], "b": b["id"]}, world=repo
                )
            ]
            docs = [
                {"id": did, "title": t or ""}
                for did, t, _path in queries.run(
                    "shared_docs", {"a": a["id"], "b": b["id"]}, world=repo
                )
            ]
            pairs.append(
                {
                    "a": {"id": a["id"], "name": a["name"]},
                    "b": {"id": b["id"], "name": b["name"]},
                    "shared_module_count": len(mods_list),
                    "joint_familiarity": round(sum(m["joint"] for m in mods_list), 4),
                    "top_shared_modules": mods_list[:5],
                    "shared_prs": prs,
                    "pr_count": len(prs),
                    "shared_decisions": decisions,
                    "decision_count": len(decisions),
                    "shared_docs": docs,
                    "doc_count": len(docs),
                }
            )

    def sentence(p: dict) -> str:
        who = f"{p['a']['name']} and {p['b']['name']}"
        if not any(
            (p["shared_module_count"], p["pr_count"], p["decision_count"], p["doc_count"])
        ):
            return f"{who}: no joint record in this graph — their work is disjoint."
        bits = []
        if p["shared_module_count"]:
            top = ", ".join(m["name"] for m in p["top_shared_modules"][:4])
            bits.append(
                f"{p['shared_module_count']} shared module(s), joint familiarity "
                f"{f2(p['joint_familiarity'])} (top: {top})"
            )
        if p["pr_count"]:
            bits.append(f"{p['pr_count']} shared PR(s)")
        if p["decision_count"]:
            bits.append(f"{p['decision_count']} shared decision(s)")
        if p["doc_count"]:
            bits.append(f"{p['doc_count']} shared doc(s)")
        return f"{who}: " + "; ".join(bits) + "."

    strongest = max(
        pairs,
        key=lambda p: (p["shared_module_count"], p["joint_familiarity"], p["pr_count"]),
    )
    answer = " ".join(sentence(p) for p in pairs)
    if strongest["shared_module_count"]:
        answer += (
            f" Closest pair: {strongest['a']['name']} and {strongest['b']['name']} — "
            f"joint familiarity {f2(strongest['joint_familiarity'])}."
        )
    cites = [
        cite("person", p["id"], p["name"], f"{p['commits']} commits") for p in resolved
    ]
    cites += [
        cite("module", m["id"], m["name"], f"joint {f2(m['joint'])}")
        for m in strongest["top_shared_modules"][:3]
    ]
    data = {
        "people": [{"id": p["id"], "name": p["name"]} for p in resolved],
        "unknown": unknown,
        "pairs": pairs,
        "pair_count": len(pairs),
    }
    return ok(tool, answer, data, cites)
