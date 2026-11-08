# Data licences

The data bundled in `src/quantavane_mcp/data/` is Quantavane's own. Each part keeps the licence its source states:

- `data/benchmark/`: the Open Problems Benchmark, https://github.com/arhancanli/quantavane-benchmark (the commit is in
  `data/MANIFEST.json`): the problem files, the checkers and the reference certificates. MIT, as the benchmark states
  (its `LICENSE`, copied here as `data/benchmark/LICENSE`).
- `data/replays/index.json`: an index of https://github.com/arhancanli/quantavane-replays. MIT, as that repository
  states (its `LICENSE`).
- `data/open_data/`: Quantavane verified results,
  https://www.kaggle.com/datasets/arhancanli12/quantavane-verified-results. Creative Commons Attribution 4.0
  International (CC BY 4.0, https://creativecommons.org/licenses/by/4.0/), as the dataset's README states: attribute it
  to "Arhan Canli (Quantavane)" with a link to the dataset. `covering_array_entries_runs.csv` holds the dataset's
  `covering_array_entries.csv` as runs of consecutive k; the expansion is byte for byte the published file.

Best known values that the problem files credit to other people are theirs: cite the source each problem file names.
The CVRPLIB instance files are not bundled.

The server's code is under the MIT licence (`LICENSE`).
