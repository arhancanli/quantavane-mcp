# Release checklist

A release makes the code and its words public, so every step marked **owner** is the owner's. Nothing here is
published by a script without the owner running it.

## Before the release

1. **Words** (owner): read and approve the public text: `README.md`, `LICENSE-DATA.md`, `CITATION.cff`, the server
   instructions, tool descriptions and prompts in `src/quantavane_mcp/server.py`, and the field descriptions in
   `src/quantavane_mcp/models.py`.
2. **Licence of the benchmark's data** (owner decision): the bundled problem files and reference certificates are
   declared CC BY 4.0 in `LICENSE-DATA.md`; the benchmark repository states MIT for its code and nothing yet for its
   data. Add the same CC BY 4.0 line to the benchmark's README, or change `LICENSE-DATA.md`.
3. **Data at the published commits**: every source must be pushed first (the sync reads `origin/main`), then
   - `python3 -I scripts/sync_data.py --open-data DIR` (DIR: the folder of the open dataset's published files),
   - `python3 -I scripts/sync_data.py --open-data DIR --check` prints `bundled data matches the sources`,
   - update the snapshot line in the README's Limits section (benchmark, open data and replays commits and dates),
   - commit.
4. **Tests**: `pytest` (all pass; 81 skips are the opt-in parity and routing tests), then the opt-in ones:
   - in a benchmark checkout, `./fetch.sh`, then
     `QUANTAVANE_MCP_TEST_BENCHMARK=<checkout> pytest tests/test_parity_obb.py` (same exact values and verdicts as
     `obb.py` for every certificate of `test.sh`),
   - `QUANTAVANE_MCP_TEST_INSTANCES=<checkout>/instances pytest -k routing` (the 14 routing references).
5. **Static checks**: `ruff check --line-length 120 --exclude src/quantavane_mcp/data src tests scripts` and
   `mypy src/quantavane_mcp --exclude src/quantavane_mcp/data/`.
6. **Version**: `__version__` in `src/quantavane_mcp/__init__.py` and `version` in `CITATION.cff` agree; the README
   citation block gives the same version.

## Build and check the package

```sh
rm -rf dist && uv build
uvx twine check dist/*
unzip -l dist/quantavane_mcp-*.whl | grep -c quantavane_mcp/data/   # 210: 209 data files and MANIFEST.json
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
- Routing problems need the CVRPLIB instance files, which the server never downloads.
- Replays published after a release appear in the next release; replay folders whose README section is not written
  yet are indexed from their own scripts' comments and documentation.
- The training-gym hook (`QUANTAVANE_MCP_GYM`) is tested with a stand-in backend only.
