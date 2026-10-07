"""Dipole-pair resolution for target separation (split from separation.py).

Must be called AFTER (re-)classification. No import from separation.py.
"""

from __future__ import annotations

from ..models import Candidate


def resolve_dipole_pairs(candidates: list[Candidate]) -> list[Candidate]:
    """Relabel negative lobes of bipolar dipoles misclassified as cavities.

    Must be called AFTER (re-)classification, because ``classify_candidate``
    works per-candidate and cannot see that two opposite-polarity fragments
    came from the same fused parent. Fragments sharing a
    ``separation_parent_id`` with opposite polarities and strong peaks on both
    sides form one dipole response: the lobes belong to one signed response,
    not to independently inferred objects.

    The fix keeps both fragments for localization (no data deleted) but:
    - both lobes get a ``dipole-pair`` quality flag and cross-linked notes,
    - lobe hypotheses are preserved; detecting a dipole never upgrades or
      downgrades a lobe into a material-oriented class.
    """
    from collections import defaultdict

    groups: dict[int, list[Candidate]] = defaultdict(list)
    for c in candidates:
        if c.separation_status == "decomposed-consensus" and c.separation_parent_id is not None:
            groups[int(c.separation_parent_id)].append(c)
    for parent_id, group in groups.items():
        if len(group) < 2:
            continue
        polarities = {c.polarity for c in group}
        if "positive" not in polarities or "negative" not in polarities:
            continue
        try:
            max_pos = max(float(c.positive_peak) for c in group if c.polarity == "positive")
            max_neg = max(float(abs(c.negative_peak)) for c in group if c.polarity == "negative")
        except ValueError:
            continue
        if max_pos < 2.0 or max_neg < 2.0:
            continue
        if min(max_pos, max_neg) / max(max_pos, max_neg) < 0.30:
            continue
        pos_ids = sorted(c.id for c in group if c.polarity == "positive")
        neg_ids = sorted(c.id for c in group if c.polarity == "negative")
        for c in group:
            sibling = neg_ids if c.polarity == "positive" else pos_ids
            sibling_txt = ", ".join(f"#{i}" for i in sibling)
            dipole_note = (
                f"bipolar dipole pair with candidate(s) {sibling_txt} "
                f"(same parent {parent_id}); opposite-sign lobes are treated as "
                f"one dipolar response, not as independent objects."
            )
            if dipole_note not in (c.notes or ""):
                c.notes = ((c.notes + "; ") if c.notes else "") + dipole_note
            if "dipole-pair" not in c.quality_flags:
                c.quality_flags = list(c.quality_flags) + ["dipole-pair"]
            # Do not relabel the individual lobes here. A dipole is a response
            # morphology, not evidence of a particular material. The final merged
            # response is represented by ``dipolar-response`` in realworld.py.
    return candidates


__all__ = ["resolve_dipole_pairs"]
