# Implementation Plan

This plan targets a new Swiss pairing package intended to replace current
`py4swiss` usage in `pychess-variants` over time, while using `rustworkx` for
matching.

For the rule-transition notes that now affect interpretation of Aeroflot and
`py4swiss` differences, see [RULEBOOK_DIFF_2026.md](RULEBOOK_DIFF_2026.md).

## Scope Baseline

- Rule sources:
  - C.04.1 Basic rules for Swiss Systems (effective from 1 Feb 2026)
  - C.04.2 General handling rules for Swiss Tournaments (effective from 1 Feb 2026)
  - C.04.3 FIDE Dutch System (effective from 1 Feb 2026)
- Initial target scale: up to ~300 active players.
- Architecture principle: staged optimization aligned with FIDE criterion
  priority ordering.
- Current direction: exact/FIDE mode is the canonical target; synthetic
  baselines are guardrails against accidental regressions, not the main
  success metric.
- Current API direction: `pair_round_dutch()` and `pair_snapshots_dutch()` now
  point at the exact/FIDE solver; the old public two-mode path is gone.

## Milestones

1. Foundation (this repository stage)
- Typed domain model with explicit player pairing state.
- FIDE reference constants and article tagging in code comments.
- Bracket-level matcher based on `rustworkx.max_weight_matching`.
- Initial criteria coverage:
  - C.04.1 rule 2 (no rematch),
  - C.04.1 rule 4 and C.04.3 C2 (full-point bye repeat block),
  - C.04.3 C3 (absolute color conflict for non-topscorers),
  - C.04.3 C5/C6/C7 partial staged objective for byes and downfloaters.
- Extensive unit tests for deterministic behavior and constraints.

2. Dutch bracket completeness
- Full [C5]-[C21] staged objective handling for bracket candidate choice.
- Exact transposition/exchange sequencing per C.04.3 section 4.
- Deterministic candidate generation order per FIDE sequence rules.

3. Tournament-level Dutch process
- Full bracket chain handling with MDPs, remainders, PPB/CLB collapse logic.
- Color allocation implementation E.1-E.5 equivalent.
- TRF import/export adapters and pychess-compatible state adapter.

4. Integration and parity
- Golden tests against `py4swiss` for legacy-rule parity where needed.
- 2026-rule conformance suites driven from frozen tournament fixtures.
- Performance profiling and bounded-time stress tests (200-300 player targets).

## Progress Snapshot (2026-03-11)

- Completed:
  - [C5]-[C21] candidate key implemented in bracket solver.
  - Deterministic candidate tie-break with explicit generation sequence index.
  - Article 4.2/4.3 exact sequence search for small homogeneous brackets
    (bounded by player count), with large-bracket matching fallback.
  - Initial tournament-level round chain (scoregroups + MDP carry-over).
  - Article 3.7-style heterogeneous sequence expansion (MDP set, S2
    transpositions, remainder candidate nesting).
  - Large heterogeneous fixture tests and round-pipeline stress coverage.
  - Golden harness against py4swiss with imported TRF fixtures and
    parity/known-gap test split.
  - Parity closure for D.2 criterion edge-case fixture (`dutch_d2_criterion_d`).
  - Last-bracket unresolved handling now raises `PairingError`, closing
    `no_legal_pairings` parity fixture.
  - TRF `XXP` forbidden-pair constraints mapped into model and legality checks.
  - Collapse-aware tournament round solving added for bracket-chain completion
    and parity on `dutch_e2_both_absolute_higher_favored`.
  - Round-level collapse search now limits [C8] tie-break lookahead to the
    immediate next bracket, recovering sub-80-player benchmark runtime on the
    checked-in recurring `p32` fixture catalog and removing legacy runner
    errors there.
  - Large-event runtime path added to bound collapse-search runtime at higher
    player counts.
  - Typed pychess adapter module added for snapshot conversion and
    user-object pairing mapping.
  - Golden fixture catalog expanded with additional parity fixtures
    (`burstein_late_entries_black`, `dubov_bye_for_high_tpn`, `invalid_code`).
  - Cross-engine benchmark harness added (success-rate + p50/p95 latency)
    for TRF fixture catalogs and pychess-exported TRF state batches.
  - pychess dump-to-TRF batch exporter added for benchmark fixture generation
    from `tournament*.json` production dumps.
  - Seeded synthetic Swiss batch generator added for benchmark input creation
    before production Swiss history is available.
  - Recurring synthetic baseline runner added with run-level JSON reports and
    append-only trend CSV (`benchmarks/run_recurring_baselines.py`).
  - Benchmark summary now records both-ok equality rates separately from
    over-all-case rates, and benchmark runs fail fast when the selected
    interpreter cannot import `py4swiss`.
  - Refreshed checked-in recurring baselines culminating in
    `post-bounded-c8-20260311`, with calibrated SLA presets and per-profile
    pass/fail tracking in recurring baseline outputs.
  - After the exact-only cleanup, a fresh rerun of that older synthetic
    py4swiss-compare sweep was intentionally not adopted as the new baseline:
    it is still useful for spotting runtime blowups, but it is no longer a
    good canonical performance target for the exact solver.
  - Added a dedicated exact runtime corpus benchmark over the checked
    real-world stress set (Aeroflot, Graz, and Budapest Group B) so exact-mode
    performance can be watched on meaningful fixtures instead of only through
    the older synthetic py4swiss sweep.
  - Local `bbpPairings` build now works as a second external oracle, and the
    benchmark harness can run three-way TRF comparisons across
    `swisspairing`, `py4swiss`, and `bbpPairings`.
  - Exact search now uses candidate-budget guards plus tighter odd-bracket
    exact candidate pruning, removing the large recurring `p32` / `p128`
    tail without changing checked py4swiss parity.
  - Recurring synthetic coverage now includes `p512`; the full checked-in
    sweep remains practical there, and the main added cost is synthetic
    export time.
  - Checked-in 64-player regression TRFs added for the slow runtime tail.
  - `PlayerState` now precomputes color-preference state, reducing repeated
    candidate-scoring overhead in large benchmark cases.
  - Current golden parity suite has no xfail fixtures.
  - Imported checked-in Dutch reference fixtures from `bbpPairings`
    (`dutch_2025_C5`, `dutch_2025_C9`, and the legacy diagnostic `issue_7`)
    plus the extra upstream `py4swiss` parity fixture
    `burstein_late_entries.trf`. `dutch_2025_C5` is the first concrete local
    fixture where `bbpPairings` and `swisspairing` agree while `py4swiss`
    disagrees.
  - `issue_7` is no longer treated as the main remaining 2026 blocker. That
    BBP bug report was opened on 2020-04-13, well before the 2026 ruleset, and
    current public references still split on it (`bbpPairings` vs
    `py4swiss` + `JaVaFo`). Keep it as a checked-in legacy divergence fixture.
  - Additional `issue_7` solver triage still improved the generic path:
    infeasible high-score MDP selections are now filtered before ranking,
    incomplete multi-MDP heterogeneous ties keep article sequence order, and
    the cheap exact odd-heterogeneous refinement window is wider. Those fixes
    remove the earlier top-half mismatch and confine the remaining divergence
    to the final collapsed 22-player bracket.
  - The heterogeneous structural tie-break is now limited to multi-MDP ties;
    single-MDP final-bracket ties keep exact article sequence order again,
    which restores BBP / py4swiss parity on the checked late-entry fixture.
  - Added a Chess-Results XLSX importer plus a first checked-in real-world OTB
    corpus reconstructed from Aeroflot Open 2026 (`9` pre-round TRF snapshots
    and published-pairings manifest). Aeroflot rounds 1-3 now have direct
    published-pairing tests and currently match the published pairings in
    `swisspairing`, `bbpPairings`, and `py4swiss`.
  - Aeroflot round 5 exposed two medium-large exact search gaps: a 33-player
    homogeneous odd bracket needed deeper downfloater coverage beyond the old
    20-player cutoff, and a 21-player one-MDP odd bracket needed a narrow
    resident-partner scan. `swisspairing` now matches `bbpPairings` on the
    full round-5 snapshot.
  - Aeroflot round 5 also surfaced another concrete local `py4swiss` split:
    `bbpPairings` and `swisspairing` agree on the final 3-player bracket while
    `py4swiss` chooses a different last-bracket pairing/bye outcome.
  - Aeroflot rounds 4 / 6 / 7 / 8 / 9 still disagree with the published
    pairings, but all three engines currently agree with each other there, so
    the remaining gap looks more like reconstruction or tournament-specific
    non-engine handling than a checked Dutch solver bug.
  - Aeroflot later-round diagnosis is now stronger: rounds 4 / 6 / 7 / 8 / 9
    are checked as consensus-engine-vs-published cases, and the published
    exports for those rounds include multiple `not paired` / bye seats
    (`3`, `5`, `7`, `9`, and `11` respectively). Treat those as real-world
    event-management divergences, not as active Dutch-core blockers.
  - Follow-up rulebook review: the official Aeroflot 2026 regulations say the
    pairings were generated by `Swiss Manager` and show no sign of acceleration.
    The FIDE handbook diff also matters here: `C.04.2` now allows broader
    limited post-publication pairing changes than the pre-2026 text, and
    `C.04.3` replaced the old PSD / PPB / CLB framing with the 2026 PAB +
    [C5]-[C21] criterion stack. This makes pre-2026 Dutch engines a weaker
    reference for Aeroflot-era events than BBP/FIDE.
  - Optional JaVaFo support is now wired into the reference-compare harness as
    a Swiss-Manager-lineage oracle. On the checked golden TRF catalog, JaVaFo
    agrees with the other engines on all pairable fixtures, but the checked
    public release does not reject the two impossible-fixture cases that the
    other three engines reject. On the Aeroflot round-5 hotspot, the same
    public JaVaFo release aligns with `py4swiss` rather than with
    `bbpPairings` + `swisspairing`, which is useful Swiss-Manager-lineage
    evidence but not stronger normative evidence than the 2026 FIDE rules plus
    BBP.
  - Added a normalized Lichess Swiss TRF corpus with checked provenance notes,
    plus a dedicated regression test module (`tests/test_lichess_reference.py`)
    to lock current multi-engine behavior on those imported real-world cases.
  - Added a one-command Lichess fixture refresh script
    (`benchmarks/import_lichess_fixtures.sh`) that normalizes local downloads,
    updates checked fixtures, and emits a reference-compare JSON snapshot.
  - Added a rulebook-driven 2026 coverage suite against the local handbook
    markdown copies and closed the remaining Dutch article 5.2 color-allocation
    gaps. The public state/input surface now also carries explicit
    `initial_color`, full-point unplayed-round state, and current-round float
    assignments, and Chess-Results float history can be derived from imported
    round sheets.
  - The multi-engine compare harness now preserves white/black orientation and
    honors TRF `XXC` initial-color configuration instead of normalizing away
    color-order-only differences.
  - Added a live Chess-Results event importer and expanded the checked real-world
    OTB corpus with Prague International Chess Festival 2026 D, Budapest Spring
    Festival 2026 Group A, and International Chessopen Graz 2026 A.
  - Budapest round 7 is now fixed, Budapest round 5 now matches
    `bbpPairings` after switching the compare/build-state path to TRF-derived
    float history, Graz now matches `bbpPairings`, `py4swiss`, and `JaVaFo`
    on all 9 checked rounds, and the earlier Graz round-1 runtime tail is
    closed out by a direct trivial first-round bracket path.
  - The checked Lichess corpus also moved to the `bbpPairings` side once float
    history was derived from the TRF instead of inherited from `py4swiss`;
    `py4swiss` and `JaVaFo` still agree with each other there.
  - External pychess integration checkpoint was merged forward onto
    `pychess-variants` `master`. The current integration now includes backend
    selection via `SWISS_PAIRING_BACKEND`, direct installed-wheel loading for
    `swisspairing`, the Swiss TRF export endpoint
    (`/games/export/tournament/{tournamentId}/trf`), the Swiss summary TRF
    download link in the client, native `swisspairing` snapshot construction,
    TRF-aligned float-history derivation, and extended dual-backend soak tests
    covering direct multi-round parity, full 5-round Swiss tournament flow,
    reload-boundary late-join parity, paused-player reload flow, repeated
    restart pairing, and multi-reload late-join / pause-rejoin state changes.
  - Packaging now includes a clean-wheel smoke path: local wheel install is
    documented for downstream projects, and CI installs the built wheel into a
    fresh virtualenv and exercises a small import/pairing smoke test on Python
    3.12, 3.13, and 3.14.
  - Exact/FIDE mode is now the public default through `pair_bracket()` and
    `pair_round_dutch()`, and it no longer times out on the checked
    Aeroflot/Graz/Budapest OTB stress cases.
  - Recent exact-path work now caches sequence-independent pair penalties and
    removes duplicate canonical exact candidates early, which cut the main
    remaining Budapest Group B round-5 cold exact case from about `7.5s` to
    about `2.2s`.
  - Budapest Group B rounds 5 and 7 now have direct exact-mode regressions in
    `tests/test_chess_results.py`, so the current exact frontier is anchored
    on real OTB cold-runtime cases as well as behavior.
  - Budapest Group B round 8 now matches the `py4swiss` / `bbpPairings`
    consensus in exact mode too, after restoring article-order tie-breaks in
    the odd one-MDP and odd homogeneous exact fallback paths.
  - Extended unit-test coverage for criteria and sequence behavior.
- Next:
  - Keep exact/FIDE correctness as the primary target and treat recurring
    synthetic runtime SLAs as regression alarms only. Future exact work
    should be judged mainly on rule conformance, checked corpus behavior, and
    real-world exact runtimes.
  - Publish/package `swisspairing` for downstream consumption so downstream
    integrations can move from manual local wheel reinstalls to tagged
    TestPyPI / PyPI releases.
  - Extend the real-world OTB corpus beyond the current
    Aeroflot/Prague/Budapest/Graz/Budapest-Group-B set. After switching the
    harness to TRF-derived float history, the Budapest Group B corpus now
    mainly exposes split-reference cases on rounds 4 / 5 / 9.
  - Deploy the pychess integration behind the existing backend switch, then
    evaluate the default-backend flip after production evidence rather than
    from more local soak expansion alone.

## Non-Goals (for stage 1)

- Full C.04.3 heterogeneous-bracket sequencing (Article 3.7 / 4.4).
- Unbounded exhaustive transposition enumeration for large brackets.
- Full pychess production cutover away from `py4swiss`.
