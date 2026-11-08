# Data licence

The data bundled in `src/quantavane_mcp/data/` is Quantavane's own and is licensed under the Creative Commons
Attribution 4.0 International licence (CC BY 4.0, https://creativecommons.org/licenses/by/4.0/). Attribute it to
"Arhan Canli (Quantavane)" with a link to its source:

- `data/benchmark/`: the Open Problems Benchmark, https://github.com/arhancanli/quantavane-benchmark (the commit is in
  `data/MANIFEST.json`): the problem files and the reference certificates. Its checkers (`data/benchmark/checkers/`)
  are code under the MIT licence in `LICENSE`.
- `data/open_data/`: Quantavane verified results, https://www.kaggle.com/datasets/arhancanli12/quantavane-verified-results
  (`covering_array_entries_runs.csv` holds the dataset's `covering_array_entries.csv` as runs of consecutive k; the
  expansion is byte for byte the published file).
- `data/replays/index.json`: an index of https://github.com/arhancanli/quantavane-replays.

Best known values that the problem files credit to other people are theirs: cite the source each problem file names.
The CVRPLIB instance files are not bundled.

The server's code is under the MIT licence (`LICENSE`).
