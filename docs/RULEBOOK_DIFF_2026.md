# 2026 Rulebook Diff Notes

This note records the parts of the FIDE Swiss rulebook transition that are
most relevant to `swisspairing`.

Scope:

- understand which old-vs-2026 rule changes may explain current reference
  differences
- improve interpretation of Aeroflot Open 2026 results
- avoid over-trusting pre-2026 Dutch implementations for 2026 events

This document is for project guidance only. It does not mean the project
should support a pre-2026 pairing mode.

## Main Conclusions

- The repo target remains the FIDE rules effective from 1 February 2026.
- `bbpPairings` remains the strongest external 2026 Dutch oracle available in
  this project.
- The public `JaVaFo` release is useful as a Swiss-Manager-lineage oracle, but
  it is not treated as a stronger 2026 Dutch authority than `bbpPairings`.
- `py4swiss` should still be treated mainly as a compatibility oracle, not as
  the normative 2026 rules oracle.
- Aeroflot Open 2026 should be analyzed as a 2026-rules event, but its
  published pairings are not a perfect oracle because the event regulations say
  the pairings were managed by `Swiss Manager`.
- Old-vs-new handbook differences are large enough that a pre-2026 Dutch
  engine can disagree for legitimate rule reasons, not only for implementation
  bugs.

## Aeroflot 2026 Context

- Aeroflot Open 2026 was held from 27 February 2026 to 6 March 2026, so the
  effective default rules are the post-1-February-2026 rules.
- The Aeroflot regulations say the pairings were managed by `Swiss Manager`.
  That means a published-pairing mismatch is not automatically evidence that
  `swisspairing` or `bbpPairings` is wrong.
- The public `JaVaFo` release is worth checking for Aeroflot-style cases
  because Swiss Manager is JaVaFo-based, but that still does not make JaVaFo
  the rules authority for 2026 Dutch questions.
- The checked Aeroflot TRF snapshots currently show no acceleration markers, so
  `C.04.7` does not look like the primary explanation for the observed Aeroflot
  differences.

Practical interpretation for current Aeroflot evidence:

- If `swisspairing`, `bbpPairings`, and `py4swiss` all agree with each other
  but differ from the published Aeroflot pairings, treat that as a
  publication/reconstruction/tournament-procedure question first, not as a
  confirmed Dutch solver bug.
- If a published Aeroflot split also matches the public `JaVaFo` release,
  treat that as useful Swiss-Manager-lineage evidence.
- If `swisspairing` and `bbpPairings` agree but `py4swiss` differs, treat the
  result as a plausible 2026-rules divergence candidate.

## C.04.1

`C.04.1` did change across the transition, including wording around byes and
color-rule exceptions. This matters, but so far it looks secondary compared to
the `C.04.2` and `C.04.3` changes for the concrete mismatches already observed
in this repo.

Working assumption:

- keep watching `C.04.1` for corner-case legality questions
- do not currently treat it as the main explanation for Aeroflot or
  `py4swiss` parity gaps

## C.04.2

The `C.04.2` transition is important because it changes what can happen after
initial pairings are produced.

Project-relevant takeaway:

- the 2026 text allows broader limited post-publication pairing changes than
  the pre-2026 text

Why this matters here:

- Aeroflot used `Swiss Manager`, and some published-pairing differences may be
  explained by publication-stage handling rather than by the underlying Dutch
  engine logic
- this makes published pairings a useful real-world signal, but not a perfect
  oracle on their own

## C.04.3

This is the biggest algorithmic transition for `swisspairing`.

Pre-2026 Dutch rules use the older `PSD / PPB / CLB` framing. The 2026 Dutch
rules use the newer `PAB` and the `[C5]-[C21]` comparison stack.

Project-relevant takeaway:

- do not assume that a pre-2026 Dutch engine remains normatively valid for 2026
  events
- a `py4swiss` disagreement can be caused by rulebook lag, not only by a local
  implementation bug

This is the main reason the repo now treats:

1. FIDE handbook as authority
2. `bbpPairings` as the stronger 2026 Dutch oracle
3. `JaVaFo` as a Swiss-Manager-lineage oracle
4. `py4swiss` as a compatibility reference

## C.04.7

Acceleration still matters in general, but it does not currently look central
to the checked Aeroflot corpus.

Current project view:

- do not spend effort on acceleration as an explanation for Aeroflot unless new
  evidence appears
- revisit `C.04.7` later if another real-world corpus clearly uses it

## Current Repo Policy

- Do not add a pre-2026 rules mode unless a separate explicit product goal is
  introduced later.
- Keep evaluating current behavior against the 2026 handbook.
- Use `bbpPairings` to arbitrate current Dutch conformance questions where
  practical.
- Use `JaVaFo` to help interpret Swiss-Manager-style published pairings, not to
  override the 2026 handbook.
- Keep `py4swiss` in the loop because pychess replacement compatibility still
  matters.
- When a `py4swiss` difference appears, record whether it is likely:
  - a local bug
  - a 2026-rules divergence
  - a publication-stage / tournament-management effect

## Known Cases This Helps Interpret

- `tests/reference_fixtures/bbp/dutch_2025_C5.trf`
  `swisspairing` and `bbpPairings` agree, `py4swiss` disagrees
- Aeroflot round 5 final 3-player bracket
  `swisspairing` and `bbpPairings` agree, `py4swiss` disagrees
- Aeroflot round 5 on the checked public JaVaFo release
  `JaVaFo` aligns with the `py4swiss` side rather than with `bbpPairings`
- Aeroflot rounds 4 / 6 / 7 / 8 / 9
  all three engines currently agree with each other but differ from the
  published pairings

## Sources

- FIDE Handbook `C.04.1` from 1 February 2026:
  `https://handbook.fide.com/chapter/C0401202507`
- FIDE Handbook `C.04.1` till 31 January 2026:
  `https://handbook.fide.com/chapter/C0401Till2026`
- FIDE Handbook `C.04.2` from 1 February 2026:
  `https://handbook.fide.com/chapter/GeneralHandlingRulesForSwissTournaments202602`
- FIDE Handbook `C.04.2` till 31 January 2026:
  `https://handbook.fide.com/chapter/GeneralHandlingRulesForSwissTournamentsTill2026`
- FIDE Handbook `C.04.3` from 1 February 2026:
  `https://handbook.fide.com/chapter/C0403202602`
- FIDE Handbook `C.04.3` till 31 January 2026:
  `https://handbook.fide.com/chapter/C0403Till2026`
- FIDE Handbook `C.04.7` from 1 February 2026:
  `https://handbook.fide.com/chapter/C0407202602`
- FIDE Handbook `C.04.7` till 31 January 2026:
  `https://handbook.fide.com/chapter/C0407Till2026`
- Aeroflot Open 2026 festival page:
  `https://aeroflotopen.ru/en/international-chess-festival`
- Aeroflot Open 2026 regulations:
  `https://files.chessinschools.ru/AEROFLOT/2026/intr_chess_fest_2026%20%281%29.doc.pdf`
