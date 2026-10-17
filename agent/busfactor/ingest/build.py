"""Assemble snapshot.json from git primitives + optional GitHub enrichment.

Everything here is pure assembly: given the same inputs the output is
byte-identical (sorted lists, rounded floats, no "now" timestamps). The
snapshot is the pinned demo dataset; meta.snapshot_sha256 covers the final
form so consumers can verify exactly what they loaded.
"""

from __future__ import annotations

import difflib
import hashlib
import json
import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path

from . import git as gitm
from . import pulls as pullsm
from .weights import know_weight

# ---- thresholds (pinned per snapshot; recorded in meta.thresholds) --------
WINDOW_DAYS = 365
MIN_MODULE_COMMITS = 3
MAX_MODULES = 80
MAX_PEOPLE = 200
KNOWS_THRESHOLD = 0.05
MAX_KNOWS_PER_MODULE = 10
MAX_DOCS = 150
MAX_DECISIONS = 80
MAX_PRS = 400
OWNS_MIN_SHARE = 0.35
TOP_DOC_AUTHORS = 3
MIN_CONTRIB_COMMITS = 2  # a visit is one commit; knowledge starts at two

DECISION_RE = re.compile(
    r"(?i)\b(migrat\w*|switch\w*|replac\w*|introduc\w*|deprecat\w*|adopt\w*"
    r"|redesign\w*|rewrite\w*|rearchitect\w*|architectur\w*|decision|adr)\b"
)
NOREPLY_RE = re.compile(r"^(?:\d+\+)?([^@+]+)@users\.noreply\.github\.com$", re.IGNORECASE)


def _slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", s.strip().lower()).strip("-")


def _handle_from_email(email: str) -> str | None:
    m = NOREPLY_RE.match(email.strip())
    return m.group(1).lower() if m else None


def _iso_to_dt(s: str) -> datetime:
    return datetime.fromisoformat(s).astimezone(UTC)


def _min_iso(a: str, b: str) -> str:
    if not a:
        return b
    if not b:
        return a
    return a if _iso_to_dt(a) <= _iso_to_dt(b) else b


def _max_iso(a: str, b: str) -> str:
    if not a:
        return b
    if not b:
        return a
    return a if _iso_to_dt(a) >= _iso_to_dt(b) else b


@dataclass
class PersonAcc:
    id: str
    names: Counter = field(default_factory=Counter)
    handle: str | None = None
    commits: int = 0
    prs: int = 0
    reviews: int = 0
    first_seen: str = ""
    last_seen: str = ""
    github_only: bool = False

    @property
    def name(self) -> str:
        if self.names:
            return self.names.most_common(1)[0][0]
        return self.handle or self.id.removeprefix("p:")

    @property
    def activity(self) -> int:
        return self.commits * 2 + self.reviews * 3 + self.prs


def _merge_github_people(people: dict[str, PersonAcc], log=print) -> dict[str, str]:
    """Fold GitHub-only identities (PR authors/reviewers) into commit people.

    Heuristic: normalized handle vs normalized display name similarity, plus a
    prefix match (so "barakb" lands on "Barak Bar Orion"). A clear winner is
    required — ambiguous matches are left alone rather than guessed.
    """
    remap: dict[str, str] = {}
    gh_only = [a for a in people.values() if a.github_only and a.handle]
    commit_people = [a for a in people.values() if not a.github_only and a.commits > 0]
    for gacc in gh_only:
        h = re.sub(r"[^a-z]", "", gacc.handle.lower())
        if not h:
            continue
        scored: list[tuple[float, PersonAcc]] = []
        for acc in commit_people:
            n = re.sub(r"[^a-z]", "", acc.name.lower())
            ratio = max(
                difflib.SequenceMatcher(None, h, n).ratio(),
                difflib.SequenceMatcher(None, h, n[: len(h)]).ratio(),
            )
            scored.append((ratio, acc))
        scored.sort(key=lambda t: (-t[0], t[1].id))
        if not scored:
            continue
        best_r, best = scored[0]
        second_r = scored[1][0] if len(scored) > 1 else 0.0
        if best_r >= 0.82 and (best_r - second_r) >= 0.08:
            best.names.update(gacc.names)
            best.prs += gacc.prs
            best.reviews += gacc.reviews
            best.first_seen = _min_iso(best.first_seen, gacc.first_seen)
            best.last_seen = _max_iso(best.last_seen, gacc.last_seen)
            if best.handle is None:
                best.handle = gacc.handle
            remap[gacc.id] = best.id
            del people[gacc.id]
            log(f"  merged @{gacc.handle} -> {best.name} ({best_r:.2f})")
    return remap


def build_snapshot(
    repo: Path,
    out_path: Path,
    *,
    window_days: int = WINDOW_DAYS,
    cache_dir: Path | None = None,
    token: str | None = None,
    log=print,
) -> dict:
    repo = Path(repo).resolve()
    out_path = Path(out_path)
    cache_dir = Path(cache_dir) if cache_dir else out_path.parent / "raw"

    owner, name = gitm.owner_repo(repo)
    head, head_dt = gitm.head_info(repo)
    since_dt = head_dt - timedelta(days=window_days)
    since_iso = since_dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    log(f"snapshot: {owner}/{name} @ {head[:10]} since {since_iso}")

    # ---- commits -----------------------------------------------------------
    commits = [
        c for c in gitm.read_commits(repo, since_iso) if not gitm.BOT_RE.search(c.author_name)
    ]
    for c in commits:
        c.modules = sorted({m for f in c.files if (m := gitm.module_of(f))})
        m = gitm.PR_IN_SUBJECT.search(c.subject)
        if m:
            c.pr = int(m.group(1))
    log(f"  commits: {len(commits)}")

    # ---- people from commits ----------------------------------------------
    people: dict[str, PersonAcc] = {}
    email_to_pid: dict[str, str] = {}

    name_to_handle: dict[str, str] = {}
    for c in commits:
        h = _handle_from_email(c.author_email)
        if h:
            name_to_handle.setdefault(c.author_name.strip().casefold(), h)

    for c in commits:
        pid = email_to_pid.get(c.author_email)
        if pid is None:
            handle = _handle_from_email(c.author_email) or name_to_handle.get(
                c.author_name.strip().casefold()
            )
            pid = "p:" + _slug(handle or c.author_email.split("@")[0])
            email_to_pid[c.author_email] = pid
        acc = people.get(pid)
        if acc is None:
            acc = PersonAcc(id=pid)
            people[pid] = acc
        acc.names[c.author_name.strip()] += 1
        if acc.handle is None:
            acc.handle = _handle_from_email(c.author_email)
        acc.commits += 1
        acc.first_seen = _min_iso(acc.first_seen, c.date)
        acc.last_seen = _max_iso(acc.last_seen, c.date)
    log(f"  people from commits: {len(people)}")

    # ---- per-module commit stats ------------------------------------------
    mod_commits: Counter[str] = Counter()
    mod_first: dict[str, str] = {}
    mod_last: dict[str, str] = {}
    person_mod: dict[tuple[str, str], dict] = {}
    for c in commits:
        pid = email_to_pid[c.author_email]
        for m in c.modules:
            mod_commits[m] += 1
            mod_first[m] = _min_iso(mod_first.get(m, ""), c.date)
            mod_last[m] = _max_iso(mod_last.get(m, ""), c.date)
            st = person_mod.setdefault((pid, m), {"commits": 0, "reviews": 0, "last": ""})
            st["commits"] += 1
            st["last"] = _max_iso(st["last"], c.date)

    seen_modules = len(mod_commits)
    kept_modules = [
        m
        for m, n in sorted(mod_commits.items(), key=lambda kv: (-kv[1], kv[0]))
        if n >= MIN_MODULE_COMMITS
    ][:MAX_MODULES]
    kept = set(kept_modules)
    log(f"  modules: {len(kept)} kept / {seen_modules} seen")

    # ---- GitHub enrichment (optional) --------------------------------------
    pulls = pullsm.fetch_merged_pulls(owner, name, since_iso, cache_dir, token)
    log(
        f"  merged PRs in window: {len(pulls)}"
        + ("" if token else " (tokenless: titles/authors only)")
    )

    pr_modules: dict[int, set[str]] = defaultdict(set)
    for c in commits:
        if c.pr:
            pr_modules[c.pr] |= set(c.modules)

    reviews: dict[int, list[dict]] = {}
    if token and pulls:
        for pr in pulls:
            rvs = pullsm.fetch_reviews(owner, name, pr["number"], cache_dir, token)
            if rvs:
                reviews[pr["number"]] = rvs
    reviews_available = bool(reviews)
    log(f"  reviews: {'available' if reviews_available else 'unavailable'}")

    # ---- login-level aggregates -------------------------------------------
    def ensure_login(login: str) -> PersonAcc:
        pid = "p:" + _slug(login)
        acc = people.get(pid)
        if acc is None:
            acc = PersonAcc(id=pid, handle=login, github_only=True)
            people[pid] = acc
        if acc.handle is None:
            acc.handle = login
        return acc

    login_reviews_mod: Counter[tuple[str, str]] = Counter()
    login_review_last: dict[str, str] = {}
    mod_review_totals: Counter[str] = Counter()
    for number, rvs in reviews.items():
        for m in pr_modules.get(number, ()):
            for rv in rvs:
                if gitm.BOT_RE.search(rv["login"]):
                    continue
                login_reviews_mod[(rv["login"], m)] += 1
                login_review_last[rv["login"]] = _max_iso(login_review_last.get(rv["login"], ""), rv["at"])
                mod_review_totals[m] += 1

    for pr in pulls:
        login = pr["author_login"]
        if not login or gitm.BOT_RE.search(login):
            continue
        acc = ensure_login(login)
        acc.prs += 1
        acc.first_seen = _min_iso(acc.first_seen, pr["merged_at"])
        acc.last_seen = _max_iso(acc.last_seen, pr["merged_at"])
    for (login, _m), n in login_reviews_mod.items():
        acc = ensure_login(login)
        acc.reviews += n
        acc.last_seen = _max_iso(acc.last_seen, login_review_last.get(login, ""))

    # ---- merge GitHub-only identities into commit people -------------------
    remap = _merge_github_people(people, log)
    log(f"  people after merge: {len(people)}")

    def R(pid: str) -> str:
        return remap.get(pid, pid)

    # ---- merged contribution table for weights ----------------------------
    contrib: dict[tuple[str, str], dict] = defaultdict(
        lambda: {"commits": 0, "reviews": 0, "last": ""}
    )
    for (pid, m), st in person_mod.items():
        c = contrib[(pid, m)]
        c["commits"] += st["commits"]
        c["last"] = _max_iso(c["last"], st["last"])
    if reviews_available:
        for (login, m), n in login_reviews_mod.items():
            pid = R("p:" + _slug(login))
            c = contrib[(pid, m)]
            c["reviews"] += n
            c["last"] = _max_iso(c["last"], login_review_last.get(login, ""))

    # ---- KNOWS edges -------------------------------------------------------
    knows: list[dict] = []
    for (pid, m), c in contrib.items():
        if m not in kept or pid not in people:
            continue
        if c["commits"] < MIN_CONTRIB_COMMITS and c["reviews"] < 1:
            continue
        commit_share = c["commits"] / mod_commits[m]
        review_share = None
        if reviews_available:
            total = mod_review_totals.get(m, 0)
            review_share = (c["reviews"] / total) if total else 0.0
        last = c["last"] or people[pid].last_seen
        days = max((head_dt - _iso_to_dt(last)).total_seconds() / 86400, 0.0) if last else 365.0
        w = know_weight(commit_share, review_share, days)
        if w >= KNOWS_THRESHOLD:
            knows.append(
                {
                    "person": pid,
                    "module": f"m:{m}",
                    "weight": w,
                    "commits": c["commits"],
                    "reviews": c["reviews"],
                    "last_at": last or "",
                    "source": "traced",
                }
            )
    by_mod: dict[str, list[dict]] = defaultdict(list)
    for e in knows:
        by_mod[e["module"]].append(e)
    knows = []
    for _m, edges in sorted(by_mod.items()):
        edges.sort(key=lambda e: (-e["weight"], e["person"]))
        knows.extend(edges[:MAX_KNOWS_PER_MODULE])
    knows.sort(key=lambda e: (e["module"], -e["weight"], e["person"]))
    log(f"  knows edges: {len(knows)}")

    # ---- OWNS edges --------------------------------------------------------
    rules = gitm.parse_codeowners(repo)
    owns: list[dict] = []
    top_by_module: dict[str, dict] = {}
    for e in knows:
        cur = top_by_module.get(e["module"])
        if cur is None or (e["weight"], e["person"]) > (cur["weight"], cur["person"]):
            top_by_module[e["module"]] = e
    for m in sorted(kept):
        pids = ["p:" + _slug(u) for u in gitm.codeowners_match(rules, m)]
        pids = [p for p in pids if p in people]
        if pids:
            for p in pids:
                owns.append({"person": p, "module": f"m:{m}", "source": "codeowners", "share": None})
        else:
            top = top_by_module.get(f"m:{m}")
            if top and top["weight"] >= OWNS_MIN_SHARE:
                share = round(top["commits"] / mod_commits[m], 4)
                owns.append(
                    {"person": top["person"], "module": f"m:{m}", "source": "top-contributor", "share": share}
                )
    log(f"  owns edges: {len(owns)}")

    # ---- decisions ---------------------------------------------------------
    dec_rows: list[dict] = []
    decided_by: list[dict] = []
    affects: list[dict] = []
    seen_titles: set[str] = set()

    def add_decision(
        did: str, title: str, decided_at: str, source: str, source_ref: str,
        decider_pids: list[str], module_ids: list[str],
    ) -> None:
        dec_rows.append(
            {
                "id": did, "title": title, "status": "merged", "decided_at": decided_at,
                "source": source, "source_ref": source_ref,
            }
        )
        for p in sorted(set(decider_pids)):
            decided_by.append({"decision": did, "person": p})
        for m in sorted(set(module_ids)):
            affects.append({"decision": did, "module": m})

    for pr in pulls:  # ascending by merged_at
        title = pr["title"]
        if not DECISION_RE.search(title):
            continue
        norm = _slug(title)[:100]
        if not norm or norm in seen_titles:
            continue
        seen_titles.add(norm)
        deciders: list[str] = []
        if pr["author_login"]:
            pid = R("p:" + _slug(pr["author_login"]))
            if pid in people:
                deciders.append(pid)
        for rv in reviews.get(pr["number"], []):
            pid = R("p:" + _slug(rv["login"]))
            if pid in people:
                deciders.append(pid)
        mods = [f"m:{m}" for m in sorted(pr_modules.get(pr["number"], ())) if m in kept]
        add_decision(
            f"dec:pr-{pr['number']}", title[:140], pr["merged_at"], "pull-request",
            f"PR #{pr['number']}", deciders, mods,
        )
    if not pulls:  # tokenless/offline fallback: mine commit subjects
        for c in commits:
            if not DECISION_RE.search(c.subject):
                continue
            norm = _slug(c.subject)[:100]
            if not norm or norm in seen_titles:
                continue
            seen_titles.add(norm)
            add_decision(
                f"dec:{c.sha[:10]}", c.subject[:140], c.date, "commit", c.sha[:10],
                [email_to_pid[c.author_email]], [f"m:{m}" for m in c.modules if m in kept],
            )
    dec_rows.sort(key=lambda d: (d["decided_at"], d["id"]), reverse=True)
    dec_rows = dec_rows[:MAX_DECISIONS]
    keep_dec = {d["id"] for d in dec_rows}
    decided_by = [e for e in decided_by if e["decision"] in keep_dec]
    affects = [e for e in affects if e["decision"] in keep_dec]
    log(f"  decisions: {len(dec_rows)}")

    # ---- docs --------------------------------------------------------------
    files = gitm.tracked_files(repo)
    doc_paths = [
        f
        for f in files
        if f.lower().endswith((".md", ".mdx", ".rst"))
        and not f.startswith((".github/", "node_modules/"))
    ]

    def doc_priority(p: str) -> tuple[int, str]:
        pl = p.lower()
        if pl.startswith("docs/"):
            return (0, p)
        if "/" not in p:
            return (1, p)
        return (2, p)

    doc_paths.sort(key=doc_priority)
    doc_paths = doc_paths[:MAX_DOCS]

    file_authors: dict[str, Counter] = defaultdict(Counter)
    for c in commits:
        pid = email_to_pid[c.author_email]
        for f in c.files:
            file_authors[f][pid] += 1

    docs: list[dict] = []
    wrote: list[dict] = []
    for p in doc_paths:
        title = gitm.doc_title(repo, p)
        pl = p.lower()
        if re.search(r"adr|decision", pl):
            kind = "adr"
        elif re.search(r"design|architect|rfc|spec", pl):
            kind = "design"
        elif pl.endswith("readme.md"):
            kind = "readme"
        else:
            kind = "guide"
        authors = [pid for pid, _ in file_authors[p].most_common(TOP_DOC_AUTHORS)]
        docs.append({"id": f"d:{p}", "path": p, "title": title, "kind": kind, "authors": authors})
        for pid in authors:
            wrote.append({"person": pid, "doc": f"d:{p}"})
    log(f"  docs: {len(docs)}")

    # ---- PR nodes + edges --------------------------------------------------
    decision_prs = {
        int(d["source_ref"].split("#")[1])
        for d in dec_rows
        if d["source"] == "pull-request" and "#" in d["source_ref"]
    }
    prs: list[dict] = []
    touches: list[dict] = []
    authored: list[dict] = []
    for pr in pulls:
        n = pr["number"]
        mods = sorted(m for m in pr_modules.get(n, ()) if m in kept)
        if not mods and n not in decision_prs:
            continue
        prs.append(
            {
                "id": f"pr:{n}", "number": n, "title": pr["title"][:140],
                "merged_at": pr["merged_at"], "author_login": pr["author_login"], "url": pr["url"],
            }
        )
        for m in mods:
            touches.append({"pr": f"pr:{n}", "module": f"m:{m}"})
        if pr["author_login"]:
            pid = R("p:" + _slug(pr["author_login"]))
            if pid in people:
                authored.append({"person": pid, "pr": f"pr:{n}"})
    prs.sort(key=lambda p: (p["merged_at"], p["number"]))
    if len(prs) > MAX_PRS:
        prs = prs[-MAX_PRS:]
        keep_ids = {p["id"] for p in prs}
        touches = [t for t in touches if t["pr"] in keep_ids]
        authored = [a for a in authored if a["pr"] in keep_ids]

    reviewed: list[dict] = []
    keep_ids = {p["id"] for p in prs}
    for n, rvs in sorted(reviews.items()):
        if f"pr:{n}" not in keep_ids:
            continue
        per = Counter(rv["login"] for rv in rvs)
        for login, cnt in sorted(per.items()):
            pid = R("p:" + _slug(login))
            if pid in people:
                last = max(rv["at"] for rv in rvs if rv["login"] == login)
                reviewed.append({"person": pid, "pr": f"pr:{n}", "reviews": cnt, "last_at": last})
    reviewed.sort(key=lambda e: (e["pr"], e["person"]))
    log(f"  prs: {len(prs)} · touches {len(touches)} · authored {len(authored)} · reviewed {len(reviewed)}")

    # ---- final people filter ----------------------------------------------
    keep_pids: set[str] = {e["person"] for e in knows}
    keep_pids |= {e["person"] for e in owns}
    keep_pids |= {e["person"] for e in decided_by}
    keep_pids |= {w["person"] for w in wrote}
    keep_pids |= {a["person"] for a in authored}
    keep_pids |= {r["person"] for r in reviewed}
    keep_pids = {p for p in keep_pids if p in people}
    ranked = sorted(keep_pids, key=lambda p: (-people[p].activity, p))[:MAX_PEOPLE]
    keep = set(ranked)

    knows = [e for e in knows if e["person"] in keep]
    owns = [e for e in owns if e["person"] in keep]
    decided_by = [e for e in decided_by if e["person"] in keep]
    dec_ids = {e["decision"] for e in decided_by}
    dec_rows = [d for d in dec_rows if d["id"] in dec_ids]
    affects = [e for e in affects if e["decision"] in dec_ids]
    wrote = [w for w in wrote if w["person"] in keep]
    authored = [a for a in authored if a["person"] in keep]
    reviewed = [r for r in reviewed if r["person"] in keep]

    people_rows = [
        {
            "id": people[pid].id,
            "name": people[pid].name,
            "handle": people[pid].handle or "",
            "status": "active",
            "first_seen": people[pid].first_seen,
            "last_seen": people[pid].last_seen,
            "commits": people[pid].commits,
            "reviews": people[pid].reviews,
            "prs": people[pid].prs,
        }
        for pid in sorted(keep)
    ]

    module_rows = [
        {
            "id": f"m:{m}",
            "name": m,
            "path": m,
            "commits_window": mod_commits[m],
            "first_seen": mod_first.get(m, ""),
            "last_seen": mod_last.get(m, ""),
            "criticality": None,
        }
        for m in sorted(kept)
    ]

    # ---- assemble + hash ---------------------------------------------------
    body = {
        "meta": {
            "repo_url": f"https://github.com/{owner}/{name}",
            "head_commit": head,
            "window_days": window_days,
            "since": since_iso,
            "generator": "busfactor.ingest",
            "formula": "0.50*commit_share + 0.30*review_share + 0.20*recency",
            "reviews_available": reviews_available,
            "pulls_available": bool(pulls),
            "thresholds": {
                "min_module_commits": MIN_MODULE_COMMITS,
                "max_modules": MAX_MODULES,
                "max_people": MAX_PEOPLE,
                "knows_threshold": KNOWS_THRESHOLD,
                "min_contrib_commits": MIN_CONTRIB_COMMITS,
                "max_knows_per_module": MAX_KNOWS_PER_MODULE,
                "max_docs": MAX_DOCS,
                "max_decisions": MAX_DECISIONS,
                "max_prs": MAX_PRS,
                "module_depth": gitm.MODULE_DEPTH,
            },
        },
        "people": people_rows,
        "modules": module_rows,
        "docs": docs,
        "decisions": dec_rows,
        "prs": prs,
        "knows": knows,
        "owns": owns,
        "authored": authored,
        "reviewed": reviewed,
        "touches": touches,
        "wrote": wrote,
        "decided_by": decided_by,
        "affects": affects,
    }
    canon = json.dumps(body, sort_keys=True, separators=(",", ":"))
    body["meta"]["snapshot_sha256"] = hashlib.sha256(canon.encode()).hexdigest()

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(body, sort_keys=True, indent=1) + "\n")

    log(f"  snapshot -> {out_path}")
    log(
        f"  nodes: people {len(people_rows)} · modules {len(module_rows)} · docs {len(docs)}"
        f" · decisions {len(dec_rows)} · prs {len(prs)}"
    )
    log(
        f"  edges: knows {len(knows)} · owns {len(owns)} · authored {len(authored)}"
        f" · reviewed {len(reviewed)} · touches {len(touches)} · wrote {len(wrote)}"
        f" · decided_by {len(decided_by)} · affects {len(affects)}"
    )
    log(f"  sha256: {body['meta']['snapshot_sha256']}")
    return body
