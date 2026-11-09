# Changes

## 0.2.0 (unreleased)

One release for benchmark v2.1, its two collections and the claim checks.

**Data**
- The Open Problems Benchmark v2.1 (commit 504492c of 9 Nov 2026): 149,372 problems, 395 single problems (21 new:
  Costas arrays of orders 32 and 33, the Moore graph of degree 57, srg(99,14,1,2), srg(88,27,6,9), the projective plane
  of order 12, three MOLS of order 10, 3 x 3 and 4 x 4 matrix multiplication, the Mona Lisa TSP, Erdős problems #107
  and #993, the kissing numbers in dimensions 22, 23 and 25 to 31) and the 148,977 family cells of v2.0; eight new
  checkers, byte for byte the benchmark's, checked against their SHA-256 before every run.
- Quantavane Prestige 100 (`collections/prestige100`): one hundred famous open problems, each a single problem of the
  benchmark, with the keeper's record, the history of the bounds, why it matters and the leaderboard of certificates we
  replayed; pages and index bundled.
- The Quantavane Originals (`collections/originals`): 39 new problems of ours in nine fields, each with its own checker
  (nine programs), its certificate, its instance files where it has them, a written novelty check and exact first
  values; the dropped candidates with the evidence.
- The benchmark's CHANGELOG, and the SHA-256 that fetch.sh pins for the Mona Lisa instance (checked before use, like
  CVRPLIB's).
- Our replays at 57988b0 of 9 Nov 2026 (was 1fbce3f of 8 Nov): 36 README sections and 11 replay folders indexed.

**Tools**
- `list_collection` and `get_collection_problem`: Prestige 100 by slot, family or words; the Originals by field or
  words; one problem in full.
- `get_problem`, `check_candidate`, `compare_to_record`, `cite` and the prompts take the Originals' ids; a collection
  problem's checker runs from its own folder, sandboxed, with the arguments obb.py gives it, and its verdicts equal
  obb.py's (tested for every Original's certificate).
- `run_claim_checks`: Quantavane's claim pipeline, offline. The benchmark's checker and a second checker written apart
  from it must agree on the exact value; red controls built from the object (each broken so that it must be refused)
  must be refused by both; the value must strictly beat the keeper's value on file. Verdict RECORD, NOT-A-RECORD or NOT
  VERIFIED, every check with its output, the keeper's value with the date read, the literature queries (recorded, not
  run) and the pipeline's packet as text. It never re-reads a keeper (offline) and says so.
- `quantavane_mcp/independent/second_check.py`: second checkers for 27 checker programs (Ramsey and multicolour
  Ramsey, Schur and weak Schur, van der Waerden, covering designs, constant weight codes, linear codes, covering arrays,
  spherical codes, kissing configurations, Golomb rulers, sorting networks, cap sets, no-three-in-line, strong powers,
  Hadamard and circulant weighing matrices, Costas arrays, MOLS, projective planes, strongly regular graphs, cages,
  degree-diameter graphs, snakes and coils, superpermutations, Erdős #993 trees, matrix multiplication), standard
  library only, runnable on their own.
- `check_candidate` results say where a certified value stands (`standing`) and which collection the problem is in.
- Resources: `quantavane://collections`, a collection's README, each problem's page, the Originals' certificates,
  `quantavane://benchmark/changelog`; the checkers index and documentation include the collections' checkers.
- Prompt `prepare_claim`. Command line: `quantavane-mcp claim PROBLEM FILE`.

**Fixes**
- The expected verdicts of test.sh lines that end with a comment (most of v2.1's) were skipped by the parser; they are
  read now, so the parity test covers the Prestige 100 record certificates, the new red controls and our C_1a value.
- The instance message for a pinned non-CVRPLIB file names its address and hash.

**Tests**: the Originals' certificates and red controls, the collections through the MCP client, every second checker
on known objects and on broken ones, agreement with the benchmark's checker on the bundled certificates, the claim
pipeline (verified, record, forged object, missing second checker, a red control that passes, the tool and the command
line), and, opt-in, obb.py parity for the Originals and the second checkers on every test.sh certificate.

## 0.1.0 (8 to 9 Nov 2026, tagged v0.1.0)

First release: the Open Problems Benchmark v2.0 (149,351 problems), its checkers in a sandbox with obb.py's verdicts,
verified results, replays and citations; tools `list_problems`, `get_problem`, `check_candidate`, `compare_to_record`,
`search_results`, `get_replay`, `cite`.
