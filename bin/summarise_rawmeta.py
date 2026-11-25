#!/usr/bin/env python3
"""Summarise ThermoRawFileParser 1.4.5 output into per-file and per-dataset tables.

For every RAW row in the samplesheet the input directory must hold:
  <accession>__<file stem>.metadata.json   from: ThermoRawFileParser.sh -m 0 -f 4 -c ...
  <accession>__<file stem>.query.json      from: ThermoRawFileParser.sh query -n <scans> -b ...

JSON layouts were read from the ThermoRawFileParser v1.4.5 source:
  metadata (Writer/Metadata.cs, MetadataWriter.cs): object with lists
    InstrumentProperties / MsData / ScanSettings of {accession, cvLabel, name, value};
    MS2 dissociation types are ScanSettings entries (e.g. MS:1000422 ... value "HCD").
  query (Query/ProxiSpectrum.cs): list of spectra, each with "attributes":
    [{accession, name, value}], including "ms level" (MS:1000511) and
    "filter string" (MS:1000512).

The MS2 mass analyzer (Orbitrap "FTMS" vs ion trap "ITMS") is not in the metadata,
so it is read from the filter strings of the sampled scans. These decide the
fragment tolerance used in the search, so a file with no sampled MS2 is an error.

Outputs: rawfile_acquisition.tsv (one row per RAW file) and
         dataset_acquisition.tsv (one row per accession).
"""
import argparse
import collections
import csv
import json
import os
import re
import sys

ANALYZERS = ("FTMS", "ITMS", "ASTMS")
ACT_RE = re.compile(r"@([a-z]+)\d")
SPS_RE = re.compile(r"\bsps\b")

FILE_COLS = ["accession", "file_name", "instrument_model", "n_ms1", "n_ms2", "n_ms3",
             "metadata_dissociation", "ms2_analyzer", "ms2_activation", "ms3_analyzer",
             "sps_ms3", "min_charge", "max_charge", "n_sampled_scans", "n_sampled_ms2"]
DATASET_COLS = ["accession", "n_raw", "instrument_models", "ms2_analyzer", "ms2_activation",
                "n_files_with_ms3", "n_files_sps_ms3", "heterogeneous"]


def log(msg):
    sys.stderr.write("[summarise_rawmeta] %s\n" % msg)


def stem(name):
    return name[:-4] if name.lower().endswith(".raw") else os.path.splitext(name)[0]


def terms(obj, key):
    return [t for t in (obj.get(key) or []) if isinstance(t, dict)]


def term_value(obj, key, name, default="NA"):
    for t in terms(obj, key):
        if t.get("name") == name:
            return t.get("value") if t.get("value") not in (None, "") else default
    return default


def parse_metadata(path):
    with open(path) as fh:
        m = json.load(fh)
    dissoc = sorted(set(t.get("value") for t in terms(m, "ScanSettings")
                        if "dissociation" in (t.get("name") or "") and t.get("value")))
    return {
        "instrument_model": term_value(m, "InstrumentProperties", "Thermo Scientific instrument model"),
        "n_ms1": term_value(m, "MsData", "Number of MS1 spectra", "0"),
        "n_ms2": term_value(m, "MsData", "Number of MS2 spectra", "0"),
        "n_ms3": term_value(m, "MsData", "Number of MS3 spectra", "0"),
        "min_charge": term_value(m, "MsData", "MS min charge"),
        "max_charge": term_value(m, "MsData", "MS max charge"),
        "metadata_dissociation": ",".join(dissoc) if dissoc else "NA",
    }


def parse_filter(fs):
    tok = fs.split()
    analyzer = tok[0] if tok and tok[0] in ANALYZERS else "UNKNOWN"
    acts = ACT_RE.findall(fs)
    return analyzer, acts, bool(SPS_RE.search(fs))


def parse_query(path):
    with open(path) as fh:
        spectra = json.load(fh)
    if not isinstance(spectra, list):
        raise ValueError("%s: query output is not a list" % path)
    ms2_an, ms2_act, ms3_an = collections.Counter(), collections.Counter(), collections.Counter()
    sps = False
    n_ms2 = 0
    for s in spectra:
        attrs = {a.get("name"): a.get("value") for a in s.get("attributes") or [] if isinstance(a, dict)}
        fs, lvl = attrs.get("filter string"), attrs.get("ms level")
        if fs is None or lvl is None:
            continue
        analyzer, acts, is_sps = parse_filter(fs)
        if lvl == "2":
            n_ms2 += 1
            ms2_an[analyzer] += 1
            if acts:
                ms2_act[acts[0].upper()] += 1
        elif lvl == "3":
            ms3_an[analyzer] += 1
            sps = sps or is_sps
    fmt = lambda c: ",".join(sorted(c)) if c else "NA"
    return {
        "ms2_analyzer": fmt(ms2_an), "ms2_activation": fmt(ms2_act),
        "ms3_analyzer": fmt(ms3_an), "sps_ms3": "yes" if sps else "no",
        "n_sampled_scans": str(len(spectra)), "n_sampled_ms2": str(n_ms2),
    }


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--samplesheet", required=True)
    ap.add_argument("--indir", required=True)
    ap.add_argument("--outdir", required=True)
    a = ap.parse_args(argv)

    with open(a.samplesheet) as fh:
        raw = [r for r in csv.DictReader(fh) if r["kind"] == "raw"]
    if not raw:
        raise SystemExit("no raw rows in samplesheet")

    rows, errors = [], []
    for r in raw:
        base = os.path.join(a.indir, "%s__%s" % (r["accession"], stem(r["file_name"])))
        mpath, qpath = base + ".metadata.json", base + ".query.json"
        missing = [p for p in (mpath, qpath) if not os.path.exists(p)]
        if missing:
            errors.append("%s/%s: missing %s" % (r["accession"], r["file_name"], missing))
            continue
        row = {"accession": r["accession"], "file_name": r["file_name"]}
        row.update(parse_metadata(mpath))
        row.update(parse_query(qpath))
        if int(row["n_ms2"]) == 0 or int(row["n_sampled_ms2"]) == 0:
            errors.append("%s/%s: no MS2 scans (metadata %s, sampled %s); raise --query_scans"
                          % (r["accession"], r["file_name"], row["n_ms2"], row["n_sampled_ms2"]))
        if "UNKNOWN" in row["ms2_analyzer"]:
            errors.append("%s/%s: unrecognised MS2 analyzer in filter strings"
                          % (r["accession"], r["file_name"]))
        rows.append(row)

    by_acc = collections.OrderedDict()
    for row in rows:
        by_acc.setdefault(row["accession"], []).append(row)
    ds_rows = []
    for acc, rs in by_acc.items():
        def tally(col):
            c = collections.Counter(x[col] for x in rs)
            return ";".join("%s(%d)" % (k, v) for k, v in sorted(c.items()))
        combos = set((x["instrument_model"], x["ms2_analyzer"], x["ms2_activation"], x["sps_ms3"]) for x in rs)
        ds_rows.append({
            "accession": acc, "n_raw": str(len(rs)),
            "instrument_models": tally("instrument_model"),
            "ms2_analyzer": tally("ms2_analyzer"), "ms2_activation": tally("ms2_activation"),
            "n_files_with_ms3": str(sum(1 for x in rs if int(x["n_ms3"]) > 0)),
            "n_files_sps_ms3": str(sum(1 for x in rs if x["sps_ms3"] == "yes")),
            "heterogeneous": "yes" if len(combos) > 1 else "no",
        })

    os.makedirs(a.outdir, exist_ok=True)
    for name, cols, data in (("rawfile_acquisition.tsv", FILE_COLS, rows),
                             ("dataset_acquisition.tsv", DATASET_COLS, ds_rows)):
        with open(os.path.join(a.outdir, name), "w", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=cols, delimiter="\t")
            w.writeheader()
            w.writerows(data)

    log("RAW files in samplesheet: %d; summarised: %d; errors: %d" % (len(raw), len(rows), len(errors)))
    for e in errors:
        log("ERROR " + e)
    return 1 if errors or len(rows) != len(raw) else 0


if __name__ == "__main__":
    sys.exit(main())
