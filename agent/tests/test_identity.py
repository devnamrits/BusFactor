"""Same-name identity collapse + tolerant person resolution."""

from busfactor.ingest.identity import collapse_same_name_people
from busfactor.sim import people as people_mod


def _body() -> dict:
    return {
        "meta": {},
        "people": [
            {
                "id": "p:joe-gallo",
                "name": "Joe Gallo",
                "handle": "",
                "status": "active",
                "first_seen": "2020-01-01T00:00:00Z",
                "last_seen": "2026-01-01T00:00:00Z",
                "commits": 424,
                "reviews": 10,
                "prs": 5,
            },
            {
                "id": "p:joegallo",
                "name": "Joe Gallo",
                "handle": "joegallo",
                "status": "active",
                "first_seen": "2019-01-01T00:00:00Z",
                "last_seen": "2025-01-01T00:00:00Z",
                "commits": 9,
                "reviews": 1,
                "prs": 0,
            },
            {
                "id": "p:someone",
                "name": "Someone Else",
                "handle": "",
                "status": "active",
                "first_seen": "",
                "last_seen": "",
                "commits": 3,
                "reviews": 0,
                "prs": 0,
            },
        ],
        "knows": [
            {
                "module": "m:x",
                "person": "p:joe-gallo",
                "commits": 5,
                "reviews": 0,
                "weight": 0.4,
                "last_at": "2026-01-01T00:00:00Z",
                "source": "traced",
            },
            {
                "module": "m:x",
                "person": "p:joegallo",
                "commits": 2,
                "reviews": 1,
                "weight": 0.1,
                "last_at": "2025-05-01T00:00:00Z",
                "source": "traced",
            },
            {
                "module": "m:x",
                "person": "p:someone",
                "commits": 3,
                "reviews": 0,
                "weight": 0.05,
                "last_at": "2024-01-01T00:00:00Z",
                "source": "traced",
            },
        ],
        "owns": [
            {"module": "m:y", "person": "p:joegallo", "share": 0.3, "source": "top"},
        ],
        "authored": [{"person": "p:joegallo", "pr": "pr:1"}],
        "wrote": [{"doc": "d:a", "person": "p:joegallo"}],
        "decided_by": [{"decision": "dec:1", "person": "p:joegallo"}],
        "docs": [
            {
                "id": "d:a",
                "authors": ["p:joegallo"],
                "kind": "guide",
                "path": "a",
                "title": "A",
            }
        ],
        "reviewed": [],
        "touches": [],
        "modules": [],
        "decisions": [],
        "prs": [],
        "affects": [],
    }


def test_collapse_same_name() -> None:
    body = _body()
    remap = collapse_same_name_people(body, log=lambda *_: None)
    assert remap == {"p:joegallo": "p:joe-gallo"}
    assert [p["id"] for p in body["people"]] == ["p:joe-gallo", "p:someone"]

    win = body["people"][0]
    assert win["commits"] == 433
    assert win["reviews"] == 11
    assert win["prs"] == 5
    assert win["handle"] == "joegallo"
    assert win["first_seen"] == "2019-01-01T00:00:00Z"
    assert win["last_seen"] == "2026-01-01T00:00:00Z"

    assert len(body["knows"]) == 2
    by_person = {k["person"]: k for k in body["knows"]}
    assert set(by_person) == {"p:joe-gallo", "p:someone"}
    k = by_person["p:joe-gallo"]
    assert k["commits"] == 7 and k["reviews"] == 1
    assert abs(float(k["weight"]) - 0.5) < 1e-9
    assert by_person["p:someone"]["commits"] == 3

    assert body["owns"][0]["person"] == "p:joe-gallo"
    assert body["authored"][0]["person"] == "p:joe-gallo"
    assert body["wrote"][0]["person"] == "p:joe-gallo"
    assert body["decided_by"][0]["person"] == "p:joe-gallo"
    assert body["docs"][0]["authors"] == ["p:joe-gallo"]


def test_person_lookup_prefers_exact_then_busiest(monkeypatch) -> None:
    roster = [
        {
            "id": "p:colleen-mcginnis",
            "name": "Colleen McGinnis",
            "handle": "",
            "status": "active",
            "commits": 14,
            "reviews": 0,
            "last_seen": "",
        },
        {
            "id": "p:colleen-j-mcginnis",
            "name": "Colleen McGinnis",
            "handle": "",
            "status": "active",
            "commits": 2,
            "reviews": 0,
            "last_seen": "",
        },
        {
            "id": "p:nhat",
            "name": "Nhat",
            "handle": "",
            "status": "active",
            "commits": 5,
            "reviews": 0,
            "last_seen": "",
        },
        {
            "id": "p:nhat-nguyen",
            "name": "Nhat Nguyen",
            "handle": "",
            "status": "active",
            "commits": 900,
            "reviews": 0,
            "last_seen": "",
        },
    ]
    monkeypatch.setattr(people_mod, "list_people", lambda repo="main": roster)

    assert people_mod.get_person("Colleen McGinnis")["id"] == "p:colleen-mcginnis"
    assert people_mod.get_person("nhat nguyen")["id"] == "p:nhat-nguyen"
    assert people_mod.get_person("p:nhat")["id"] == "p:nhat"

    try:
        people_mod.get_person("nobody here")
    except ValueError:
        pass
    else:
        raise AssertionError("expected ValueError for unknown person")
