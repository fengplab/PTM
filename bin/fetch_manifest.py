#!/usr/bin/env python3
"""Step 0: list every file in a set of PRIDE projects, with size, MD5 and URLs.

Downloads NO raw data. Only small JSON/TSV metadata from the PRIDE API.

Endpoints and record fields were taken from PRIDE's own client, pridepy 0.0.16
(Apache-2.0), download/pride.py and download/util.py:
  GET {API}/projects/{acc}                -> project metadata (JSON object)
  GET {API}/projects/{acc}/files/all      -> JSON list of file records
        record keys used: fileName, fileSizeBytes, fileCategory.value,
                          publicFileLocations[{name: "FTP Protocol"|"Aspera Protocol", value}]
  GET {API}/files/checksum/{acc}          -> TSV with File-Name, File-MD5Checksum, File-Size

Outputs (in --outdir):
  manifest.tsv          one row per file
  dataset_summary.tsv   one row per accession
  json/<acc>.project.json, json/<acc>.files.json, json/<acc>.checksum.tsv   (audit copies)

Standard library only; runs on macOS system python3 (3.9+) and Linux.
Exits non-zero if any accession fails or has no RAW files.
"""
import argparse
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request

API = "https://www.ebi.ac.uk/pride/ws/archive/v3"
ACC_RE = re.compile(r"^PXD\d{6}$")
USER_AGENT = "ptm-manifest/0.1 (python urllib)"

MANIFEST_COLS = [
    "accession", "file_name", "category", "extension", "size_bytes",
    "md5", "size_matches_checksum_tsv", "ftp_url", "aspera_url",
]
SUMMARY_COLS = [
    "accession", "title", "instruments", "quantification_methods",
    "n_files", "n_raw", "raw_bytes", "total_bytes", "raw_extensions",
    "n_raw_missing_md5", "n_raw_missing_ftp", "sdrf_files", "status",
]


def log(msg):
    sys.stderr.write("[fetch_manifest] %s\n" % msg)
    sys.stderr.flush()


def http_get(url, accept, retries, pause, opener=None):
    """GET with retry/backoff on 429/5xx and network errors. Returns bytes."""
    opener = opener or urllib.request.urlopen
    last_err = None
    for attempt in range(1, retries + 1):
        req = urllib.request.Request(url, headers={"Accept": accept, "User-Agent": USER_AGENT})
        try:
            with opener(req, timeout=120) as resp:
                status = getattr(resp, "status", 200)
                if status != 200:
                    raise urllib.error.HTTPError(url, status, "status %s" % status, None, None)
                return resp.read()
        except urllib.error.HTTPError as e:
            last_err = e
            if e.code not in (429, 500, 502, 503, 504):
                raise
        except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
            last_err = e
        wait = pause * (2 ** (attempt - 1))
        log("GET %s failed (%s); retry %d/%d in %.0fs" % (url, last_err, attempt, retries, wait))
        time.sleep(wait)
    raise RuntimeError("GET %s failed after %d attempts: %s" % (url, retries, last_err))


def parse_checksum_tsv(text):
    """Return {file_name: (md5, size_or_None)} from the PRIDE checksum TSV."""
    lines = [l for l in text.splitlines() if l.strip()]
    if not lines:
        return {}
    cols = [c.strip().lower() for c in lines[0].split("\t")]
    need = {"file-name", "file-md5checksum", "file-size"}
    if not need.issubset(cols):
        raise ValueError("unrecognised checksum TSV header: %r" % lines[0])
    i_name, i_md5, i_size = cols.index("file-name"), cols.index("file-md5checksum"), cols.index("file-size")
    out = {}
    for line in lines[1:]:
        parts = line.rstrip("\n").split("\t")
        if len(parts) <= max(i_name, i_md5, i_size):
            continue
        md5 = parts[i_md5].strip().lower()
        try:
            size = int(parts[i_size].strip())
        except ValueError:
            size = None
        out[parts[i_name].strip()] = (md5, size)
    return out


def extension(name):
    low = name.lower()
    for ext in (".raw.zip", ".mzml.gz", ".wiff.scan", ".d.zip", ".tar.gz"):
        if low.endswith(ext):
            return ext[1:]
    return low.rsplit(".", 1)[-1] if "." in low else ""


def names_from(value):
    """Best-effort flattening of a metadata field that may be list of dicts/strings."""
    # UNVERIFIED: exact shape of instruments / quantificationMethods in the v3
    # project JSON was not confirmed (API unreachable from the build session).
    # Missing or unexpected shapes yield "NA"; the full JSON is saved for audit.
    if not value:
        return "NA"
    if isinstance(value, list):
        out = []
        for v in value:
            if isinstance(v, dict):
                out.append(str(v.get("name") or v.get("value") or v))
            else:
                out.append(str(v))
        return "; ".join(out)
    return str(value)


def build_rows(acc, files, checksums):
    rows = []
    for rec in files:
        name = rec.get("fileName")
        if not name:
            raise ValueError("%s: file record without fileName: %r" % (acc, rec))
        cat = (rec.get("fileCategory") or {}).get("value") or "NA"
        size = rec.get("fileSizeBytes")
        if not isinstance(size, int):
            raise ValueError("%s: %s has non-integer fileSizeBytes %r" % (acc, name, size))
        ftp = aspera = ""
        for loc in rec.get("publicFileLocations") or []:
            if loc.get("name") == "FTP Protocol":
                ftp = loc.get("value") or ""
            elif loc.get("name") == "Aspera Protocol":
                aspera = loc.get("value") or ""
        md5, ck_size = checksums.get(name, ("", None))
        if ck_size is None:
            size_match = "NA"
        else:
            size_match = "yes" if ck_size == size else "no"
        rows.append({
            "accession": acc, "file_name": name, "category": cat,
            "extension": extension(name), "size_bytes": size, "md5": md5,
            "size_matches_checksum_tsv": size_match, "ftp_url": ftp, "aspera_url": aspera,
        })
    return rows


def summarise(acc, project, rows):
    raw = [r for r in rows if r["category"] == "RAW"]
    exts = sorted(set(r["extension"] for r in raw))
    sdrf = [r["file_name"] for r in rows if "sdrf" in r["file_name"].lower()]
    problems = []
    if not raw:
        problems.append("NO_RAW_FILES")
    if any(not r["md5"] for r in raw):
        problems.append("RAW_MISSING_MD5")
    if any(not r["ftp_url"] for r in raw):
        problems.append("RAW_MISSING_FTP")
    if any(r["size_matches_checksum_tsv"] == "no" for r in raw):
        problems.append("SIZE_MISMATCH_VS_CHECKSUM_TSV")
    return {
        "accession": acc,
        "title": (project.get("title") or "NA").replace("\t", " "),
        "instruments": names_from(project.get("instruments")),
        "quantification_methods": names_from(project.get("quantificationMethods")),
        "n_files": len(rows),
        "n_raw": len(raw),
        "raw_bytes": sum(r["size_bytes"] for r in raw),
        "total_bytes": sum(r["size_bytes"] for r in rows),
        "raw_extensions": ",".join(exts) if exts else "NA",
        "n_raw_missing_md5": sum(1 for r in raw if not r["md5"]),
        "n_raw_missing_ftp": sum(1 for r in raw if not r["ftp_url"]),
        "sdrf_files": ",".join(sdrf) if sdrf else "NA",
        "status": ";".join(problems) if problems else "OK",
    }


def write_tsv(path, cols, rows):
    tmp = path + ".tmp"
    with open(tmp, "w") as fh:
        fh.write("\t".join(cols) + "\n")
        for r in rows:
            fh.write("\t".join(str(r[c]) for c in cols) + "\n")
    os.replace(tmp, path)  # write only on success


def read_accessions(path):
    accs = []
    with open(path) as fh:
        for line in fh:
            s = line.split("#", 1)[0].strip()
            if not s:
                continue
            if not ACC_RE.match(s):
                raise SystemExit("not a PRIDE PXD accession: %r" % s)
            if s in accs:
                raise SystemExit("duplicate accession: %s" % s)
            accs.append(s)
    if not accs:
        raise SystemExit("no accessions in %s" % path)
    return accs


def main(argv=None, opener=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--accessions", required=True, help="text file, one PXD accession per line")
    ap.add_argument("--outdir", required=True)
    ap.add_argument("--api", default=API)
    ap.add_argument("--retries", type=int, default=5)
    ap.add_argument("--pause", type=float, default=5.0,
                    help="seconds between projects, and base back-off on errors")
    a = ap.parse_args(argv)

    accs = read_accessions(a.accessions)
    jdir = os.path.join(a.outdir, "json")
    os.makedirs(jdir, exist_ok=True)

    all_rows, summaries, failed = [], [], []
    for i, acc in enumerate(accs):
        if i:
            time.sleep(a.pause)  # PRIDE rate-limits bursts
        log("%s (%d/%d)" % (acc, i + 1, len(accs)))
        try:
            pj = http_get("%s/projects/%s" % (a.api, acc), "application/json", a.retries, a.pause, opener)
            fj = http_get("%s/projects/%s/files/all" % (a.api, acc), "application/json", a.retries, a.pause, opener)
            ck = http_get("%s/files/checksum/%s" % (a.api, acc), "text/plain", a.retries, a.pause, opener)
            project = json.loads(pj.decode("utf-8"))
            files = json.loads(fj.decode("utf-8"))
            if not isinstance(files, list):
                raise ValueError("files/all did not return a JSON list")
            checks = parse_checksum_tsv(ck.decode("utf-8"))
            for suffix, blob in ((".project.json", pj), (".files.json", fj), (".checksum.tsv", ck)):
                with open(os.path.join(jdir, acc + suffix), "wb") as fh:
                    fh.write(blob)
            rows = build_rows(acc, files, checks)
        except Exception as e:  # recorded and reported; run exits non-zero below
            log("FAILED %s: %s" % (acc, e))
            failed.append(acc)
            summaries.append({c: "NA" for c in SUMMARY_COLS})
            summaries[-1].update({"accession": acc, "status": "API_FAILED: %s" % str(e).replace("\t", " ")})
            continue
        s = summarise(acc, project, rows)
        log("%s: %d files in, %d RAW, raw %.1f GB, status %s"
            % (acc, len(files), s["n_raw"], s["raw_bytes"] / 1e9, s["status"]))
        all_rows.extend(rows)
        summaries.append(s)

    write_tsv(os.path.join(a.outdir, "manifest.tsv"), MANIFEST_COLS, all_rows)
    write_tsv(os.path.join(a.outdir, "dataset_summary.tsv"), SUMMARY_COLS, summaries)

    ok = [s for s in summaries if s["status"] != "NA" and isinstance(s["raw_bytes"], int)]
    log("TOTAL RAW across %d fetched accessions: %.2f TB (decimal)"
        % (len(ok), sum(s["raw_bytes"] for s in ok) / 1e12))
    bad = [s["accession"] for s in summaries if "NO_RAW_FILES" in s["status"]]
    if failed or bad:
        log("ERROR: failed=%s no_raw=%s" % (failed, bad))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
