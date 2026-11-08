#!/usr/bin/env python3
"""Rebuild the data bundled with quantavane-mcp from our three public sources, each read at a pinned git commit.

  python3 -I scripts/sync_data.py --open-data DIR [--benchmark DIR] [--benchmark-ref REF] [--replays DIR]
                                  [--replays-ref REF] [--check]

--open-data (or QUANTAVANE_OPEN_DATA) is the folder holding the open dataset's files, as published on Kaggle.

Sources (all Quantavane's own):
- the Open Problems Benchmark (github.com/arhancanli/quantavane-benchmark): problems/, checkers/, refs/, README.md and
  LICENSE, copied byte for byte with `git show REF:PATH`, plus the CVRPLIB instance hashes from fetch.sh and the
  expected verdicts of test.sh;
- the verified-results open data (the Kaggle dataset arhancanli12/quantavane-verified-results): records.json,
  totals.json, README.md, the ca-tools rows and the first-entry exclusions, copied as they are;
  covering_array_entries.csv (206,384 rows, 18 MB) is stored as runs of consecutive k with identical columns, and the
  expansion is checked to reproduce the original file byte for byte;
- our replays (github.com/arhancanli/quantavane-replays): an index of the README sections at REF, plus the replay
  folders the README does not describe yet.

Writes src/quantavane_mcp/data/ and its MANIFEST.json (the SHA-256 of every file and the commits read). With --check
it rebuilds into a temporary folder and exits 1 if anything differs from the bundled data. Standard library only."""
import argparse
import ast
import csv
import datetime as dt
import filecmp
import hashlib
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile

HOME = os.path.expanduser("~")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "src", "quantavane_mcp", "data")
BENCHMARK_URL = "https://github.com/arhancanli/quantavane-benchmark"
REPLAYS_URL = "https://github.com/arhancanli/quantavane-replays"
TAO_REPO = "teorth/optimizationproblems"


def git(repo, *args):
    return subprocess.run(["git", "-C", repo, *args], check=True, capture_output=True).stdout


def git_text(repo, *args):
    return git(repo, *args).decode("utf-8").strip()


def commit_time(repo, commit):
    """The commit time in UTC, ISO 8601."""
    stamp = int(git_text(repo, "log", "-1", "--format=%ct", commit))
    return dt.datetime.fromtimestamp(stamp, dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def write(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as f:
        f.write(data if isinstance(data, bytes) else data.encode("utf-8"))


def dump_json(obj):
    return json.dumps(obj, indent=1, ensure_ascii=False, sort_keys=True) + "\n"


# ---------------------------------------------------------------------------------------------------- benchmark


def sync_benchmark(repo, ref, out):
    commit = git_text(repo, "rev-parse", ref)
    files = git_text(repo, "ls-tree", "-r", "--name-only", commit).splitlines()
    keep = [f for f in files if f in ("README.md", "LICENSE")
            or re.fullmatch(r"problems/[^/]+\.json", f)
            or re.fullmatch(r"checkers/[^/]+\.(py|c)", f)
            or f.startswith("refs/")]
    for f in keep:
        write(os.path.join(out, "benchmark", f), git(repo, "show", f"{commit}:{f}"))

    # the date each problem file was last written (its best known value was read then, or on the date it states)
    dates = {}
    log = git_text(repo, "log", "--format=@%cs", "--name-only", commit, "--", "problems")
    day = None
    for line in log.splitlines():
        if line.startswith("@"):
            day = line[1:]
        elif line.startswith("problems/") and line not in dates:
            dates[line] = day
    problem_dates = {}
    for f in keep:
        if f.startswith("problems/"):
            pid = json.loads(git(repo, "show", f"{commit}:{f}"))["id"]
            problem_dates[pid] = dates[f]

    # CVRPLIB instances: fetched by fetch.sh, never bundled; their SHA-256 lets the server verify a local copy
    instances = {}
    for line in git(repo, "show", f"{commit}:fetch.sh").decode().splitlines():
        m = re.match(r"^slow (\S+\.vrp) (\S+) ([0-9a-f]{64})$", line.strip())
        if m:
            instances[m.group(1)] = {"url": m.group(2), "sha256": m.group(3)}

    # expected verdicts on the reference submissions (test.sh): ours are bundled, the others are fetched by fetch.sh
    expected, external = [], []
    for line in git(repo, "show", f"{commit}:test.sh").decode().splitlines():
        m = re.match(r'^t (\S+) (\S+) "([^"]*)"$', line.strip())
        if not m:
            continue
        pid, path, verdicts = m.group(1), m.group(2), [v for v in m.group(3).split(",") if v]
        row = {"problem": pid, "file": os.path.basename(path), "expected": verdicts}
        (expected if path.startswith("refs/") else external).append(row)

    meta = {
        "repository": BENCHMARK_URL,
        "commit": commit,
        "commit_date": commit_time(repo, commit),
        "problem_count": len(problem_dates),
        "problem_file_dates": problem_dates,
        "cvrplib_instances": instances,
        "reference_expected": expected,
        "external_expected": external,
    }
    write(os.path.join(out, "benchmark", "meta.json"), dump_json(meta))
    return {"repository": BENCHMARK_URL, "commit": commit, "commit_date": meta["commit_date"],
            "files": len(keep), "problems": len(problem_dates)}


# ---------------------------------------------------------------------------------------------------- open data

RUN_COLUMNS = ["t", "v", "k_from", "k_to", "N", "previous_N", "family_rows_k", "source"]


def covering_array_runs(raw):
    """Runs of consecutive k whose other columns agree; returns (header, runs). Lossless: see expand_runs."""
    rows = list(csv.reader(io.StringIO(raw.decode("utf-8"))))
    header, body = rows[0], rows[1:]
    assert header == ["t", "v", "k", "N", "previous_N", "family_rows_k", "source"], header
    runs = []
    for t, v, k, n, prev, fam, src in body:
        k = int(k)
        last = runs[-1] if runs else None
        if last and (last[0], last[1], last[4], last[5], last[6], last[7]) == (t, v, n, prev, fam, src) \
                and last[3] == k - 1:
            last[3] = k
        else:
            runs.append([t, v, k, k, n, prev, fam, src])
    return header, runs


def expand_runs(header, runs):
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\r\n")
    w.writerow(header)
    for t, v, k0, k1, n, prev, fam, src in runs:
        for k in range(int(k0), int(k1) + 1):
            w.writerow([t, v, k, n, prev, fam, src])
    return buf.getvalue().encode("utf-8")


def sync_open_data(folder, out):
    files = ["README.md", "records.json", "totals.json", "covering_arrays_catools_rows.csv",
             "first_entries_not_best.csv"]
    for f in files:
        with open(os.path.join(folder, f), "rb") as fh:
            write(os.path.join(out, "open_data", f), fh.read())
    with open(os.path.join(folder, "covering_array_entries.csv"), "rb") as fh:
        raw = fh.read()
    header, runs = covering_array_runs(raw)
    # the original file uses csv's default "\r\n" line ends; the expansion must give the same bytes
    if expand_runs(header, runs) != raw:
        sys.exit("covering_array_entries.csv: the runs do not reproduce the file byte for byte; nothing written")
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(RUN_COLUMNS)
    w.writerows(runs)
    write(os.path.join(out, "open_data", "covering_array_entries_runs.csv"), buf.getvalue())

    try:   # the files must be committed where they are kept, so the bundle matches a recorded version
        dirty = git_text(folder, "status", "--porcelain", "--", ".")
    except subprocess.CalledProcessError:
        dirty = ""
    if dirty:
        sys.exit(f"{folder} has uncommitted changes; commit them (or publish the dataset) first; nothing written")
    totals = json.load(open(os.path.join(folder, "totals.json")))
    return {
        "dataset": "https://www.kaggle.com/datasets/arhancanli12/quantavane-verified-results",
        "date": totals["date"],
        "covering_array_entries_csv": {"rows": len(raw.splitlines()) - 1, "sha256": sha256(raw), "bytes": len(raw),
                                       "runs": len(runs)},
    }


# ---------------------------------------------------------------------------------------------------- replays

MONTHS = "January February March April May June July August September October November December".split()


def github_anchor(heading, seen):
    """GitHub's heading anchor: lower case, punctuation removed, spaces to hyphens, repeats numbered."""
    s = re.sub(r"[^\w\- ]", "", heading.strip().lower(), flags=re.UNICODE).replace(" ", "-")
    n = seen.get(s, 0)
    seen[s] = n + 1
    return s if n == 0 else f"{s}-{n}"


def iso_dates(text):
    out = []
    for d1, d2, mon, year in re.findall(r"\((\d{1,2})(?: to (\d{1,2}))? (" + "|".join(MONTHS) + r") (\d{4})\)", text):
        out.append(f"{year}-{MONTHS.index(mon) + 1:02d}-{int(d2 or d1):02d}")
    return out


def constants_in(heading):
    """Constant ids named in a heading, as the optimization constants repository numbers its pages (42a, 1c, 89b):
    every C-prefixed id (C42, C1a), or a bare id that opens the heading (3b:)."""
    head = heading.split("(")[0]
    found = []
    toks = re.findall(r"\bC(\d{1,3}[a-z]{0,2})\b", head)
    m = re.match(r"^(\d{1,3}[a-z]{1,2}):", head)
    for tok in ([m.group(1)] if m else []) + toks:
        if tok not in found:
            found.append(tok)
    return found


def asterisk_rows(text):
    """Rows of ASTERISK_INDEX.md: one per starred bound, with its class (a)-(d) and the pull requests it names."""
    rows, cls = [], None
    for line in text.splitlines():
        h = re.match(r"^## \(([a-d])\)", line)
        if h:
            cls = h.group(1)
            continue
        if line.startswith("## "):
            cls = None
        m = re.match(r"^\| \[(\w+)\]\([^)]*\) ([^|]+?) \| ([^|]*) \|", line)
        if cls and m:
            prs, _ = row_info(line)
            rows.append({"constant": m.group(1), "tag": m.group(2).strip(), "bound": m.group(3).strip(),
                         "class": cls, "prs": prs})
    return rows


def row_info(line):
    prs = sorted({int(x) for x in re.findall(r"optimizationproblems/pull/(\d+)", line)}
                 | {int(x) for x in re.findall(r"(?<![\w/])#(\d{2,4})\b", line)})
    tags = sorted(set(re.findall(r"\[([A-Z][A-Za-z]*\d{2,4}[a-z]?)\]", line)))
    return prs, tags


def sync_replays(repo, ref, out):
    commit = git_text(repo, "rev-parse", ref)
    text = git(repo, "show", f"{commit}:README.md").decode("utf-8")
    tree = git_text(repo, "ls-tree", "-r", "--name-only", commit).splitlines()
    folders = sorted({f.split("/")[0] for f in tree if "/" in f})
    parts = re.split(r"(?m)^## ", text)
    sections, anchors = [], {}
    for part in parts[1:]:
        heading, _, body = part.partition("\n")
        anchor = github_anchor(heading, anchors)
        if heading.strip() == "Reproduce":
            continue
        if heading.strip() == "Method" and sections:   # the method of the C1a/C1c/C1d replays
            sections[-1]["method"] = body.strip()
            if not sections[-1]["summary"]:            # that section opens with its table: its method summarises it
                bullets = [" ".join(x.strip() for x in b.splitlines()) for b in ("\n" + body.strip()).split("\n- ")[1:]]
                first = bullets[0] if bullets else ""
                sections[-1]["summary"] = next((b for b in bullets if "exact integers" in b), first)
            continue
        paths = re.findall(r"`([\w\-]+)/[\w\-./]*`", body)
        sec_folders = []
        for p in paths:
            if p in folders and p not in sec_folders:
                sec_folders.append(p)
        if not sec_folders and re.search(r"\bC1[acd]\b|C1a, C1c", heading):
            sec_folders = ["."]                          # the C1a/C1c/C1d replays sit at the top level
        lines = body.strip().splitlines()
        summary_lines = []
        for line in lines:
            if line.startswith("|") or (summary_lines and not line.strip()):
                break
            summary_lines.append(line)
        summary = " ".join(x.strip() for x in summary_lines)
        rows = []
        for line in lines:
            header = re.match(r"^\|\s*-", line) or re.match(r"^\| (Constant|Check|Row) \|", line)
            if line.startswith("|") and not header:
                prs, tags = row_info(line)
                rows.append({"text": line.strip(), "prs": prs, "tags": tags})
        prs, tags = row_info(body)
        files = {}
        for folder in sec_folders:
            prefix = "" if folder == "." else folder + "/"
            names = [f[len(prefix):] for f in tree if f.startswith(prefix)
                     and (folder != "." or "/" not in f or f.startswith("results/"))]
            files[folder] = {
                "checks": sorted(n for n in names if "/" not in n and re.search(r"\.(py|c)$", n)),
                "results": sorted(n for n in names if n.startswith("results/"))[:40],
                "fetch": "fetch.sh" in names,
                "run_all": "run_all.sh" in names,
            }
        sections.append({
            "kind": "section",
            "heading": heading.strip(),
            "anchor": anchor,
            "dates": iso_dates(heading),
            "constants": constants_in(heading),
            "prs": prs,
            "tags": tags,
            "folders": sec_folders,
            "files": files,
            "summary": summary,
            "rows": rows,
        })
    sections += folder_entries(repo, commit, tree, {f for s in sections for f in s["folders"]})
    star = git(repo, "show", f"{commit}:ASTERISK_INDEX.md").decode("utf-8") if "ASTERISK_INDEX.md" in tree else ""
    snap = re.search(r"^Snapshot: (.*)$", star, re.M)
    index = {
        "repository": REPLAYS_URL,
        "commit": commit,
        "commit_date": commit_time(repo, commit),
        "about": re.sub(r"\s+", " ", text.split("\n## ")[0].split("\n", 1)[1].split("\n\n")[0]).strip(),
        "asterisk_index": {
            "file": "ASTERISK_INDEX.md",
            "snapshot": re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", snap.group(1)) if snap else None,
            "rows": asterisk_rows(star),
        },
        "reproduce": "./fetch.sh then ./run_all.sh in the folder (fetch.sh downloads the certificates at pinned "
                     "commits and checks every SHA-256; Python 3.9+, standard library only)",
        "tao_repository": "https://github.com/" + TAO_REPO,
        "sections": sections,
    }
    write(os.path.join(out, "replays", "index.json"), dump_json(index))
    return {"repository": REPLAYS_URL, "commit": commit, "commit_date": index["commit_date"],
            "sections": sum(s["kind"] == "section" for s in sections),
            "folders_without_section": sum(s["kind"] == "folder" for s in sections)}


def _header_comment(text):
    """The comment block that opens a shell script (after the #! line)."""
    out = []
    for line in text.splitlines()[1 if text.startswith("#!") else 0:]:
        if not line.startswith("#"):
            break
        out.append(line.lstrip("#").strip())
    return " ".join(x for x in out if x)


def _program_doc(name, text):
    if name.endswith(".py"):
        try:
            return ast.get_docstring(ast.parse(text)) or ""
        except SyntaxError:
            return ""
    m = re.match(r"\s*/\*(.*?)\*/", text, re.S)
    return m.group(1).strip() if m else ""


def folder_entries(repo, commit, tree, covered):
    """Replay folders the README does not describe yet (it is written after the replay): an entry from the folder's
    own run_all.sh and fetch.sh header comments and its checking programs' documentation, all read, none run."""
    out = []
    folders = sorted({f.split("/")[0] for f in tree if "/" in f})
    for folder in folders:
        m = re.fullmatch(r"c(\d{1,3}[a-z]{0,2})", folder)
        if not m or folder in covered:
            continue
        names = [f[len(folder) + 1:] for f in tree if f.startswith(folder + "/")]

        def show(name, folder=folder):
            return git(repo, "show", f"{commit}:{folder}/{name}").decode("utf-8", "replace")
        run_all = _header_comment(show("run_all.sh")) if "run_all.sh" in names else ""
        fetch = _header_comment(show("fetch.sh")) if "fetch.sh" in names else ""
        checks = sorted(n for n in names if "/" not in n and re.search(r"\.(py|c)$", n))
        docs = [_program_doc(n, show(n)) for n in checks]
        prs, tags = row_info(" ".join([run_all, fetch] + docs))
        summary = run_all or (docs[0].split("\n\n")[0].replace("\n", " ") if docs else "")
        day = git_text(repo, "log", "-1", "--format=%cs", commit, "--", folder)
        out.append({
            "kind": "folder",
            "heading": f"C{m.group(1)}: replay in {folder}/ ({day}; the README section is not written yet)",
            "anchor": None,
            "dates": [day],
            "constants": [m.group(1)],
            "prs": prs,
            "tags": tags,
            "folders": [folder],
            "files": {folder: {"checks": checks, "results": sorted(n for n in names if n.startswith("results/"))[:40],
                               "fetch": "fetch.sh" in names, "run_all": "run_all.sh" in names}},
            "summary": summary,
            "rows": [],
        })
    return out


# ---------------------------------------------------------------------------------------------------- main


def build(args, out):
    if os.path.exists(out):
        shutil.rmtree(out)
    os.makedirs(out)
    sources = {
        "benchmark": sync_benchmark(args.benchmark, args.benchmark_ref, out),
        "open_data": sync_open_data(args.open_data, out),
        "replays": sync_replays(args.replays, args.replays_ref, out),
    }
    files = {}
    for dirpath, _, names in os.walk(out):
        for n in names:
            p = os.path.join(dirpath, n)
            with open(p, "rb") as fh:
                data = fh.read()
            files[os.path.relpath(p, out).replace(os.sep, "/")] = {"sha256": sha256(data), "bytes": len(data)}
    manifest = {"schema": 1, "sources": sources, "files": dict(sorted(files.items()))}
    write(os.path.join(out, "MANIFEST.json"), dump_json(manifest))
    return manifest


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--benchmark", default=os.path.join(HOME, "quantavane-benchmark"))
    ap.add_argument("--benchmark-ref", default="origin/main")
    ap.add_argument("--replays", default=os.path.join(HOME, "quantavane-replays"))
    ap.add_argument("--replays-ref", default="origin/main")
    ap.add_argument("--open-data", default=os.environ.get("QUANTAVANE_OPEN_DATA"),
                    help="folder with the open dataset's files (default: $QUANTAVANE_OPEN_DATA)")
    ap.add_argument("--check", action="store_true", help="rebuild into a temporary folder and compare")
    args = ap.parse_args()
    if not args.open_data:
        ap.error("--open-data (or QUANTAVANE_OPEN_DATA) is required")
    if args.check:
        with tempfile.TemporaryDirectory() as tmp:
            target = os.path.join(tmp, "data")
            build(args, target)
            cmp = filecmp.dircmp(OUT, target)
            diffs = []

            def walk(c, prefix=""):
                diffs.extend(prefix + x for x in c.left_only + c.right_only + c.diff_files)
                for name, sub in c.subdirs.items():
                    walk(sub, prefix + name + "/")
            walk(cmp)
            if diffs:
                print("differs from the sources:", ", ".join(sorted(diffs)[:20]))
                return 1
            print("bundled data matches the sources")
            return 0
    m = build(args, OUT)
    total = sum(f["bytes"] for f in m["files"].values())
    print(f"wrote {len(m['files'])} files ({total / 1e6:.2f} MB) to {os.path.relpath(OUT, ROOT)}")
    for k, v in m["sources"].items():
        print(f"  {k}: " + ", ".join(f"{a}={b}" for a, b in v.items() if not isinstance(b, dict)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
