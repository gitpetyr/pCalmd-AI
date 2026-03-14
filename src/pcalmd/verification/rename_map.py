"""Global rename map for cross-chunk name consistency."""

from __future__ import annotations

import re


class GlobalRenameMap:
    """Maintains a consistent mapping of original names to new names.

    Conflict resolution: first-come-first-served.  If a later chunk
    proposes a *new_name* that is already taken (by a different
    *old_name*), the proposal is rejected and the original name is kept.
    """

    def __init__(self) -> None:
        self._map: dict[str, str] = {}  # old_name -> new_name
        self._reverse: dict[str, str] = {}  # new_name -> old_name

    @property
    def mapping(self) -> dict[str, str]:
        """Return a read-only copy of the current mapping."""
        return dict(self._map)

    def propose(self, old_name: str, new_name: str) -> bool:
        """Propose a rename.  Returns True if accepted, False if rejected.

        A proposal is rejected when:
        - *old_name* already has a different mapping
        - *new_name* is already used for a different *old_name*
        """
        if old_name in self._map:
            return self._map[old_name] == new_name

        if new_name in self._reverse:
            return False

        self._map[old_name] = new_name
        self._reverse[new_name] = old_name
        return True

    def merge(self, renames: dict[str, str]) -> dict[str, str]:
        """Merge a batch of renames.  Returns the subset that was accepted."""
        accepted: dict[str, str] = {}
        for old, new in renames.items():
            if self.propose(old, new):
                accepted[old] = new
        return accepted

    def apply_to_source(self, source: str) -> str:
        """Apply all accepted renames to *source* using word-boundary matching."""
        if not self._map:
            return source

        # Sort by length descending so longer names are matched first.
        for old, new in sorted(self._map.items(), key=lambda x: -len(x[0])):
            pattern = r"\b" + re.escape(old) + r"\b"
            source = re.sub(pattern, new, source)
        return source

    def __len__(self) -> int:
        return len(self._map)

    def __contains__(self, old_name: str) -> bool:
        return old_name in self._map

    def get(self, old_name: str) -> str | None:
        """Return the new name for *old_name*, or None."""
        return self._map.get(old_name)
