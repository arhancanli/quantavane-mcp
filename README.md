# quantavane-mcp

<!-- mcp-name: io.github.arhancanli/quantavane-mcp -->

An MCP server for open problems with exact checkers. It gives an AI agent, or a person at a terminal, Quantavane's
[Open Problems Benchmark](https://github.com/arhancanli/quantavane-benchmark): 117 open problems, each with its best
known value, the source and date of that value, and an exact checker. A candidate is scored by the benchmark's own
checker, in a sandbox, offline, and the answer is a verdict and an exact value, never an estimate.

It also answers from Quantavane's verified results (the open dataset), our independent replays of certificates in the
optimization constants repository, and gives citations for all of it.

- **Exact.** Values are integers or fractions, compared exactly. The checkers are byte for byte those of the public
  benchmark, and every reference certificate gets the verdict the benchmark's own runner gives (tested).
- **Offline.** The server never opens a network connection. Its data is a snapshot whose commits and dates it reports.
- **Honest.** A check that hits a limit says "no verdict", not "invalid". A value is a record only when it is certified
  and beats the best known value. Best known values credited to other people say so, with their source.

## Contents

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
`pip install .`.

`selftest` verifies every bundled file against its SHA-256, then runs a covering design, a constant weight code, a
spherical code, a constant and a Ramsey colouring through the sandboxed checkers and compares the verdicts with the
benchmark's.

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
| `list_problems` | The problems, one line each, with filters (family, words) and pages. |
| `get_problem` | One problem: statement, objective, best known value with source and read date, values in review, certificate format, checker, improvement rule, reference certificates. |
| `check_candidate` | Runs the problem's exact checker on a certificate (text, or a local file) in the sandbox. Verdict, exact value, comparisons with the best known values, the certificate's SHA-256 and the commands that rerun the check with the public benchmark. |
| `compare_to_record` | Is a value better than the best known? Exact comparison with the page best and the verified values in review, with the date the value was read. Proves nothing about any object. |
| `search_results` | Quantavane's verified results by table, cell (`CAN(3,2872,4)`, `C(84,7,2,5)`, `A(51,6,6)`, `R(8,12)`, `[63,14,33] over GF(5)`, ...), words, date or status, with citation info. |
| `get_replay` | Our replay of a certificate in [teorth/optimizationproblems](https://github.com/teorth/optimizationproblems), by pull request, row (`1c Kos2026`) or constant: what was checked, the exact values, our programs and the commands that re-derive it. |
| `cite` | BibTeX and citation text (and CITATION.cff) for the benchmark, a problem, a result, the dataset, a replay or this server. |

Every tool is read-only, has an input schema with limits and an output schema, and returns structured content.
Errors come back as tool errors that say what to change.

Resources: `quantavane://about` (version, data commits and dates, limits), `quantavane://problems` and
`quantavane://problems/{problem_id}`, `quantavane://checkers`, `quantavane://checkers/{program}` (documentation) and
`quantavane://checkers/{program}/source`, `quantavane://refs/{filename}` (our reference certificates),
`quantavane://benchmark/readme`, `quantavane://open-data/readme`. Problem ids, checker names and certificate names
complete as you type in clients that support completion.

Prompts: `attack_problem(problem_id)`, `verify_certificate(problem_id, certificate_path)`, `explain_replay(pr)`.

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
 "reproduce": "git clone https://github.com/arhancanli/quantavane-benchmark && cd quantavane-benchmark && git checkout 6c6c027\npython3 -I obb.py check covering-17-7-4-6 CANDIDATE ..."
}
```

Remove one block and the same call returns `"verdict": "not_certified"` with the checker's reason
(`some 6-subset meets every block in fewer than 4 points`).

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

Without an MCP client, the same check from the command line (JSON out; exit status 0 certified, 1 not certified, 2
no verdict or an error):

```sh
quantavane-mcp check covering-17-7-4-6 design.txt
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
  decimals; for C16 the lower end of a rigorous enclosure. `exactness` in each result says which.
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

- **A snapshot.** The data is from the commits and dates in `quantavane://about` (benchmark 6c6c027 of 7 Nov 2026;
  open data of 7 Nov 2026; replays b892ccb of 8 Nov 2026). Best known values move: check the source page before
  claiming a record. A newer release of this package brings newer data.
- **Routing instances are not bundled.** The 14 vehicle routing problems need CVRPLIB's instance files (third-party
  data). Run `fetch.sh` in a clone of the benchmark and set `QUANTAVANE_MCP_INSTANCES` to its `instances/` folder;
  each file is checked against the SHA-256 the benchmark pins before it is used. The server never downloads them.
- **Ramsey.** Needs a C compiler; the checker is compiled once into a cache folder. Colourings have at most 2048
  vertices.
- **Time.** The default timeout is 120 s. Most checks take under a second; the Turán (42a) and Bohr radius (59a)
  checkers can take a minute or more on large certificates.
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
- A Ramsey file with rows longer than the C checker's 2048 columns is rejected before the checker runs (the C
  checker would also reject it, after writing past its matrix for widths 2049 to 2055).

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

Code: MIT ([LICENSE](LICENSE)). Bundled data (problem files, reference certificates, verified results, the replay
index): CC BY 4.0 ([LICENSE-DATA.md](LICENSE-DATA.md)). The benchmark's checkers are MIT, as in the benchmark.

## Citation

`cite(target="server")`, or:

```bibtex
@software{quantavane-mcp,
  author  = {Canli, Arhan},
  title   = {quantavane-mcp: an MCP server for open problems with exact checkers},
  year    = {2026},
  version = {0.1.0},
  url     = {https://github.com/arhancanli/quantavane-mcp}
}
```

To cite the benchmark, a problem, a result, the dataset or a replay, use `cite` with that target; citing a problem
also gives the source of its best known value, which should be cited as well. See also [CITATION.cff](CITATION.cff).

Quantavane: https://quantavane.com. Questions and corrections: open an issue.
