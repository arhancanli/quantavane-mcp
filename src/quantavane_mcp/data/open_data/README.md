# Quantavane verified results (7 November 2026)

Results found by Quantavane's search programs, each checked exactly by a separate program and sent to the public table
that keeps the problem. A result counts as verified only once that table lists it. On 7 November 2026: 1,342,778 verified results, 274,682 records (better than the best known before) and 1,068,096 first entries (sizes the table had
no entry for), shown apart; 11,904 further cells are not counted because a published construction is smaller there.

## Files
- `records.csv`, `records.json`: every Quantavane result with its status (listed, sent, in the next batch), the value
  before ours, the date and a link: covering array families, spherical codes, covering designs, constant weight codes,
  linear and quantum codes, Ramsey bounds, vehicle-routing solutions, project-scheduling results and prime gaps.
- `covering_array_entries.csv`: the 206,384 entries of the ca-tools covering array table
  (github.com/chrispbsmolen/ca-tools) where our families give the smallest known size. Columns: `t` (strength), `v`
  (symbols), `k` (columns), `N` (rows, our size), `previous_N` (the table's best size without our rows),
  `family_rows_k` (the column count of our listed family row that gives this entry), `source`.
- `covering_arrays_catools_rows.csv`: the 217 rows of ca-tools' live table that credit us (strength 3: 75, of which 34
  past 10,000 columns, the first entries; strength 4: 92; 5: 31; 6: 19), as the table lists them.
- `first_entries_not_best.csv`: the width ranges where a published construction (Shokri and Moura 2025; the Roux-type
  construction of Colbourn, Martirosyan, Tran Van Trung and Walker) is smaller than ours, so those cells are not ours.
- `totals.json`: the counts above.

## How every result is checked
Each family or object is checked by an exact program written apart from the search (and, for covering arrays, again
by the table's own checker before it is listed). Covering array families and their check logs:
github.com/arhancanli/quantavane-covering-arrays; covering designs: github.com/arhancanli/quantavane-covering-records;
every result page with its check: quantavane.com/results/.

## License and citation
CC BY 4.0. Cite: Arhan Canli (Quantavane), New upper bounds for covering array numbers from partly cyclic covering
perfect hash families, 2026, doi:10.5281/zenodo.23839216, and quantavane.com/results/.
