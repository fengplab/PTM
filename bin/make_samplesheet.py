#!/usr/bin/env python3
"""Build the step 1 samplesheet for a batch from the step 0 manifest.

One row per file to download: every RAW file of the selected accessions, plus
any SDRF file (sample description) they have. Sample identity downstream comes
from this sheet (accession + file_name) and the SDRF, never from glob order.

Inputs : manifest.tsv and dataset_summary.tsv from fetch_manifest.py
Output : samplesheet CSV with columns
         accession,file_name,kind,size_bytes,md5,url
         kind is 'raw' or 'sdrf'. url is the PRIDE FTP URL, kept for traceability;
         the download step fetches by accession + file name with pridepy.

Fails if a requested accession is missing, not status OK, has no RAW rows, or
any RAW row lacks an MD5 or URL. Logs counts in and out.
"""
import argparse
import csv
import re
import sys

FTP_PREFIX = "ftp://ftp.pride.ebi.ac.uk/"
COLS = ["accession", "file_name", "kind", "size_bytes", "md5", "url"]
MD5_RE = re.compile(r"^[0-9a-f]{32}$")


def log(msg):
    sys.stderr.write("[make_samplesheet] %s\n" % msg)


def check_url(ftp_url):
    if not ftp_url.startswith(FTP_PREFIX):
        raise ValueError("unexpected PRIDE URL (expected %s...): %s" % (FTP_PREFIX, ftp_url))
    return ftp_url


def read_tsv(path):
    with open(path) as fh:
        return list(csv.DictReader(fh, delimiter="\t"))


def build(manifest, summary, accessions):
    status = {r["accession"]: r["status"] for r in summary}
    rows = []
    for acc in accessions:
        if acc not in status:
            raise SystemExit("accession %s not in dataset_summary" % acc)
        if status[acc] != "OK":
            raise SystemExit("accession %s has status %s" % (acc, status[acc]))
        mrows = [r for r in manifest if r["accession"] == acc]
        raw = [r for r in mrows if r["category"] == "RAW"]
        sdrf = [r for r in mrows if "sdrf" in r["file_name"].lower()]
        if not raw:
            raise SystemExit("accession %s has no RAW files in the manifest" % acc)
        for r in raw:
            if not MD5_RE.match(r["md5"]) or not r["ftp_url"]:
                raise SystemExit("%s/%s lacks a valid md5 or URL" % (acc, r["file_name"]))
        names = [r["file_name"] for r in raw + sdrf]
        if len(names) != len(set(names)):
            raise SystemExit("duplicate file names within %s" % acc)
        for r, kind in [(x, "raw") for x in raw] + [(x, "sdrf") for x in sdrf]:
            rows.append({
                "accession": acc, "file_name": r["file_name"], "kind": kind,
                "size_bytes": r["size_bytes"], "md5": r["md5"], "url": check_url(r["ftp_url"]),
            })
        log("%s: %d manifest rows in, %d RAW + %d SDRF out (%.2f GB raw)"
            % (acc, len(mrows), len(raw), len(sdrf), sum(int(r["size_bytes"]) for r in raw) / 1e9))
    return rows


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--manifest", required=True)
    ap.add_argument("--summary", required=True)
    ap.add_argument("--accessions", required=True, nargs="+")
    ap.add_argument("--out", required=True)
    a = ap.parse_args(argv)
    if len(a.accessions) != len(set(a.accessions)):
        raise SystemExit("duplicate accessions requested")
    rows = build(read_tsv(a.manifest), read_tsv(a.summary), a.accessions)
    with open(a.out, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=COLS)
        w.writeheader()
        w.writerows(rows)
    log("wrote %d rows to %s" % (len(rows), a.out))
    return 0


if __name__ == "__main__":
    sys.exit(main())
