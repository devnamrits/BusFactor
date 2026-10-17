"""Deterministic snapshot extraction from a git clone.

Design rules:
  * No LLM touches ingestion — extraction is regex plus arithmetic (I2).
  * Same clone at the same commit with the same window => byte-identical
    snapshot (I5). Every threshold is a named constant in build.py.

This module holds the git primitives; assembly happens in build.py.
"""

from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

SEP = "\x1f"
REC = "@@@"

# Which trees count as "modules" and which are plumbing.
MODULE_DEPTH = 2
EXCLUDE_PREFIXES = (
    "deps/",
    "docs/",
    "build/",
    "native-deps/",
    "fuzz/",
    "bench/",
    ".github/",
    ".cargo/",
    ".claude/",
    ".devcontainer/",
    ".vscode/",
)

BOT_RE = re.compile(r"(\[bot\]|dependabot|renovate|[-_]bot\b|[-_]robot\b|copilot)", re.IGNORECASE)
PR_IN_SUBJECT = re.compile(r"\(#(\d+)\)\s*$")
MAX_COMMITS = 250_000  # sanity net for accidental mega-repos — env: BUSFACTOR_MAX_COMMITS
MERGE_PR_RE = re.compile(r"^Merge pull request #(\d+)\b")


@dataclass
class Commit:
    sha: str
    author_name: str
    author_email: str
    date: str  # ISO 8601 with offset, straight from git
    subject: str
    files: list[str] = field(default_factory=list)
    modules: list[str] = field(default_factory=list)
    pr: int | None = None

    @property
    def dt(self) -> datetime:
        return datetime.fromisoformat(self.date)


def _git(repo: Path, *args: str) -> str:
    proc = subprocess.run(
        ["git", "-C", str(repo), "-c", "core.quotepath=false", *args],
        capture_output=True,
        text=True,
        check=False,  # failure is handled below with the real stderr message
    )
    if proc.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed in {repo}:\n{proc.stderr.strip()}")
    return proc.stdout


def head_info(repo: Path) -> tuple[str, datetime]:
    """(commit sha, commit date in UTC) of HEAD — the snapshot's anchor."""
    sha = _git(repo, "rev-parse", "HEAD").strip()
    date_s = _git(repo, "show", "-s", "--format=%aI", sha).strip()
    return sha, datetime.fromisoformat(date_s).astimezone(UTC)


def owner_repo(repo: Path) -> tuple[str, str]:
    """Parse owner/name from the origin remote."""
    url = _git(repo, "remote", "get-url", "origin").strip()
    m = re.search(r"github\.com[:/]([^/]+)/([^/.]+)", url)
    if not m:
        raise RuntimeError(f"cannot parse owner/repo from remote: {url}")
    return m.group(1), m.group(2)


def module_of(path: str) -> str | None:
    """Map a file path to its module. Root files and excluded trees → None."""
    if not path:
        return None
    if any(path.startswith(p) for p in EXCLUDE_PREFIXES):
        return None
    parts = path.split("/")
    if len(parts) < 2:
        return None
    if len(parts) >= 3:
        return "/".join(parts[:MODULE_DEPTH])
    return parts[0]


def read_commits(repo: Path, since_iso: str, max_commits: int = MAX_COMMITS) -> list[Commit]:
    """Windowed non-merge commits with the files they touched.

    Preflights the window size, then streams `git log` line-by-line: a
    mega-repo window can emit hundreds of MB, which would otherwise be
    buffered whole and take the API process down with it.
    """
    count = int(
        _git(repo, "rev-list", "--count", "HEAD", "--no-merges", f"--since={since_iso}").strip()
        or 0
    )
    if count > max_commits:
        raise ValueError(
            f"history too large: {count:,} commits in this window (limit "
            f"{max_commits:,}) — narrow the window (e.g. 365 days) or pick a smaller repo"
        )

    fmt = f"{REC}%H{SEP}%an{SEP}%ae{SEP}%aI{SEP}%s"
    proc = subprocess.Popen(
        [
            "git",
            "-C",
            str(repo),
            "-c",
            "core.quotepath=false",
            "log",
            "--no-merges",
            f"--since={since_iso}",
            f"--pretty=format:{fmt}",
            "--name-only",
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    commits: list[Commit] = []
    header: list[str] | None = None

    def flush() -> None:
        nonlocal header
        if header is None:
            return
        sha, name, email, date_s, subject = header[0].split(SEP)
        commits.append(
            Commit(
                sha=sha,
                author_name=name,
                author_email=email,
                date=date_s,
                subject=subject,
                files=header[1:],
            )
        )
        header = None

    for raw in proc.stdout:
        line = raw.rstrip("\r\n")
        if line.startswith(REC):
            flush()
            if len(commits) >= max_commits:  # belt and braces behind the preflight
                proc.kill()
                proc.communicate()
                raise ValueError(
                    f"history too large: more than {max_commits:,} commits — "
                    "narrow the window (e.g. 365 days) or pick a smaller repo"
                )
            header = [line[len(REC):]]
        elif header is not None and line.strip():
            header.append(line.strip())
    flush()
    _, err = proc.communicate()
    if proc.returncode != 0:
        raise RuntimeError(f"git log failed in {repo}:\n{err.strip()}")
    return commits


def merge_pr_map(repo: Path, since_iso: str) -> dict[str, int]:
    """sha -> PR number for merge commits ("Merge pull request #N")."""
    out: dict[str, int] = {}
    raw = _git(repo, "log", "--merges", f"--since={since_iso}", "--pretty=format:%H\x1f%s")
    for line in raw.splitlines():
        if SEP not in line:
            continue
        sha, subject = line.split(SEP, 1)
        m = MERGE_PR_RE.match(subject)
        if m:
            out[sha] = int(m.group(1))
    return out


def tracked_files(repo: Path) -> list[str]:
    return [
        ln.strip()
        for ln in _git(repo, "ls-tree", "-r", "--name-only", "HEAD").splitlines()
        if ln.strip()
    ]


def doc_title(repo: Path, path: str) -> str:
    """First `# heading` of a markdown file; falls back to the file stem."""
    try:
        content = _git(repo, "show", f"HEAD:{path}")
    except RuntimeError:
        return Path(path).stem
    for line in content.splitlines():
        line = line.strip()
        if line.startswith("# "):
            return line[2:].strip()[:120]
    return Path(path).stem


@dataclass
class CodeownersRule:
    pattern: str
    users: list[str]  # individual handles (teams are skipped — they aren't people)


def clone_or_fetch(url: str, dest: Path, log=print) -> Path:
    """Blobless clone, or incremental fetch when the clone already exists.

    Blobless means full commit history without old file contents; `git log
    --name-only` and `git show HEAD:<path>` still work, so a mid-size repo
    indexes in seconds instead of minutes.
    """
    dest.parent.mkdir(parents=True, exist_ok=True)
    if (dest / ".git").exists():
        log(f"  fetching {url}")
        _git(dest, "fetch", "--filter=blob:none", "--quiet", "origin")
        _git(dest, "remote", "set-head", "origin", "-a")
        for ref in ("origin/HEAD", "origin/main", "origin/master"):
            try:
                _git(dest, "reset", "--hard", ref)
                return dest
            except RuntimeError:
                continue
        raise RuntimeError(f"no default branch found in {dest} after fetch")
    log(f"  cloning {url} (blobless, no checkout)")
    proc = subprocess.run(
        ["git", "clone", "--filter=blob:none", "--no-checkout", "--quiet", url, str(dest)],
        capture_output=True,
        text=True,
        check=False,  # failure is handled below with the real stderr message
    )
    if proc.returncode != 0:
        raise RuntimeError(f"git clone failed for {url}:\n{proc.stderr.strip()}")
    return dest


def parse_codeowners(repo: Path) -> list[CodeownersRule]:
    for candidate in ("CODEOWNERS", ".github/CODEOWNERS", "docs/CODEOWNERS"):
        path = repo / candidate
        text = ""
        try:
            text = _git(repo, "show", f"HEAD:{candidate}")
        except RuntimeError:
            text = path.read_text() if path.exists() else ""
        if not text:
            continue
        rules: list[CodeownersRule] = []
        for raw_line in text.splitlines():
            line = raw_line.split("#", 1)[0].strip()
            if not line:
                continue
            tokens = line.split()
            if len(tokens) < 2:
                continue
            users = [
                t[1:].lower()
                for t in tokens[1:]
                if t.startswith("@") and "/" not in t  # skip orgs/teams
            ]
            if users:
                rules.append(CodeownersRule(pattern=tokens[0], users=users))
        if rules:
            return rules
    return []


def codeowners_match(rules: list[CodeownersRule], module: str) -> list[str]:
    """Users whose patterns cover this module (simple prefix + glob matching)."""
    import fnmatch

    out: list[str] = []
    for rule in rules:
        pat = rule.pattern.strip().lstrip("/").rstrip("/")
        hit = False
        if "*" in pat:
            hit = fnmatch.fnmatch(module, pat) or fnmatch.fnmatch(module + "/", pat + "/")
        else:
            hit = module == pat or module.startswith(pat + "/")
        if hit:
            out.extend(u for u in rule.users if u not in out)
    return out
