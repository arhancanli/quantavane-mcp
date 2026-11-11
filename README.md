# quantavane-mcp

<!-- mcp-name: io.github.arhancanli/quantavane-mcp -->

An MCP server for open problems with exact checkers. It gives an AI agent, or a person at a terminal, Quantavane's
[Open Problems Benchmark](https://github.com/arhancanli/quantavane-benchmark) v2.1: 149,372 open problems, each with
its best known value, the source and date of that value, and an exact checker. 395 are single problems (Tao's
optimization constants, Ramsey numbers, cages, kissing numbers, sorting networks, Hadamard matrices, matrix
multiplication and more); 148,977 are cells of six families read from their keepers' tables (covering designs,
spherical codes, linear codes, covering arrays, constant weight codes and project scheduling). Two collections of our
own come with them: **Quantavane Prestige 100**, one hundred famous open problems (R(5,5), the kissing numbers from
dimension 5 to 31, 3 x 3 matrix multiplication, the Moore graph of degree 57 and more) with their keepers' records, and
the **Quantavane Originals**, 39 new problems of ours, each with its own checker, a written novelty check and our
first value. A candidate is scored by the benchmark's own checker, in a sandbox, offline, and the answer is a verdict
and an exact value, never an estimate.

`run_claim_checks` runs Quantavane's claim pipeline on an object: two separately written checkers must agree on its
exact value, red controls (copies of it broken so that they must fail) must be refused, and the value must beat the
keeper's value on file. It also answers from Quantavane's verified results (the open dataset), our independent replays
of certificates in the optimization constants repository, and gives citations for all of it.

- **Exact.** Values are integers or fractions, compared exactly. The checkers are byte for byte those of the public
  benchmark, and every reference certificate gets the verdict the benchmark's own runner gives (tested).
- **Offline.** The server never opens a network connection. Its data is a snapshot whose commits and dates it reports.
- **Honest.** A check that hits a limit says "no verdict", not "invalid". A value is a record only when it is certified
  and beats the best known value. Best known values credited to other people say so, with their source.

## Five-minute start

You need [uv](https://docs.astral.sh/uv/getting-started/installation/); it fetches Python 3.10 or later if your system
lacks it. The first command downloads the server from GitHub (about 15 seconds); the rest take a second or two each.

```sh
# 1. Check the install: every bundled file against its SHA-256, then reference certificates through the checkers
uvx --from git+https://github.com/arhancanli/quantavane-mcp quantavane-mcp selftest

# 2. Check a covering design C(17,7,4,6) with 17 blocks (ours, listed by the Covering Repository)
curl -sSLO https://raw.githubusercontent.com/arhancanli/quantavane-benchmark/main/refs/ours_covering_17-7-4-6.txt
uvx --from git+https://github.com/arhancanli/quantavane-mcp quantavane-mcp check covering-17-7-4-6 ours_covering_17-7-4-6.txt
#    "verdict": "certified", "value": "17", "standing": "equals the best known"

# 3. Remove one block and check again: refused, with the 6-subset that is no longer covered
sed 1d ours_covering_17-7-4-6.txt > broken.txt
uvx --from git+https://github.com/arhancanli/quantavane-mcp quantavane-mcp check covering-17-7-4-6 broken.txt || true
#    "verdict": "not_certified", "reason": "the 6-subset [2, 3, 5, 8, 9, 11] meets every block in fewer than 4 points"
```

Then give the tools to an agent, for example Claude Code (other clients: [connect a client](#connect-a-client)):

```sh
claude mcp add quantavane -- uvx --from git+https://github.com/arhancanli/quantavane-mcp quantavane-mcp
```

and ask it to pick an open problem, build candidates in code and check them. `check` and `claim` print JSON, so they
also work in any scoring pipeline without an MCP client.

## Contents

- [Five-minute start](#five-minute-start)
- [Install](#install) and [connect a client](#connect-a-client)
- [Tools, resources and prompts](#tools-resources-and-prompts)
- [Examples](#examples)
- For [AI agent builders](#for-ai-agent-builders), [researchers](#for-researchers) and [professors](#for-professors)
- [Limits](#limits), [configuration](#configuration), [security](#security)
- [Licence](#licence) and [citation](#citation)

## Install

Python 3.10 or later on Linux or macOS. The Ramsey checker is C, so Ramsey problems also need a C compiler (`cc`).

```sh
uvx quantavane-mcp --version          # run without installing (uv)
pip install quantavane-mcp            # or install with pip
quantavane-mcp selftest               # checks the bundled data and runs reference certificates
```

From the source: `uvx --from git+https://github.com/arhancanli/quantavane-mcp quantavane-mcp`, or in a clone,
`pip install .`. A client can start the server from GitHub the same way: wherever this README says `uvx
quantavane-mcp`, write `uvx --from git+https://github.com/arhancanli/quantavane-mcp quantavane-mcp` (in JSON,
`"args": ["--from", "git+https://github.com/arhancanli/quantavane-mcp", "quantavane-mcp"]`).

`selftest` verifies every bundled file against its SHA-256, then runs a covering design, a constant weight code, a
spherical code, a constant, a Ramsey colouring and one of the Originals through the sandboxed checkers, compares the
verdicts with the benchmark's, and runs the claim checks once.

## Connect a client

The server speaks MCP over stdio. Any client starts it with the command `uvx` and the argument `quantavane-mcp`.

**Claude Code**

```sh
claude mcp add quantavane -- uvx quantavane-mcp
```

or, for a project, in `.mcp.json`:

```json
{
  "mcpServers": {
    "quantavane": { "command": "uvx", "args": ["quantavane-mcp"] }
  }
}
```

**Claude Desktop** (`claude_desktop_config.json`; on macOS in `~/Library/Application Support/Claude/`, on Windows in
`%APPDATA%\Claude\`). Desktop apps do not always see your shell's `PATH`, so give the full path of `uvx`
(`which uvx`). They may also start servers in the root folder, so name the folders your certificate files live in:

```json
{
  "mcpServers": {
    "quantavane": {
      "command": "/full/path/to/uvx",
      "args": ["quantavane-mcp"],
      "env": { "QUANTAVANE_MCP_ROOTS": "/Users/you/candidates" }
    }
  }
}
```

**Cursor** (`~/.cursor/mcp.json`) uses the same `mcpServers` block as Claude Desktop.

**VS Code** (`.vscode/mcp.json`):

```json
{
  "servers": {
    "quantavane": { "type": "stdio", "command": "uvx", "args": ["quantavane-mcp"] }
  }
}
```

**Codex CLI** (`~/.codex/config.toml`):

```toml
[mcp_servers.quantavane]
command = "uvx"
args = ["quantavane-mcp"]
```

**Other clients**: command `uvx`, arguments `["quantavane-mcp"]`, transport stdio. With a `pip` install the command
is `quantavane-mcp` (or `python -m quantavane_mcp`).

## Tools, resources and prompts

| Tool | What it does |
| --- | --- |
| `list_problems` | The problems, one line each, with pages. Without a family it lists the single problems; with `family` it lists that family (its single problems, then its cells), filtered by the cells' parameters (`params`, such as `{"v": 13, "t": 3}`) or by words, or draws a random `sample` of cells with a `seed` (the same draw as `obb.py sample`). |
| `get_problem` | One problem or family cell (a cell is written out like a problem file, as `obb.py show` does): statement, objective, best known value with source, keeper and read date, values in review, certificate format, checker, improvement rule, reference certificates, a cell's parameters and the table's other bound. |
| `check_candidate` | Runs the problem's exact checker on a certificate (text, or a local file) in the sandbox. Verdict, exact value, comparisons with the best known values, the certificate's SHA-256 and the commands that rerun the check with the public benchmark. |
| `compare_to_record` | Is a value better than the best known? Exact comparison with the page best and the verified values in review, with the date the value was read. Proves nothing about any object. |
| `search_results` | Quantavane's verified results by table, cell (`CAN(3,2872,4)`, `C(84,7,2,5)`, `A(51,6,6)`, `R(8,12)`, `[63,14,33] over GF(5)`, ...), words, date or status, with citation info. |
| `get_replay` | Our replay of a certificate in [teorth/optimizationproblems](https://github.com/teorth/optimizationproblems), by pull request, row (`1c Kos2026`) or constant: what was checked, the exact values, our programs and the commands that re-derive it. |
| `cite` | BibTeX and citation text (and CITATION.cff) for the benchmark, a problem, a result, the dataset, a replay or this server. |
| `list_collection` | Prestige 100 (slot, problem, family, the record as its keeper lists it and who holds it) or the Originals (field, title, our best known value, status), with words and a family or field to filter by. |
| `get_collection_problem` | One problem of a collection in full, by id or Prestige 100 slot: for Prestige 100 the record and its holders, the other bound, what would beat it, the keeper read with date and version, the history of the bounds, why it matters and our replayed certificates; for the Originals the statement, context, novelty check, exact first values and references. |
| `run_claim_checks` | Quantavane's claim pipeline on one object: the benchmark's checker and a second checker written apart from it (both sandboxed) must agree on the exact value, red controls built from the object must be refused by both, and the value must strictly beat the keeper's value on file. RECORD, NOT-A-RECORD or NOT VERIFIED, with every check, the keeper's value and its date, the literature queries to run and the pipeline's packet as text. |

Every tool is read-only, has an input schema with limits and an output schema, and returns structured content.
Errors come back as tool errors that say what to change. `get_problem`, `check_candidate`, `compare_to_record`,
`run_claim_checks` and `cite` take the ids of the Originals (such as `qr-sumfree`) as well; the Prestige 100 problems are
single problems of the benchmark and keep their ids (such as `ramsey-5-5`).

Resources: `quantavane://about` (version, data commits and dates, limits), `quantavane://problems` and
`quantavane://problems/{problem_id}` (a single problem or a cell), `quantavane://families` and
`quantavane://families/{name}` (each family's keeper, date read, open rule and what was left out),
`quantavane://checkers`, `quantavane://checkers/{program}` (documentation) and
`quantavane://checkers/{program}/source`, `quantavane://refs/{filename}` (our reference certificates),
`quantavane://benchmark/readme`, `quantavane://benchmark/changelog`, `quantavane://open-data/readme`,
`quantavane://collections`, `quantavane://collections/{name}` (a collection's README),
`quantavane://collections/{name}/{problem_id}` (a problem's page, by id or Prestige 100 slot) and
`quantavane://collections/{name}/refs/{filename}` (the Originals' certificates). Problem ids, checker names, collection
names and certificate names complete as you type in clients that support completion.

Prompts: `attack_problem(problem_id)`, `verify_certificate(problem_id, certificate_path)`, `explain_replay(pr)`,
`prepare_claim(problem_id, certificate_path)`.

## Examples

Outputs below are abridged from real calls.

Check a covering design from a file:

```json
check_candidate {"problem_id": "covering-17-7-4-6", "certificate_path": "/tmp/ours_covering_17-7-4-6.txt"}
{
 "verdict": "certified",
 "value": "17",
 "improves_page_best": false,
 "comparisons": [{"reference": "page best", "value": "17", "threshold": "17", "improves": false,
   "source": "Covering Repository (coveringrepository.com), C(17,7,4,6) = 17 blocks: ours, listed since 2026-10-26 (before it 18); read 6 Nov 2026"}],
 "certificate_sha256": "cf4b0b58b318634eb94e629075d9a916d6aa5585c240bf75d1221e0cbb8d688d",
 "reproduce": "git clone https://github.com/arhancanli/quantavane-benchmark && cd quantavane-benchmark && git checkout 9cb6183\npython3 -I obb.py check covering-17-7-4-6 CANDIDATE ..."
}
```

Remove one block and the same call returns `"verdict": "not_certified"` with the checker's reason
(`some 6-subset meets every block in fewer than 4 points`).

A family cell: the open entries of Grassl's tables for binary codes of length 32, then one in full:

```json
list_problems {"family": "linear-code", "params": {"q": 2, "n": 32}}
{"total": 2, "problems": [{"id": "code-q2-n32-k14", "title": "Linear code [32,14] over GF(2)", "best_known": "8"},
                          {"id": "code-q2-n32-k18", "title": "Linear code [32,18] over GF(2)", "best_known": "6"}]}

get_problem {"problem_id": "code-q2-n32-k14"}
{"params": {"q": 2, "n": 32, "k": 14}, "objective": "maximize",
 "best_known": {"value": "8", "exact": "8", "read": "read 2026-11-09"},
 "bound": {"value": "9", "kind": "upper bound", "source": "the upper bound in the same table"},
 "provenance": {"keeper": "M. Grassl, bounds on the minimum distance of linear codes (codetables.de)",
                "url": "https://www.codetables.de/BKLC/BKLC.php?q=2&n=32&k=14", "read": "2026-11-09", ...},
 "checker": {"program": "lincode_check.py", "standalone": "python3 -I checkers/lincode_check.py 2 32 14 FILE", ...}}
```

A [32,14] binary code with minimum distance 9 would close this entry. `{"family": "linear-code", "sample": 5,
"seed": 0}` draws five cells at random, the same five that `obb.py sample linear-code 5 0` prints.

Would 0.41035 be a new lower bound for the autocorrelation constant C_1c?

```json
compare_to_record {"problem_id": "1c-lower", "value": "0.41035"}
{"value": "8207/20000", "improves_page_best": true, "improves_verified_in_review": false,
 "best_known_read": "as on the page at main 87b4ebb; problem file of 2026-11-05"}
```

It beats the page's 0.4103333 but not the certificate in review (0.41035965...), and it is only a number until a
certificate for it is checked.

A covering array cell:

```json
search_results {"cell": "CAN(3,2872,4)"}
{"covering_array_entries": [{"t": 3, "k": 2872, "v": 4, "N": 604, "previous_N": 607, "family_rows_k": 2876,
  "source": "ca-tools (github.com/chrispbsmolen/ca-tools), VERIFIED"}], ...}
```

Our replay of a pull request, with the commands to re-derive it:

```json
get_replay {"pr": 292}
{"found": true, "matches": [{"heading": "C1a, C1c and C1d (3 to 7 November 2026)",
  "rows": ["| $C_{1c} \\geq$ | [#292](...) (Koshta's row) | ... | 134648548624804778248790016 / 328144294688458468928334649 = 0.41033335274849333953... | ..."],
  "rederive": ["git clone https://github.com/arhancanli/quantavane-replays.git",
               "cd quantavane-replays && git checkout b892ccb", "./fetch.sh && ./run_all.sh"]}], ...}
```

A Prestige 100 problem and one of the Originals:

```json
list_collection {"collection": "prestige100", "group": "Ramsey", "limit": 2}
{"total": 24, "entries": [{"id": "ramsey-5-5", "slot": 1, "family": "Ramsey numbers", "record": "R(5,5) ≥ 43",
  "holders": "G. Exoo (1989)", "flagship": true, "quantavane": false}, ...]}

get_collection_problem {"collection": "originals", "problem": "qr-sumfree"}
{"title": "Largest sum-free set of quadratic residues", "entry": {"field": "Number theory", "objective": "maximize",
 "best_known": {"value": "174", ...}, "novelty": {"verdict": "new as stated. ...", ...}, "first_values": {...}}, ...}
```

The claim pipeline on our 6-regular graph of girth 9 on 5,600 vertices:

```json
run_claim_checks {"problem_id": "cage-6-9", "certificate_path": "/tmp/ours_cage_6_9_n5600.s6"}
{"verdict": "RECORD (5600 vs listed 7781; both checks OK, red controls all rejected; keeper value on file, read 8 Nov 2026; problem file of 2026-11-08; re-read the keeper today before sending)",
 "verified": true, "record": true, "second_checker": "second_check.py cage", "red_controls": 1,
 "checks": [{"kind": "check", "program": "cage_check.py", "verdict": "certified", "value": "5600"},
            {"kind": "check", "program": "second_check.py cage", "verdict": "certified", "value": "5600"},
            {"kind": "red", "name": "the edge 0 800 removed (two vertices lose a neighbour)", "program": "cage_check.py", "verdict": "not_certified"},
            {"kind": "red", "name": "the edge 0 800 removed (two vertices lose a neighbour)", "program": "second_check.py cage", "verdict": "not_certified"}],
 "keeper": {"name": "House of Graphs cage table (...)", "value": "7781", "read": "read 8 Nov 2026; problem file of 2026-11-08",
            "re_read": "not done: offline. The pipeline re-reads the keeper's page the same day before a claim is sent; ..."},
 "packet": {"VERDICT": "...", "checks.txt": "...", "keeper.txt": "...", "literature.json": "...", "README.md": "..."}}
```

Without an MCP client, the same check from the command line (JSON out; exit status 0 certified, 1 not certified, 2
no verdict or an error), and the claim checks (exit status 0 RECORD, 1 NOT-A-RECORD, 2 NOT VERIFIED or an error):

```sh
quantavane-mcp check covering-17-7-4-6 design.txt
quantavane-mcp claim covering-17-7-4-6 design.txt
```

## For AI agent builders

- Start an agent with the `attack_problem` prompt, or give it the tools and the server's instructions. The loop is:
  `get_problem`, build candidates in code, write each to a file, `check_candidate` with `certificate_path`, keep the
  certified ones. Inline certificates are accepted up to 4,000,000 characters, but files keep the context small.
- Treat `verdict` as the only ground truth: `certified` proves `value`; `not_certified` means the certificate is
  invalid (`reason` says why); `no_verdict` means a limit stopped the check and nothing was proved either way.
- Long checks send progress notifications every 5 seconds to clients that ask for them. `timeout_s` goes up to 900
  by default.
- Lists are paged (`total`, `has_more`, `next_offset`); outputs are small, and large texts (certificates, checker
  sources) are resources the agent reads only when it needs them.
- Before reporting a new best, run `run_claim_checks` (or the `prepare_claim` prompt): it adds the second checker and
  the red controls, and says RECORD only when both checkers agree, every red control is refused and the value beats
  the keeper's value on file.
- Training: the `quantavane_mcp.checking.Checker` class is the same sandboxed checker as a Python API
  (`Checker(store, settings).check_data(problem_id, data)`), and `quantavane-mcp check` is a scoring command for any
  pipeline. Gym environments around the same checkers can be attached later: set `QUANTAVANE_MCP_GYM` to a backend
  (`package.module:attribute`) with `environments()` and `propose(env_id, obj)` and the server adds `gym_environments`
  and `gym_propose`. Unset, it adds nothing and imports nothing.

## For researchers

- **What is checked.** Each problem names its checker; `quantavane://checkers/{program}` gives the checker's own
  documentation (what it proves and how) and its source. The checkers are standard-library Python and one C program,
  written apart from the searches that produced the reference results. They are the public benchmark's files at the
  commit in `quantavane://about`, verified against their SHA-256 before every run.
- **Values.** Integers for counts (blocks, words, vertices, route cost); exact fractions for the autocorrelation,
  Korenblum, Turán and Bohr-radius bounds; for spherical codes the largest cosine in 50-digit arithmetic printed to 20
  decimals; for C16 the lower end of a rigorous enclosure; for the checkers added since v1.1 (and the covering array,
  linear code and scheduling cells) the integer or fraction the checker prints after `RESULT`. `exactness` and
  `score_meaning` in each result say which.
- **Comparisons.** Two reference values are kept apart: the best value on the source page or table, and the best
  verified value still in review (a pull request whose certificate we replayed). Claims nobody has replayed are listed
  and never compared. A printed value whose exact original is unknown counts as beaten only by more than its last
  printed digit.
- **Reproducing.** Every result carries the commands that rerun the same check with the public benchmark, and the
  certificate's SHA-256. The test suite checks that the server's exact value and verdicts equal those printed by the
  benchmark's own `obb.py` for every certificate in its `test.sh` (the routing ones when the CVRPLIB files are
  present).
- **A certified improvement is a candidate record.** It becomes a record when the table's keeper lists it. The
  problem's source names the table; `cite(target="problem")` gives the reference.
- **Claim checks.** `run_claim_checks` is the gate Quantavane uses before it sends a result to a keeper. The second
  checkers (`quantavane_mcp/independent/second_check.py`, standard library, runnable on their own) were written from
  the problem statements, apart from the benchmark's checkers, for 27 checker programs: Ramsey and multicolour Ramsey,
  Schur and weak Schur, van der Waerden, covering designs, constant weight codes, linear codes (over GF(2) to GF(9) by
  listing the code), covering arrays, spherical codes (the first checker's printed largest cosine confirmed exactly to
  one unit of its 20th decimal), kissing configurations, Golomb rulers, sorting networks, cap sets, no-three-in-line,
  strong powers of cycles, Hadamard and circulant weighing matrices, Costas arrays, mutually orthogonal Latin squares,
  projective planes, strongly regular graphs, cages, degree-diameter graphs, snakes and coils, superpermutations, trees
  for Erdős problem #993 and matrix multiplication algorithms. Each red control breaks the object in a way that must
  be refused (a clique planted, a block or an edge removed, a word or vector repeated, a point duplicated). The
  analytic constants, routing, scheduling, the Mona Lisa tour, Erdős #107 and the Originals have no second checker yet,
  so their claims come back NOT VERIFIED. A second checker that would exceed its limits says so (no verdict) rather
  than guessing: the largest of our own cages (17,600 vertices), very large covering designs and codes, and sorting
  networks on more than about 35 channels are past them.

## For professors

- The problems are real: Ramsey lower bounds from Radziszowski's survey, spherical codes from Henry Cohn's table,
  covering designs from the Covering Repository, constant weight codes from Andries Brouwer's table, CVRPLIB
  instances, and constants from the optimization constants repository. Many best known entries are recent.
- Students can submit a certificate and get an exact verdict, with the checker's reason when it fails, without
  setting up the checkers themselves. An invalid certificate is not an error: it gets `not_certified` and a reason.
  The Ramsey and covering checkers make good first exercises (small inputs, clear failures).
- For a course, set `QUANTAVANE_MCP_ROOTS` to the folder students write their certificates to.
- Results that improve a problem can be sent to the table's keeper, and to Quantavane: see the benchmark's
  [Submitting](https://github.com/arhancanli/quantavane-benchmark#submitting) section. Accepted results carry the
  student's name.

## Limits

- **A snapshot.** The data is from the commits and dates in `quantavane://about` (benchmark v2.1 with Prestige 100 and
  the Originals, 504492c of 9 Nov 2026, its tables read on 8 and 9 Nov; open data of 7 Nov 2026; replays 57988b0 of 9
  Nov 2026). Best known values move: check the source page before claiming a record (`run_claim_checks` compares with
  the value on file and says so). A newer release of this package brings newer data.
- **Instance files are not bundled.** The 14 vehicle routing problems need CVRPLIB's instance files, the Mona Lisa
  problem its TSP instance, and the project-scheduling cells the instance files of their sets (third-party data). Run `fetch.sh` in a clone of the
  benchmark for CVRPLIB and the Mona Lisa instance, unpack the scheduling sets as the family's `instances` note says,
  and set `QUANTAVANE_MCP_INSTANCES` to the `instances/` folder. CVRPLIB files and the Mona Lisa instance are checked
  against the SHA-256 the benchmark pins before they are used. The server never downloads them. (The Originals'
  instance files are ours and bundled.)
- **Ramsey.** Needs a C compiler; the checker is compiled once into a cache folder. Colourings have at most 2048
  vertices.
- **Time.** The default timeout is 120 s, and 300 s for covering designs (a C(v,k,t,m) check can take about three
  minutes); `run_claim_checks` gives each program run 600 s by default (its second checkers are plain Python: a Ramsey
  colouring on 282 vertices takes about three minutes there). Most checks take under a second; the Turán (42a) and Bohr radius (59a) checkers can take a minute or more
  on large certificates, a linear code at the edge of its family about 20 s.
- **Platforms.** Linux and macOS. On Windows the memory cap cannot be enforced, so checks are refused unless
  `QUANTAVANE_MCP_ALLOW_UNCAPPED=1`; WSL works as Linux.
- **What a checker proves is what its documentation says.** For the analytic constants the checkers verify the
  quantitative hypotheses of a stated criterion; the mathematics of the criterion itself is cited, not formalized.

## Configuration

All optional, as environment variables:

| Variable | Default | Meaning |
| --- | --- | --- |
| `QUANTAVANE_MCP_ROOTS` | working folder (unless `/` or home) and the temporary folders | Folders `certificate_path` may point into, separated by `:` (`;` on Windows). |
| `QUANTAVANE_MCP_TIMEOUT_S` | 120 | Default time limit of one check, in seconds. |
| `QUANTAVANE_MCP_MAX_TIMEOUT_S` | 900 | Largest `timeout_s` a caller may ask for. |
| `QUANTAVANE_MCP_MEMORY_MB` | 1024 | Memory cap of one checker process. |
| `QUANTAVANE_MCP_MAX_BYTES` | 33554432 | Largest certificate file. |
| `QUANTAVANE_MCP_MAX_CONCURRENT` | 2 | Checks running at once. |
| `QUANTAVANE_MCP_INSTANCES` | none | Folder with CVRPLIB instance files. |
| `QUANTAVANE_MCP_BENCHMARK_DIR` | bundled copy | A local benchmark checkout to use instead (newer problems; not verified against the release). |
| `QUANTAVANE_MCP_CACHE` | `~/Library/Caches/quantavane-mcp` or `~/.cache/quantavane-mcp` | Where the compiled Ramsey checker is kept. |
| `QUANTAVANE_MCP_CC` | `cc`, then `gcc`, then `clang` | C compiler. |
| `QUANTAVANE_MCP_GYM` | none | A training-gym backend, `package.module:attribute`. |
| `QUANTAVANE_MCP_ALLOW_UNCAPPED` | unset | `1` runs checks where the memory cap cannot be enforced. |

## Security

- Checkers run as separate processes: an argument list, never a shell; a fresh empty working folder; a minimal
  environment; stdin closed; Python in isolated mode; their own process group, killed whole at a limit.
- Limits on every check: wall-clock timeout, CPU time, memory (RLIMIT_AS and resident-size sampling on Linux,
  physical-footprint sampling every 20 ms on macOS, where a very fast allocation can overshoot briefly before the
  kill), files limited to 0 bytes, 64 file descriptors, certificate size.
- `certificate_path` must resolve, after symlinks, to a regular file inside the allowed folders; hidden files and
  folders are refused. The file is copied before the check, so the checker never sees your path.
- Checker output is returned with local paths removed. The server reads only its own data and the files you point it
  to, and writes only the compiled Ramsey checker into its cache folder.
- A Ramsey file with rows longer than the C checker's 2048 columns is rejected before the checker runs. The checker
  rejects such rows itself as well (exit 2); the server's check is a second layer.

## Development

```sh
uv venv && uv pip install -e ".[test]"
pytest                                             # the whole suite
QUANTAVANE_MCP_TEST_BENCHMARK=~/quantavane-benchmark pytest tests/test_parity_obb.py   # parity with obb.py
QUANTAVANE_MCP_TEST_INSTANCES=~/quantavane-benchmark/instances pytest -k routing        # routing references
python3 -I scripts/sync_data.py --open-data DIR    # rebuild the bundled data from the sources at pinned commits
python3 -I scripts/sync_data.py --open-data DIR --check   # confirm the bundled data matches the sources
```

## Licence

Code: MIT ([LICENSE](LICENSE)). The bundled data keeps the licence its source states
([LICENSE-DATA.md](LICENSE-DATA.md)): the benchmark's files (problems, families, checkers, reference certificates,
the Originals) and the replay index are MIT, as the benchmark and the replays repository state; the Prestige 100
collection's data is CC BY 4.0 with its checkers MIT, as its index states; the verified results are CC BY 4.0, as the
dataset states. The families hold values read from other people's tables, credited to their keepers and
holders (LICENSE-DATA.md names each table); no keeper's file is included.

## Citation

`cite(target="server")`, or:

```bibtex
@software{quantavane-mcp,
  author  = {Canli, Arhan},
  title   = {quantavane-mcp: an MCP server for open problems with exact checkers},
  year    = {2026},
  version = {0.2.0},
  url     = {https://github.com/arhancanli/quantavane-mcp}
}
```

To cite the benchmark, a problem, a result, the dataset or a replay, use `cite` with that target; citing a problem
also gives the source of its best known value, which should be cited as well. See also [CITATION.cff](CITATION.cff).

Quantavane: https://quantavane.com. Questions and corrections: open an issue.
