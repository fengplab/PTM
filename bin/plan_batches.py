#!/usr/bin/env python3
"""Group PRIDE datasets into download/process batches that fit a BeeGFS budget.

A batch is downloaded, converted, searched, its results published to NFS, and
its raw/intermediate files deleted before the next batch starts. So the peak
BeeGFS use is the largest single batch, not the sum of all batches.

Estimated peak for a dataset = raw_bytes * footprint_factor.
  footprint_factor covers raw files + converted spectra + search-engine caches
  + work-directory intermediates. The default (4.0) is a conservative GUESS,
  # UNVERIFIED: not measured on these data. Re-measure with `du` after batch 1
  and re-plan with the observed factor.

Budget = available_bytes * (1 - headroom). available_bytes must be what is
actually free to THIS project inside your 5 TB BeeGFS cap, after other projects.

Packing: first-fit decreasing by estimated peak. Datasets are never split across
batches (FDR is controlled per dataset search). A dataset whose own estimate
exceeds the budget is reported as OVERSIZE and the script exits 2.

Inputs : dataset_summary.tsv and manifest.tsv from fetch_manifest.py
Outputs: batch_plan.tsv, batches/batch_NN.files.tsv (RAW files for that batch)
"""
import argparse
import csv
import os
import sys

TB = 1e12


def log(msg):
    sys.stderr.write("[plan_batches] %s\n" % msg)


def read_tsv(path):
    with open(path) as fh:
        return list(csv.DictReader(fh, delimiter="\t"))


def pack(items, budget):
    """items: list of (accession, est_bytes). Returns (batches, oversize)."""
    batches, oversize = [], []
    for acc, est in sorted(items, key=lambda x: (-x[1], x[0])):
        if est > budget:
            oversize.append((acc, est))
            continue
        for b in batches:
            if b["used"] + est <= budget:
                b["members"].append((acc, est))
                b["used"] += est
                break
        else:
            batches.append({"members": [(acc, est)], "used": est})
    return batches, oversize


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--summary", required=True)
    ap.add_argument("--manifest", required=True)
    ap.add_argument("--available-tb", type=float, required=True,
                    help="decimal TB free for this project on BeeGFS right now")
    ap.add_argument("--headroom", type=float, default=0.15,
                    help="fraction of the budget kept free (default 0.15)")
    ap.add_argument("--footprint-factor", type=float, default=4.0)
    ap.add_argument("--outdir", required=True)
    a = ap.parse_args(argv)

    if not (0 <= a.headroom < 1) or a.footprint_factor < 1 or a.available_tb <= 0:
        raise SystemExit("invalid --headroom/--footprint-factor/--available-tb")
    budget = a.available_tb * TB * (1 - a.headroom)

    summary = read_tsv(a.summary)
    bad = [r["accession"] for r in summary if r["status"] not in ("OK",)]
    usable = [r for r in summary if r["status"] == "OK"]
    if bad:
        log("excluded (status not OK, fix or decide first): %s" % ", ".join(bad))
    items = [(r["accession"], int(r["raw_bytes"]) * a.footprint_factor) for r in usable]
    batches, oversize = pack(items, budget)

    manifest = [r for r in read_tsv(a.manifest) if r["category"] == "RAW"]
    os.makedirs(os.path.join(a.outdir, "batches"), exist_ok=True)

    plan_rows, n_files_out = [], 0
    for i, b in enumerate(batches, 1):
        accs = set(acc for acc, _ in b["members"])
        files = [r for r in manifest if r["accession"] in accs]
        n_files_out += len(files)
        path = os.path.join(a.outdir, "batches", "batch_%02d.files.tsv" % i)
        with open(path, "w") as fh:
            cols = ["accession", "file_name", "size_bytes", "md5", "ftp_url"]
            fh.write("\t".join(cols) + "\n")
            for r in files:
                fh.write("\t".join(r[c] for c in cols) + "\n")
        for acc, est in b["members"]:
            raw = next(int(r["raw_bytes"]) for r in usable if r["accession"] == acc)
            plan_rows.append(["%02d" % i, acc, "%.3f" % (raw / TB), "%.3f" % (est / TB),
                              "%.3f" % (b["used"] / TB)])
    for acc, est in oversize:
        raw = next(int(r["raw_bytes"]) for r in usable if r["accession"] == acc)
        plan_rows.append(["OVERSIZE", acc, "%.3f" % (raw / TB), "%.3f" % (est / TB), "NA"])
    for acc in bad:
        plan_rows.append(["EXCLUDED", acc, "NA", "NA", "NA"])

    with open(os.path.join(a.outdir, "batch_plan.tsv"), "w") as fh:
        fh.write("batch\taccession\traw_TB\test_peak_TB\tbatch_peak_TB\n")
        for row in plan_rows:
            fh.write("\t".join(row) + "\n")

    n_raw_in = sum(int(r["n_raw"]) for r in usable)
    planned = set(acc for b in batches for acc, _ in b["members"])
    n_raw_planned = sum(int(r["n_raw"]) for r in usable if r["accession"] in planned)
    log("budget %.2f TB (available %.2f TB, headroom %.0f%%, factor %.1f)"
        % (budget / TB, a.available_tb, a.headroom * 100, a.footprint_factor))
    log("RAW files: %d in usable datasets, %d placed in %d batches, %d in OVERSIZE datasets"
        % (n_raw_in, n_files_out, len(batches), n_raw_in - n_raw_planned))
    if n_files_out != n_raw_planned:
        log("ERROR: file count mismatch between manifest and summary")
        return 1
    if oversize:
        log("OVERSIZE (needs a decision): %s" % ", ".join(acc for acc, _ in oversize))
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
