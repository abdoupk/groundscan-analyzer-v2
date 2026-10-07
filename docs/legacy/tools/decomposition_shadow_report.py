"""Run the S01 decomposition-multiplicity measurement over every available family.

Usage::

    python tools/decomposition_shadow_report.py                  # print the census
    python tools/decomposition_shadow_report.py --json out.json
    python tools/decomposition_shadow_report.py --controlled       # only the six cases
    python tools/decomposition_shadow_report.py --real            # only the real inputs

What it prints, in order:

1. **Controlled cases** -- each of the six constructions over its resolution
   ladder, with the full causal chain (continuous maxima -> sampled maxima ->
   production seed field basins -> anomaly regions -> candidates -> top level)
   and the mechanism assigned to each multiplicity difference.
2. **Draw-to-draw stability** -- the same construction over independent noise
   draws, reduced by the declared tolerances.
3. **Anisotropy** -- the same field and the same ``dx``, only ``dy/dx`` varying.
4. **Real inputs** -- the synthetic catalogue, the frozen vendor OKM scans, the
   seven golden cases and the multiscan site path.
5. **The ``d_res`` input** -- the pooled within-response separation distribution,
   reported as a range with no proposed value.
6. **Public-path reachability** -- what a written report and CSV actually contain
   for a multiplicity instance.

The output is a census, not a verdict. Nothing here changes a decision, writes to
a fixture, or regenerates a baseline, and no proposed ``d_res`` value is ever
printed.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from groundscan.validation import decomposition_reference as ref  # noqa: E402
from groundscan.validation import decomposition_shadow_report as rep  # noqa: E402


def _controlled_scenes() -> list:
    return [builder() for builder in ref.CONTROLLED_CASES]


def print_controlled(pitches) -> list[dict]:
    print("=" * 100)
    print("1. CONTROLLED CASES -- independent oracle vs the public path")
    print("=" * 100)
    payload: list[dict] = []
    for scene in _controlled_scenes():
        print(f"\n--- {scene.name} ({scene.case_family}) ---")
        print(
            f"    construction: {scene.response_count} response(s), "
            f"continuous maxima = {ref.continuous_maxima_count(scene)}"
        )
        obs, verdicts, finding = rep.characterize_case(scene, pitches=pitches)
        header = (
            f"    {'rung':<26}{'pitch':>7}{'contMax':>8}{'sampMax':>8}{'seedBas':>9}"
            f"{'anomReg':>8}{'respReg':>8}{'cand':>6}{'top':>5}{'nested':>7}  patterns"
        )
        print(header)
        for o in obs:
            print(
                f"    {o.label:<26}{o.pitch_m:>7.3f}{o.continuous_maxima:>8}"
                f"{o.sampled_maxima:>8}{o.production_seed_field_basins:>9}"
                f"{o.anomaly_region_count:>8}{o.response_region_count:>8}"
                f"{o.candidate_count:>6}{o.top_level_count:>5}{o.decomposition_count:>7}"
                f"  {list(o.patterns)}"
            )
        print(f"    mechanism: {finding.mechanism}  (benign={finding.is_benign})")
        print(f"    excess records beyond one per response region: {finding.excess_records}")
        if finding.within_response_separations_m:
            print(
                f"    within-response separations (m): "
                f"{[round(s, 3) for s in finding.within_response_separations_m]}"
            )
        for verdict in verdicts:
            unstable = [v for v in verdict.instabilities]
            print(
                f"    draws {verdict.runs:>2} @{verdict.family.split('@')[-1]:<16} "
                f"counts={verdict.metrics['candidate_counts']} "
                f"top={verdict.metrics['top_level_counts']} "
                f"labels={verdict.metrics['distinct_label_sets']} "
                f"maxpos={verdict.metrics['max_position_move_m']}m "
                f"-> {unstable or ['stable']}"
            )
        payload.append({
            "case": scene.name,
            "case_family": scene.case_family,
            "constructed_responses": scene.response_count,
            "observations": [o.to_dict() for o in obs],
            "stability": [v.to_dict() for v in verdicts],
            "finding": finding.to_dict(),
        })
    return payload


def print_anisotropy() -> list[dict]:
    print("\n" + "=" * 100)
    print("3. ANISOTROPY -- same field, same dx=0.5, only dy/dx varying")
    print("=" * 100)
    payload = []
    for scene in _controlled_scenes():
        rows = rep.anisotropy_sweep(scene, dx=0.5)
        if (
            not any(o.decomposition_count for o in rows)
            and len({o.candidate_count for o in rows}) <= 1
        ):
            continue
        print(f"\n--- {scene.name}: continuous maxima = {rows[0].continuous_maxima} ---")
        print(
            f"    {'dy/dx':>7}{'contMax':>9}{'sampMax':>9}{'seedBas':>9}"
            f"{'anomReg':>9}{'cand':>6}{'top':>5}{'nested':>7}  positions"
        )
        for o in rows:
            print(
                f"    {o.dy_ratio:>7.2f}{o.continuous_maxima:>9}{o.sampled_maxima:>9}"
                f"{o.production_seed_field_basins:>9}{o.anomaly_region_count:>9}"
                f"{o.candidate_count:>6}{o.top_level_count:>5}{o.decomposition_count:>7}"
                f"  {[list(p) for p in o.positions_m]}"
            )
        payload.append({"case": scene.name, "rungs": [o.to_dict() for o in rows]})
    if not payload:
        print("    (no aspect-dependent multiplicity in these constructions)")
    return payload


def print_real() -> list[dict]:
    print("\n" + "=" * 100)
    print("4. REAL INPUTS -- synthetic catalogue, vendor OKM, golden cases, site path")
    print("=" * 100)
    censuses = [
        *rep.synthetic_census(),
        *rep.vendor_census(),
        *rep.golden_census(),
        *rep.site_census(),
    ]
    print(f"    {'source':<46}{'cand':>5}{'top':>5}{'nested':>7}  separation_statuses")
    for c in censuses:
        flag = "  <== MULTI-RECORD PARENT" if rep._has_multi_record_parent(c) else ""
        print(
            f"    {c.source:<46}{c.candidate_count:>5}{c.top_level_count:>5}"
            f"{c.decomposition_count:>7}  {list(c.separation_statuses)}{flag}"
        )
    agg = rep.aggregate(censuses)
    print(
        f"\n    inputs={agg['inputs']}  candidates={agg['candidates']}  "
        f"top-level={agg['top_level']}  nested={agg['decomposition']}"
    )
    print(f"    inputs carrying decomposition: {agg['inputs_with_decomposition']}")
    print(
        f"    inputs where ONE parent yielded >1 emitted record: "
        f"{agg['inputs_with_multi_record_parent']}"
    )
    return [c.to_dict() for c in censuses], agg


def print_d_res(agg) -> dict:
    print("\n" + "=" * 100)
    print("5. THE d_res INPUT -- measured within-response separation distribution")
    print("=" * 100)
    dist = agg["separation_distribution"]
    for key in ("count", "min_m", "median_m", "max_m", "distinct_values", "proposed_d_res_m"):
        print(f"    {key:<20} {dist[key]}")
    print(f"    note: {dist['note']}")
    print("\n    the parameter's own declared state:")
    for key, value in rep.d_res_state().items():
        print(f"      {key:<18} {value}")
    print(
        f"    policy available while uncalibrated: {ref.CONSERVATIVE_NEST} "
        f"(promotes = {ref.UNRESOLVED_SEPARATION.promotes})"
    )
    return dist


def print_reachability() -> dict:
    print("\n" + "=" * 100)
    print("6. PUBLIC-PATH REACHABILITY -- what the written machine contract actually contains")
    print("=" * 100)
    reach = rep.public_path_reachability()
    for key in ("artifacts", "candidate_count", "contract_candidate_count", "csv_rows"):
        print(f"    {key:<38} {reach[key]}")
    print(f"    csv separation_statuses  {reach['csv_separation_statuses']}")
    print(f"    csv separation_parent_ids {reach['csv_parent_ids']}")
    print(f"    csv fragment_counts       {reach['csv_fragment_counts']}")
    print(f"    csv response_component_ids{reach['csv_response_component_ids']}")
    return reach


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", type=Path, default=None, help="write the full report as JSON")
    parser.add_argument("--controlled", action="store_true", help="only the controlled cases")
    parser.add_argument("--real", action="store_true", help="only the real inputs")
    parser.add_argument(
        "--pitches",
        type=float,
        nargs="+",
        default=list(ref.RESOLUTION_PITCHES),
        help="resolution ladder in metres (default: 1.0 0.5 0.25 0.125)",
    )
    args = parser.parse_args()

    do_controlled = not args.real
    do_real = not args.controlled
    pitches = tuple(float(p) for p in args.pitches)

    full: dict = {"d_res": rep.d_res_state(), "level_six": ref.LEVEL_SIX_NOTE}
    if do_controlled:
        full["controlled"] = print_controlled(pitches)
        full["anisotropy"] = print_anisotropy()
    if do_real:
        censuses, agg = print_real()
        full["real_inputs"] = censuses
        full["aggregate"] = agg
        full["separation_distribution"] = print_d_res(agg)
        full["public_path"] = print_reachability()

    print("\n" + "=" * 100)
    print(f"level 6: {ref.LEVEL_SIX_NOTE}")
    print("=" * 100)

    if args.json is not None:
        args.json.write_text(json.dumps(full, indent=2, sort_keys=True), encoding="utf-8")
        print(f"\nfull report written to {args.json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
