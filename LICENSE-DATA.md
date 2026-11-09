# Data licences

The data bundled in `src/quantavane_mcp/data/` keeps the licence its source states:

- `data/benchmark/`: the Open Problems Benchmark, https://github.com/arhancanli/quantavane-benchmark (the commit is in
  `data/MANIFEST.json`): the problem files, the family definitions and cells, the checkers and the reference
  certificates. MIT, as the benchmark states (its `LICENSE`, copied here as `data/benchmark/LICENSE`).
- `data/benchmark/collections/prestige100/`: Quantavane Prestige 100, part of the benchmark. Its index states "data CC
  BY 4.0, checkers MIT": the pages, index and leaderboard are under Creative Commons Attribution 4.0 International
  (attribute them to "Arhan Canli (Quantavane)" with a link to the benchmark); the checkers it names are the
  benchmark's (MIT). The records it lists belong to their holders and are credited to them and to their keepers in
  each entry.
- `data/benchmark/collections/originals/`: the Quantavane Originals, part of the benchmark (MIT, as the benchmark
  states): problem files and pages, checkers, certificates, our own instance files and novelty checks.
- `data/replays/index.json`: an index of https://github.com/arhancanli/quantavane-replays. MIT, as that repository
  states (its `LICENSE`).
- `data/open_data/`: Quantavane verified results,
  https://www.kaggle.com/datasets/arhancanli12/quantavane-verified-results. Creative Commons Attribution 4.0
  International (CC BY 4.0, https://creativecommons.org/licenses/by/4.0/), as the dataset's README states: attribute it
  to "Arhan Canli (Quantavane)" with a link to the dataset. `covering_array_entries_runs.csv` holds the dataset's
  `covering_array_entries.csv` as runs of consecutive k; the expansion is byte for byte the published file.

## Values read from other people's tables

The six families of the benchmark hold best known values read from the tables their keepers maintain, each with the
keeper, the date read, the revision read and, where the table names one, who holds the value. Only values are
stored, with their sources; no keeper's file is included. Credit for every value goes to its holder and its table:

- `constant-weight-code`: A. E. Brouwer, bounds for binary constant weight codes, https://aeb.win.tue.nl/codes/Andw.html
  (read 9 Nov 2026).
- `covering-array`: C. Smolen's ca-tools table, the live successor of C. J. Colbourn's covering array tables,
  https://github.com/chrispbsmolen/ca-tools (read 9 Nov 2026).
- `covering-design`: the Covering Repository, successor of D. Gordon's La Jolla Covering Repository,
  https://www.coveringrepository.com/ (read 8 Nov 2026).
- `linear-code`: M. Grassl, bounds on the minimum distance of linear codes, https://www.codetables.de/ (read 9 Nov
  2026).
- `project-scheduling`: Solutions Update, M. Vanhoucke and J. Coelho, OR&S group, Ghent University,
  http://solutionsupdate.ugent.be/index.php/rcpsp (read 9 Nov 2026).
- `spherical-code`: H. Cohn, table of spherical codes, https://spherical-codes.org/ (read 9 Nov 2026).

The single problems name their sources the same way (`best_known.source` and `best_known.provenance`). The
CVRPLIB instance files, the Mona Lisa TSP instance and the scheduling sets' instance files are not bundled.

The server's code is under the MIT licence (`LICENSE`).
