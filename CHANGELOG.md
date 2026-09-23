# Changelog

## 0.2.0

### Added
- **Agent-view projection** (`mathbench-export`): whitelist-only export that strips
  evaluator fields (variants, generator metadata, scoring, references), replaces
  statements with neutral per-goal wording, assigns opaque instance IDs, and
  shuffles instance order from an evaluator-held secret. Produces a separate
  evaluator-only binding.
- **Randomized, scalable matching generator**: planted tight-Hall-set
  construction with 4–2000 vertices per side, randomized Hall-set size, density,
  labels, edge order, and family composition (`F,F,I,O` or `F,I,I,O`).
  Polynomial-time Hopcroft–Karp / König audit and reference certificates.
- Concise structural subset-sum certificates (common divisor, superincreasing
  greedy remainder) replacing exhaustive reachable-sum lists.
- GitHub Actions CI on Python 3.11–3.13.

### Changed
- Grading weights are read from the frozen `configs/protocol.json`; family-local
  scoring declarations must agree with it or grading fails.
- Unknown, duplicate, missing, or unparseable submission rows now yield a
  deterministic zero-score receipt instead of an exception.
- Evaluator receipts hash the protocol plus every parser, projection, and
  validator module involved.

## 0.1.0

- Initial public release: four certificate validators (bipartite matching,
  subset sum, graph coloring, bin packing) and ten `public_dev` families.
