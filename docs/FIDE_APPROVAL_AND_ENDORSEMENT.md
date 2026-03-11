# FIDE Approval / Endorsement Path

Status: research note for future planning.

Last reviewed: 2026-03-11.

## Why this note exists

`swisspairing` is currently validated mainly by:

- direct rulebook-driven tests against the 2026 FIDE Dutch rules
- comparisons against `bbpPairings`, `py4swiss`, and optionally `JaVaFo`
- real-world TRF corpora and synthetic regressions

That is a strong engineering method, but it is not the same thing as the
formal FIDE approval / endorsement path.

If `swisspairing` ever aims at official FIDE recognition, we should expect the
validation method, public interfaces, and deliverables to change.

## Official source set

Primary sources used for this note:

- FIDE Handbook Appendix C.04.A, "Endorsement of a Software Program"
  - https://handbook.fide.com/chapter/C04A
  - The handbook page is currently labeled as effective till 2024-12-31.
- FE-1 application form
  - https://www.fide.com/FIDE/handbook/C04Annex1_FE1.pdf
- Verification Checklist (VCL19)
  - http://spp.fide.com/wp-content/uploads/2020/04/C04Annex4_VCL19.pdf
- Current endorsed-program list annex (FEP24)
  - https://handbook.fide.com/files/handbook/C04Annex3_FEP24.pdf
- TEC "Mandatory Tie-Breaks"
  - https://tec.fide.com/2024/04/30/mandatory-tie-breaks/
  - PDF: https://tec.fide.com/wp-content/uploads/2024/09/MandatoryTieBreaks-1.pdf
- TEC "TRF25 Final Draft"
  - https://tec.fide.com/2025/01/09/trf25-final-draft/
- TEC "TRF-2026"
  - https://tec.fide.com/trf-2026/
  - PDF: http://tec.fide.com/wp-content/uploads/2025/04/TRF-2026.pdf

## What the current handbook appendix requires

The appendix is still the clearest official text for the pairing-software
endorsement process.

Main points:

- The applicant submits an FE-1 form.
- The endorsed object is a program that helps manage a chess tournament, not
  just an unpublished algorithm description.
- Endorsement is pairing-system-specific.
- The program should expose a `FIDE mode`.
- The program should provide an English language interface.
- The program should import and export the FIDE data-exchange format.
- The program should make a free Pairings Checker (FPC) publicly available.
- The program should make a free Random Tournament Generator (RTG) publicly
  available, unless exempted by the commission.
- The program must be checkable in a controlled environment.
- The program must comply with the Verification Checklist.

For pairing systems where other endorsed programs already exist, the appendix
describes a more automated path:

- the request can be submitted at any time, provided it reaches the secretariat
  at least four months before the Congress where it would be presented
- an endorsed RTG is used to generate 5000 random tournaments
- the candidate FPC is checked on those tournaments
- up to 10 discrepancies are collected for analysis
- discrepancies are classified as:
  - input-file errors
  - candidate-program errors
  - rule-interpretation ambiguities

The FE-1 form adds one more practical requirement: the applicant's own
auto-test reports must not be worse than 1 difference per 500 test
tournaments.

The appendix also defines a four-year endorsement cycle plus a transition
period. If that older cycle logic is still the one in force, the current cycle
would be 2025-2028, because 2024 was the last leap year. Under that logic,
endorsements are normally not granted in the last year of the cycle unless the
commission decides otherwise.

## What the Verification Checklist adds

The Verification Checklist is operationally important because it is broader
than "produce legal pairings".

Highlights from VCL19:

- `FIDE mode` must be the default operating mode.
- A standard installation / invocation must enter the FIDE mode.
- The default pairing system in that mode must be the endorsed one.
- All pairing-related services offered in FIDE mode must behave correctly.
- FIDE mode must block functionality explicitly prohibited by FIDE.
- Pairings must use pairing numbers, not ratings.
- Pairing numbers cannot be changed after round 4 is paired.
- FIDE-approved acceleration systems must be implemented.
- TRF16 import is mandatory; TRF06 import is recommended.
- TRF16 export must be readable by a pairing checker, including non-standard
  scoring systems.
- Unusual results must be handled correctly.
- Pairing-allocated bye value must be configurable.
- Half-point byes must be supported.
- If full-point byes can be assigned manually, the software must warn that the
  practice is deprecated by FIDE.
- The program should make the official FIDE rating list readily usable.
- All included tie-breaks must produce handbook-compliant results.

## What the newer TEC material changes

The newer TEC pages suggest that the practical process is expanding beyond the
older appendix.

Important signals:

- The mandatory tie-break page says FIDE approval of a Tournament Manager
  Software (TMS) requires the listed mandatory tie-breaks.
- The TRF25 final-draft page says the new format is intended to improve
  exchange between Tournament Handler Programs (THPs) and external pairing
  engines.
- The TRF-2026 page says the aim is to prepare the tools needed for THP
  endorsement and for testing tie-breaks and standings as well as pairings.

Inference:

- The older appendix is still the clearest formal pairing endorsement text.
- The practical direction is moving toward a broader TMS / THP approval model.
- Before any real application, we should re-check the then-current TEC policy,
  because the terminology and scope are still evolving.

## What the endorsed-program list implies

The current FEP24 list is a useful practical clue.

All listed endorsed programs are tournament-manager-style products, not bare
libraries. Several of them use an external pairing engine such as `JaVaFo` or
`bbpPairings`, while others use an internal engine.

Inference:

- FIDE is clearly willing to endorse a tournament manager that embeds or calls
  an external pairing engine.
- A bare Python library is probably not the natural endorsement target.
- The safer future target would be either:
  - a small standalone THP / CLI built around `swisspairing`, or
  - a larger tournament manager that uses `swisspairing` as its endorsed
    pairing engine

## Where `swisspairing` already helps

The current project is not starting from zero.

Useful existing assets:

- deterministic 2026 Dutch pairing core
- explicit FIDE rulebook-driven test suite
- strong comparison harnesses against external engines
- checked-in real-world and synthetic TRF corpora
- wheel packaging and install smoke coverage
- TRF16-related tooling in the benchmark layer
- synthetic tournament generation that could evolve into an RTG
- pychess integration work proving the engine can be embedded in a larger
  tournament system

## Main gaps between today's repo and a realistic FIDE path

### 1. Endorsement target shape

Current state:

- `swisspairing` is a library with pairing APIs.

Gap:

- FIDE appears to endorse tournament-handling programs, not just an importable
  engine package.

Practical implication:

- If we ever go this way, we should probably build a small public THP / CLI on
  top of `swisspairing` instead of trying to endorse the raw library alone.

### 2. Public `FIDE mode`

Current state:

- There is no public end-user `FIDE mode`.
- There is no stable console entry point at all.

Gap:

- The checklist expects a standard invocation with a default FIDE mode and
  pairing behavior that is clearly bounded to the endorsed system.

### 3. Official Pairings Checker (FPC)

Current state:

- We have internal comparison harnesses and benchmark runners.
- We do not ship a public `checker` command that takes a TRF and reports round
  consistency.

Gap:

- The appendix expects a free FPC, typically command-line driven, able to read
  TRF input and rebuild/check round pairings.

### 4. Official Random Tournament Generator (RTG)

Current state:

- We have `simulate_tournament()` and benchmark-side batch generators.

Gap:

- We do not ship a public RTG command that generates many full TRFs as an
  endorsement-grade tool.

### 5. Public TRF import / export surface

Current state:

- We have useful TRF16-related code and exporters in the benchmarking /
  tooling layer.
- We can normalize lenient TRF16 and reconstruct corpora from Chess-Results.

Gap:

- The public package API is still pairing-first, not TRF-first.
- There is no stable public CLI or documented package API that says:
  "read this TRF, pair next round, and write an official checker-friendly TRF".

### 6. Acceleration support

Current state:

- Some harnesses can pair from states whose score already includes
  acceleration.

Gap:

- VCL19 expects FIDE-approved acceleration systems to be implemented as part of
  the product, not merely pre-applied externally.

### 7. Tournament-management surface

Current state:

- The package pairs rounds from explicit player state.
- It does not aim to be a full tournament manager.

Gap:

- VCL19 covers result-entry behavior, postponed games, pairing-allocated bye
  value, half-point byes, warnings for manual full-point byes, and rating-list
  handling.
- Those requirements sit above the current engine layer.

### 8. Standings and tie-break engine

Current state:

- The repo has no public, approval-grade standings / tie-break subsystem yet.

Gap:

- The mandatory tie-break material makes this a major requirement for TMS
  approval.
- Even for individual-only approval, the required list is substantial.
- This is probably the single biggest missing subsystem outside the pairing
  core itself.

### 9. TRF-2026 support

Current state:

- The repo is centered on TRF16 plus internal benchmark helpers.

Gap:

- The TEC direction is moving toward TRF-2026 for broader THP / external
  engine exchange, standings, and tie-break support.
- Long term, a FIDE-facing product should expect TRF-2026 work.

### 10. Controlled-environment and operator package

Current state:

- We can build wheels and run local smoke tests.

Gap:

- An endorsement-grade candidate should be easy for FIDE testers to install,
  invoke, and verify in a reproducible environment.
- That probably means a small, documented command-line product with stable
  inputs, stable outputs, and a scripted verification bundle.

## How the proof method would need to change

Our current method is still the right development method, but it would need to
be extended.

Keep:

- FIDE-first rulebook tests
- BBP / JaVaFo / py4swiss comparisons
- real-world OTB corpora
- synthetic performance and regression suites

Add:

- a public FPC and RTG
- an endorsement rehearsal that actually runs the 5000-random-tournament style
  process
- discrepancy triage in the same categories used by the appendix
- package-level verification, not just library-level correctness
- standings / tie-break verification once that layer exists

In short:

- our current method proves that the engine is becoming trustworthy
- the FIDE method would also require us to prove that the shipped program
  behaves correctly as an official tournament-handling product

## Recommended staged roadmap if we ever pursue this

### Phase 1: keep the current engine-first work

Continue:

- rulebook coverage
- BBP-backed comparisons
- real-world corpus expansion
- performance work

This remains the right foundation.

### Phase 2: define the actual candidate product

Decide early whether the eventual candidate is:

- a small standalone `swisspairing` CLI / THP
- a companion product built around `swisspairing`
- or a larger host application that embeds `swisspairing`

Recommendation:

- do not aim to endorse the raw Python library alone
- prefer a small, narrow CLI / THP wrapper around the engine

### Phase 3: promote internal tooling into public surfaces

Build stable commands such as:

- `swisspairing pair`
- `swisspairing check`
- `swisspairing simulate`
- `swisspairing trf normalize`

The goal is not convenience only. These commands are the likely basis of the
future FPC, RTG, and controlled-environment verification package.

### Phase 4: implement the missing tournament-manager requirements

Highest-priority missing items:

- FIDE mode
- acceleration support
- official TRF import / export surface
- result-state handling required by VCL19
- standings and tie-break engine

### Phase 5: start TRF-2026 work

Once the standings / tie-break layer exists, add TRF-2026 support in a way
that is compatible with an external pairing-engine workflow.

### Phase 6: run an internal endorsement rehearsal

Before any contact with FIDE:

- generate large random-tournament sets
- run the candidate checker against endorsed references
- collect and classify discrepancies
- produce FE-1 style evidence and auto-test reports

### Phase 7: contact TEC / SPPC before formal application

Because the official process is visibly evolving, confirm at that time:

- whether the target should be treated as endorsement, approval, or both
- whether a standalone engine-wrapper product is acceptable
- which TRF version is expected
- whether the tie-break scope can be limited to the tournament types we want to
  support

## Bottom line for `swisspairing`

If we ever want official FIDE recognition, the current repo is a strong engine
foundation, but it is not yet shaped like the product that FIDE appears to
test.

The likely future delta is:

- less emphasis on "does it match several reference engines on our corpora?"
- more emphasis on "does the shipped tournament-handling program expose the
  required FIDE mode, checker, generator, TRF handling, standings, and
  tie-break behavior in a reproducible way?"

That means the main future additions would probably be:

- a thin public THP / CLI wrapper
- endorsement-grade FPC and RTG commands
- standings / tie-break implementation
- TRF-2026 support
- a formal verification bundle

Until then, the current FIDE-first engine work is still the correct thing to
do.
