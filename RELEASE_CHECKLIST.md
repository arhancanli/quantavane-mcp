# Release checklist

A release makes the code and its words public, so every step marked **owner** is the owner's. Nothing here is
published by a script without the owner running it.

## Before the release

1. **Words** (owner): read and approve the public text: `README.md`, `CHANGELOG.md`, `LICENSE-DATA.md`,
   `CITATION.cff`, the server instructions, tool descriptions and prompts in `src/quantavane_mcp/server.py`, the
   claim-check wording in `src/quantavane_mcp/claims.py` (verdicts, red-control names, packet text), the second
   checkers' messages in `src/quantavane_mcp/independent/second_check.py`, and the field descriptions in
   `src/quantavane_mcp/models.py`.
2. **Data licences** (owner question): `LICENSE-DATA.md` follows the sources as they read today: the benchmark's
   files and the replay index MIT (the benchmark's README and LICENSE; the replays' LICENSE), the verified results
   CC BY 4.0 (the dataset's README). If the problem files and reference certificates should be CC BY 4.0 like the
   dataset, the benchmark's README must say so first; then `LICENSE-DATA.md`, the README's Licence section and the
   `cite` notes follow.
3. **Data at the published commits**: every source must be pushed first (the sync reads `origin/main`; the bundle
   of 0.2.0 holds benchmark v2.1 with Prestige 100 and the Originals, commit 504492c, and replays 57988b0, both pushed
   on 9 Nov; the open data of 7 Nov is unchanged), then
   - `python3 -I scripts/sync_data.py --open-data DIR` (DIR: the folder of the open dataset's published files),
   - `python3 -I scripts/sync_data.py --open-data DIR --check` prints `bundled data matches the sources`,
   - update the snapshot line in the README's Limits section (benchmark, open data and replays commits and dates),
   - commit.
4. **Tests**: `pytest` (all pass; the skips are the opt-in parity and routing tests), then the opt-in ones:
   - in a benchmark checkout, `./fetch.sh` and `python3 -I tests/sample_cells.py` (it writes the sampled cells'
     objects and red controls to `certs/samples/`), then
     `QUANTAVANE_MCP_TEST_BENCHMARK=<checkout> pytest tests/test_parity_obb.py` (same exact values and verdicts as
     `obb.py` for every certificate of `test.sh` and every sampled cell; `obb.py sample` and `obb.py show` give the
     same cells, written out the same way; the Originals' certificates too; and the claim checks' second checkers
     give obb.py's value on every certificate within their limits),
   - `QUANTAVANE_MCP_TEST_INSTANCES=<checkout>/instances pytest -k routing` (the 14 routing references).
5. **Static checks**: `ruff check --line-length 120 --exclude src/quantavane_mcp/data src tests scripts` and
   `mypy src/quantavane_mcp --exclude src/quantavane_mcp/data/`.
6. **Version**: `__version__` in `src/quantavane_mcp/__init__.py` and `version` in `CITATION.cff` agree; the README
   citation block gives the same version.

## Build and check the package

```sh
rm -rf dist && uv build
uvx twine check dist/*
unzip -l dist/quantavane_mcp-*.whl | grep -c quantavane_mcp/data/   # every data file of MANIFEST.json, and itself
uv venv /tmp/qv-wheel && uv pip install --python /tmp/qv-wheel/bin/python dist/quantavane_mcp-*.whl
/tmp/qv-wheel/bin/quantavane-mcp selftest                           # "selftest: ok"
```

## Publish (owner)

1. GitHub: create the repository and push the signed commits and a signed tag `v<version>`.
2. PyPI: `uv publish` with a PyPI API token for the project `quantavane-mcp` (the name was free on 8 Nov 2026).
3. Check from a clean machine or folder: `uvx quantavane-mcp --version`, `uvx quantavane-mcp selftest`, and
   `claude mcp add quantavane -- uvx quantavane-mcp` followed by one `check_candidate` call.
4. The CI workflow (`.github/workflows/test.yml`) runs on the first push: Linux and macOS, Python 3.10 to 3.14. It
   is the first run of the Linux memory cap (RLIMIT_AS) and of Python 3.10 and 3.11; fix anything it finds before
   announcing.

## After the release (optional, owner)

- The MCP Registry: `mcp-publisher init` then `mcp-publisher publish` (the README carries the
  `mcp-name: io.github.arhancanli/quantavane-mcp` line the registry checks for PyPI packages).
- A line in the benchmark's README pointing to the server.

## Known gaps, to close in later versions

- The server uses the MCP Python SDK 1.x (`FastMCP`, `mcp>=1.30,<2`); SDK 2.x renames it `MCPServer`.
- Windows: no memory cap, so checks are refused unless `QUANTAVANE_MCP_ALLOW_UNCAPPED=1`.
- Routing problems and scheduling cells need instance files (CVRPLIB's, the scheduling sets'), which the server
  never downloads; only CVRPLIB's are pinned by SHA-256.
- Replays published after a release appear in the next release; replay folders whose README section is not written
  yet are indexed from their own scripts' comments and documentation.
- The training-gym hook (`QUANTAVANE_MCP_GYM`) is tested with a stand-in backend only.
- Claim checks: no second checker yet for the analytic constants (1a, 1c, 1d, 16a, 42a, 59a, 68a), routing,
  scheduling, the Mona Lisa tour, Erdős #107 and the Originals, so their claims say NOT VERIFIED; the second checkers
  are plain Python, so the largest objects (our 17,600-vertex cage, very large designs and codes) are past their
  limits and get no verdict. The keeper is never re-read (offline).
