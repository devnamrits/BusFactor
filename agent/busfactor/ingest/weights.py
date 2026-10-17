"""The KNOWS weight formula — the one number the whole map hangs on.

    weight = 0.50 * commit_share + 0.30 * review_share + 0.20 * recency

  * commit_share: person's commits on the module / all windowed commits on it.
  * review_share: person's approvals on PRs touching the module / all such
    approvals on it.
  * recency:      0.5 ** (days since the person's last contribution / 180).

When a source is unavailable for a snapshot (no GitHub token => no review
data), the remaining weights are renormalized so the result still lives in
0..1. The snapshot meta records which sources were present, so the formula
is never silently different — it is explicitly parameterized.
"""

from __future__ import annotations

HALF_LIFE_DAYS = 180.0
W_COMMIT, W_REVIEW, W_RECENCY = 0.50, 0.30, 0.20


def know_weight(
    commit_share: float,
    review_share: float | None,
    days_since_last: float,
) -> float:
    """→ weight in 0..1, rounded to 4 decimals (keeps snapshots byte-stable)."""
    recency = 0.5 ** (max(days_since_last, 0.0) / HALF_LIFE_DAYS)
    if review_share is None:
        total = W_COMMIT + W_RECENCY
        weight = (W_COMMIT * commit_share + W_RECENCY * recency) / total
    else:
        weight = W_COMMIT * commit_share + W_REVIEW * review_share + W_RECENCY * recency
    return round(weight, 4)
