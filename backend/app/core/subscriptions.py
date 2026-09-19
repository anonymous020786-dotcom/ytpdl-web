"""Channel / playlist subscription diffing — web port of the desktop app's
``ytpdl/core/subscriptions.py``.

Storage moves to Redis (see ``app/store.py``) since this now runs
server-side for potentially many subscriptions rather than one JSON file
next to a single user's settings, so this module keeps only the
storage-agnostic pieces: the record shape and the "what's new" diff. A
subscription's first check always reports zero new videos — with no
``known_ids`` yet, there's nothing to diff against, so it just establishes
the baseline (exactly the desktop app's behaviour, so subscribing to an
existing 500-video channel doesn't auto-queue all 500).
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Subscription:
    id: str
    owner_id: str
    url: str
    title: str = ""
    kind: str = "playlist"
    interval_minutes: int = 60
    last_checked: float = 0.0
    new_count: int = 0
    known_ids: list[str] = field(default_factory=list)


def diff_new_ids(sub: Subscription, current_ids: list[str]) -> list[str]:
    """IDs present now but not in ``sub.known_ids``, preserving source order."""
    if not sub.known_ids:
        return []
    known = set(sub.known_ids)
    return [i for i in current_ids if i and i not in known]
