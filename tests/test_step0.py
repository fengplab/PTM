"""Tests for fetch_manifest.py and plan_batches.py using mocked PRIDE responses.

Response shapes mirror pridepy 0.0.16 (PRIDE's client) and its test fixtures.
Synthetic data only.
"""
import csv
import io
import json
import os
import sys
import urllib.error

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "bin"))
import fetch_manifest as fm  # noqa: E402
import plan_batches as pb  # noqa: E402

GB = 10**9


def rec(name, cat, size, ftp=True):
    locs = []
    if ftp:
        locs.append({"name": "FTP Protocol",
                     "value": "ftp://ftp.pride.ebi.ac.uk/pride/data/archive/2020/01/PXD000001/" + name})
        locs.append({"name": "Aspera Protocol",
                     "value": "prd_ascp@fasp.ebi.ac.uk:pride/data/archive/2020/01/PXD000001/" + name})
    return {"fileName": name, "fileSizeBytes": size, "fileCategory": {"value": cat},
            "publicFileLocations": locs}


class Resp:
    def __init__(self, body, status=200):
        self.body, self.status = body, status

    def read(self):
        return self.body

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def make_opener(projects, fail_first=None):
    """projects: {acc: (files_list, checksum_tsv_text)}. fail_first: set of URLs that 429 once."""
    seen = set()

    def opener(req, timeout=None):
        url = req.full_url
        if fail_first and url in fail_first and url not in seen:
            seen.add(url)
            raise urllib.error.HTTPError(url, 429, "Too Many Requests", None, None)
        for acc, (files, ck) in projects.items():
            if url.endswith("/projects/%s" % acc):
                return Resp(json.dumps({"accession": acc, "title": "T " + acc,
                                        "instruments": [{"name": "Q Exactive"}]}).encode())
            if url.endswith("/projects/%s/files/all" % acc):
                return Resp(json.dumps(files).encode())
            if url.endswith("/files/checksum/%s" % acc):
                return Resp(ck.encode())
        raise urllib.error.HTTPError(url, 404, "Not Found", None, None)
    return opener


def ck_tsv(files, drop=(), wrong_size=()):
    lines = ["File-Name\tFile-MD5Checksum\tFile-Size"]
    for f in files:
        if f["fileName"] in drop:
            continue
        size = f["fileSizeBytes"] + (1 if f["fileName"] in wrong_size else 0)
        lines.append("%s\t%s\t%d" % (f["fileName"], "a" * 32, size))
    return "\n".join(lines) + "\n"


def read(path):
    with open(path) as fh:
        return list(csv.DictReader(fh, delimiter="\t"))


@pytest.fixture
def accfile(tmp_path):
    def _w(accs):
        p = tmp_path / "acc.txt"
        p.write_text("\n".join(accs) + "\n# comment\n")
        return str(p)
    return _w


def test_manifest_happy_path(tmp_path, accfile, monkeypatch):
    monkeypatch.setattr(fm.time, "sleep", lambda s: None)
    f1 = [rec("a.raw", "RAW", 2 * GB), rec("b.raw", "RAW", 3 * GB),
          rec("res.txt", "RESULT", 1000), rec("x.sdrf.tsv", "EXPERIMENTAL DESIGN", 10)]
    f2 = [rec("c.RAW", "RAW", 5 * GB)]
    op = make_opener({"PXD000001": (f1, ck_tsv(f1)), "PXD000002": (f2, ck_tsv(f2))})
    out = tmp_path / "out"
    rc = fm.main(["--accessions", accfile(["PXD000001", "PXD000002"]), "--outdir", str(out)], opener=op)
    assert rc == 0
    man = read(out / "manifest.tsv")
    assert len(man) == 5
    summ = {r["accession"]: r for r in read(out / "dataset_summary.tsv")}
    assert summ["PXD000001"]["n_raw"] == "2"
    assert int(summ["PXD000001"]["raw_bytes"]) == 5 * GB
    assert summ["PXD000001"]["sdrf_files"] == "x.sdrf.tsv"
    assert summ["PXD000001"]["instruments"] == "Q Exactive"
    assert summ["PXD000002"]["raw_extensions"] == "raw"
    assert all(r["status"] == "OK" for r in summ.values())
    assert (out / "json" / "PXD000001.files.json").exists()


def test_retry_on_429(tmp_path, accfile, monkeypatch):
    monkeypatch.setattr(fm.time, "sleep", lambda s: None)
    f1 = [rec("a.raw", "RAW", GB)]
    url = fm.API + "/projects/PXD000001/files/all"
    op = make_opener({"PXD000001": (f1, ck_tsv(f1))}, fail_first={url})
    rc = fm.main(["--accessions", accfile(["PXD000001"]), "--outdir", str(tmp_path / "o")], opener=op)
    assert rc == 0


def test_missing_md5_size_mismatch_and_no_ftp_flagged(tmp_path, accfile, monkeypatch):
    monkeypatch.setattr(fm.time, "sleep", lambda s: None)
    f1 = [rec("a.raw", "RAW", GB), rec("b.raw", "RAW", GB, ftp=False), rec("c.raw", "RAW", GB)]
    op = make_opener({"PXD000001": (f1, ck_tsv(f1, drop={"a.raw"}, wrong_size={"c.raw"}))})
    out = tmp_path / "o"
    rc = fm.main(["--accessions", accfile(["PXD000001"]), "--outdir", str(out)], opener=op)
    assert rc == 0  # flagged, not fatal; planner refuses non-OK datasets
    s = read(out / "dataset_summary.tsv")[0]
    assert "RAW_MISSING_MD5" in s["status"]
    assert "RAW_MISSING_FTP" in s["status"]
    assert "SIZE_MISMATCH_VS_CHECKSUM_TSV" in s["status"]


def test_no_raw_and_api_failure_exit_nonzero(tmp_path, accfile, monkeypatch):
    monkeypatch.setattr(fm.time, "sleep", lambda s: None)
    f1 = [rec("res.txt", "RESULT", 10)]
    op = make_opener({"PXD000001": (f1, ck_tsv(f1))})  # PXD000009 -> 404
    out = tmp_path / "o"
    rc = fm.main(["--accessions", accfile(["PXD000001", "PXD000009"]), "--outdir", str(out),
                  "--retries", "1"], opener=op)
    assert rc == 1
    summ = {r["accession"]: r for r in read(out / "dataset_summary.tsv")}
    assert summ["PXD000001"]["status"] == "NO_RAW_FILES"
    assert summ["PXD000009"]["status"].startswith("API_FAILED")


def test_bad_accession_rejected(tmp_path, accfile):
    with pytest.raises(SystemExit):
        fm.main(["--accessions", accfile(["syn10183279"]), "--outdir", str(tmp_path / "o")])


def test_checksum_header_must_match():
    with pytest.raises(ValueError):
        fm.parse_checksum_tsv("name\tmd5\nx\ty\n")


# ---------------- planner ----------------

def write_inputs(tmp_path, sizes_gb, status=None):
    status = status or {}
    summ = tmp_path / "dataset_summary.tsv"
    man = tmp_path / "manifest.tsv"
    with open(summ, "w") as fh:
        fh.write("\t".join(fm.SUMMARY_COLS) + "\n")
        for acc, gb in sizes_gb.items():
            row = {c: "NA" for c in fm.SUMMARY_COLS}
            row.update(accession=acc, n_raw="2", raw_bytes=str(int(gb * GB)),
                       status=status.get(acc, "OK"))
            fh.write("\t".join(row[c] for c in fm.SUMMARY_COLS) + "\n")
    with open(man, "w") as fh:
        fh.write("\t".join(fm.MANIFEST_COLS) + "\n")
        for acc, gb in sizes_gb.items():
            for k in range(2):
                row = {c: "" for c in fm.MANIFEST_COLS}
                row.update(accession=acc, file_name="%s_%d.raw" % (acc, k), category="RAW",
                           size_bytes=str(int(gb * GB / 2)), md5="a" * 32, ftp_url="ftp://x")
                fh.write("\t".join(row[c] for c in fm.MANIFEST_COLS) + "\n")
    return str(summ), str(man)


def test_pack_respects_budget(tmp_path):
    s, m = write_inputs(tmp_path, {"PXD1": 400, "PXD2": 300, "PXD3": 200, "PXD4": 100})
    out = tmp_path / "plan"
    # budget = 1 TB * 0.9 = 900 GB est; factor 2 -> 800,600,400,200 GB
    rc = pb.main(["--summary", s, "--manifest", m, "--available-tb", "1", "--headroom", "0.1",
                  "--footprint-factor", "2", "--outdir", str(out)])
    assert rc == 0
    plan = read(out / "batch_plan.tsv")
    peaks = {}
    for r in plan:
        peaks.setdefault(r["batch"], 0.0)
        peaks[r["batch"]] += float(r["est_peak_TB"])
    assert all(v <= 0.9 + 1e-9 for v in peaks.values())
    assert sorted(r["accession"] for r in plan) == ["PXD1", "PXD2", "PXD3", "PXD4"]
    n_files = sum(len(read(out / "batches" / f)) for f in os.listdir(out / "batches"))
    assert n_files == 8


def test_oversize_and_excluded(tmp_path):
    s, m = write_inputs(tmp_path, {"PXD1": 2000, "PXD2": 10, "PXD3": 10},
                        status={"PXD3": "RAW_MISSING_MD5"})
    out = tmp_path / "plan"
    rc = pb.main(["--summary", s, "--manifest", m, "--available-tb", "1",
                  "--footprint-factor", "4", "--outdir", str(out)])
    assert rc == 2
    plan = {r["accession"]: r["batch"] for r in read(out / "batch_plan.tsv")}
    assert plan["PXD1"] == "OVERSIZE"
    assert plan["PXD3"] == "EXCLUDED"
    assert plan["PXD2"] == "01"
