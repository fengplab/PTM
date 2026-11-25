"""Tests for step 1 scripts: make_samplesheet, download_verify, summarise_rawmeta.

Synthetic data only. JSON fixtures follow the ThermoRawFileParser 1.4.5 output
layout as read from its source (Writer/Metadata.cs, Query/ProxiSpectrum.cs).
"""
import csv
import functools
import hashlib
import http.server
import json
import os
import sys
import threading

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "bin"))
import download_verify as dv  # noqa: E402
import make_samplesheet as ms  # noqa: E402
import summarise_rawmeta as sr  # noqa: E402

MD5 = "a" * 32


def write_tsv(path, cols, rows):
    with open(path, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=cols, delimiter="\t")
        w.writeheader()
        w.writerows(rows)


def read_csv(path, delim=","):
    with open(path) as fh:
        return list(csv.DictReader(fh, delimiter=delim))


# ---------------- make_samplesheet ----------------

def manifest_rows(acc, n_raw, md5=MD5, sdrf=True):
    rows = []
    for i in range(n_raw):
        rows.append({"accession": acc, "file_name": "%s_%d.raw" % (acc, i), "category": "RAW",
                     "size_bytes": "1000", "md5": md5,
                     "ftp_url": "ftp://ftp.pride.ebi.ac.uk/pride/data/archive/2025/01/%s/%s_%d.raw" % (acc, acc, i)})
    rows.append({"accession": acc, "file_name": "results.txt", "category": "RESULT", "size_bytes": "5",
                 "md5": "", "ftp_url": "ftp://ftp.pride.ebi.ac.uk/x/results.txt"})
    if sdrf:
        rows.append({"accession": acc, "file_name": "%s.sdrf.tsv" % acc, "category": "EXPERIMENTAL DESIGN",
                     "size_bytes": "50", "md5": "",
                     "ftp_url": "ftp://ftp.pride.ebi.ac.uk/pride/data/archive/2025/01/%s/%s.sdrf.tsv" % (acc, acc)})
    return rows


def ms_inputs(tmp_path, manifest, statuses):
    mp, sp = tmp_path / "manifest.tsv", tmp_path / "summary.tsv"
    write_tsv(mp, ["accession", "file_name", "category", "size_bytes", "md5", "ftp_url"], manifest)
    write_tsv(sp, ["accession", "status"], [{"accession": a, "status": s} for a, s in statuses.items()])
    return str(mp), str(sp)


def test_samplesheet_selects_raw_and_sdrf(tmp_path):
    m, s = ms_inputs(tmp_path, manifest_rows("PXD000001", 3) + manifest_rows("PXD000002", 2),
                     {"PXD000001": "OK", "PXD000002": "OK"})
    out = tmp_path / "ss.csv"
    assert ms.main(["--manifest", m, "--summary", s, "--accessions", "PXD000001", "--out", str(out)]) == 0
    rows = read_csv(out)
    assert [r["kind"] for r in rows] == ["raw", "raw", "raw", "sdrf"]
    assert all(r["accession"] == "PXD000001" for r in rows)
    assert rows[0]["url"].startswith("https://ftp.pride.ebi.ac.uk/pride/data/archive/2025/01/PXD000001/")


@pytest.mark.parametrize("statuses,manifest,acc", [
    ({"PXD000001": "RAW_MISSING_MD5"}, manifest_rows("PXD000001", 1), "PXD000001"),
    ({"PXD000001": "OK"}, manifest_rows("PXD000001", 1, md5=""), "PXD000001"),
    ({"PXD000001": "OK"}, manifest_rows("PXD000001", 1), "PXD000009"),
])
def test_samplesheet_rejects_bad_input(tmp_path, statuses, manifest, acc):
    m, s = ms_inputs(tmp_path, manifest, statuses)
    with pytest.raises(SystemExit):
        ms.main(["--manifest", m, "--summary", s, "--accessions", acc, "--out", str(tmp_path / "o.csv")])


def test_https_url_rejects_foreign_host():
    with pytest.raises(ValueError):
        ms.https_url("ftp://example.org/file.raw")


# ---------------- download_verify ----------------

@pytest.fixture
def server(tmp_path):
    root = tmp_path / "srv"
    root.mkdir()
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(root))
    handler.log_message = lambda *a, **k: None
    httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    t = threading.Thread(target=httpd.serve_forever, daemon=True)
    t.start()
    yield root, "http://127.0.0.1:%d" % httpd.server_address[1]
    httpd.shutdown()


@pytest.fixture(autouse=True)
def no_proxy(monkeypatch):
    for v in ("HTTPS_PROXY", "https_proxy", "HTTP_PROXY", "http_proxy"):
        monkeypatch.delenv(v, raising=False)
    monkeypatch.setenv("NO_PROXY", "127.0.0.1")


def test_download_ok(server, tmp_path):
    root, base = server
    data = os.urandom(20000)
    (root / "a.raw").write_bytes(data)
    out = tmp_path / "a.raw"
    rc = dv.main(["--url", base + "/a.raw", "--out", str(out), "--size", str(len(data)),
                  "--md5", hashlib.md5(data).hexdigest(), "--pause", "0"])
    assert rc == 0 and out.read_bytes() == data
    assert not (tmp_path / "a.raw.part").exists()


def test_download_md5_mismatch_leaves_nothing(server, tmp_path):
    root, base = server
    (root / "a.raw").write_bytes(b"x" * 100)
    out = tmp_path / "a.raw"
    rc = dv.main(["--url", base + "/a.raw", "--out", str(out), "--size", "100",
                  "--md5", "0" * 32, "--retries", "2", "--pause", "0"])
    assert rc == 1
    assert not out.exists() and not (tmp_path / "a.raw.part").exists()


def test_download_size_mismatch(server, tmp_path):
    root, base = server
    data = b"y" * 100
    (root / "a.raw").write_bytes(data)
    rc = dv.main(["--url", base + "/a.raw", "--out", str(tmp_path / "a.raw"), "--size", "101",
                  "--md5", hashlib.md5(data).hexdigest(), "--retries", "1", "--pause", "0"])
    assert rc == 1


def test_download_404_not_retried(server, tmp_path):
    _, base = server
    rc = dv.main(["--url", base + "/missing.raw", "--out", str(tmp_path / "m.raw"), "--size", "1",
                  "--md5", MD5, "--retries", "3", "--pause", "0"])
    assert rc == 1


def test_download_requires_md5_unless_allowed(server, tmp_path):
    root, base = server
    (root / "s.sdrf.tsv").write_bytes(b"abc")
    assert dv.main(["--url", base + "/s.sdrf.tsv", "--out", str(tmp_path / "s1"), "--size", "3"]) == 2
    assert dv.main(["--url", base + "/s.sdrf.tsv", "--out", str(tmp_path / "s2"), "--size", "3",
                    "--allow-no-md5", "--pause", "0"]) == 0


def test_download_refuses_overwrite(tmp_path):
    out = tmp_path / "a.raw"
    out.write_bytes(b"old")
    assert dv.main(["--url", "http://127.0.0.1:9/a.raw", "--out", str(out), "--size", "3", "--md5", MD5]) == 2
    assert out.read_bytes() == b"old"


# ---------------- summarise_rawmeta ----------------

def cv(acc, name, value):
    return {"accession": acc, "cvLabel": "MS", "name": name, "value": value}


def metadata(model="Orbitrap Fusion Lumos", n_ms2="5000", n_ms3="0", dissoc=("HCD",)):
    return {
        "FileProperties": [cv("NCIT:C47922", "Pathname", "x.raw")],
        "InstrumentProperties": [cv("MS:1000494", "Thermo Scientific instrument model", model)],
        "MsData": [cv("PRIDE:0000481", "Number of MS1 spectra", "1000"),
                   cv("PRIDE:0000482", "Number of MS2 spectra", n_ms2),
                   cv("PRIDE:0000483", "Number of MS3 spectra", n_ms3),
                   cv("PRIDE:0000472", "MS min charge", "2"),
                   cv("PRIDE:0000473", "MS max charge", "6")],
        "ScanSettings": [cv("MS:1000422", "beam-type collision-induced dissociation", d) for d in dissoc],
        "SampleData": [],
    }


def spectrum(level, fs):
    return {"mzs": [100.0], "intensities": [1.0],
            "attributes": [{"accession": "MS:1003057", "name": "scan number", "value": "1"},
                           {"accession": "MS:1000511", "name": "ms level", "value": str(level)},
                           {"accession": "MS:1000512", "name": "filter string", "value": fs}]}


ORBI_MS2 = "FTMS + c NSI d Full ms2 652.34@hcd38.00 [110.0000-2000.0000]"
IT_MS2 = "ITMS + c NSI r d Full ms2 652.34@cid35.00 [163.0000-1315.0000]"
SPS_MS3 = "FTMS + p NSI sps d Full ms3 652.34@cid35.00 401.22@hcd65.00 [100.0000-500.0000]"
MS1 = "FTMS + p NSI Full ms [375.0000-1500.0000]"


def write_pair(d, acc, stem, meta, spectra):
    with open(os.path.join(d, "%s__%s.metadata.json" % (acc, stem)), "w") as fh:
        json.dump(meta, fh)
    with open(os.path.join(d, "%s__%s.query.json" % (acc, stem)), "w") as fh:
        json.dump(spectra, fh)


def sr_samplesheet(tmp_path, files):
    p = tmp_path / "ss.csv"
    with open(p, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=ms.COLS)
        w.writeheader()
        for acc, fn, kind in files:
            w.writerow({"accession": acc, "file_name": fn, "kind": kind, "size_bytes": "1",
                        "md5": MD5, "url": "https://x/" + fn})
    return str(p)


def test_summarise_orbitrap_iontrap_sps(tmp_path):
    jd = tmp_path / "json"
    jd.mkdir()
    write_pair(jd, "PXD000001", "a", metadata(), [spectrum(1, MS1), spectrum(2, ORBI_MS2)])
    write_pair(jd, "PXD000001", "b", metadata(), [spectrum(1, MS1), spectrum(2, ORBI_MS2)])
    write_pair(jd, "PXD000002", "c", metadata(n_ms3="900", dissoc=("CID",)),
               [spectrum(1, MS1), spectrum(2, IT_MS2), spectrum(3, SPS_MS3)])
    ss = sr_samplesheet(tmp_path, [("PXD000001", "a.raw", "raw"), ("PXD000001", "b.RAW", "raw"),
                                   ("PXD000002", "c.raw", "raw"), ("PXD000002", "c.sdrf.tsv", "sdrf")])
    out = tmp_path / "out"
    assert sr.main(["--samplesheet", ss, "--indir", str(jd), "--outdir", str(out)]) == 0
    files = {r["file_name"]: r for r in read_csv(out / "rawfile_acquisition.tsv", "\t")}
    assert len(files) == 3
    assert files["a.raw"]["ms2_analyzer"] == "FTMS" and files["a.raw"]["ms2_activation"] == "HCD"
    assert files["c.raw"]["ms2_analyzer"] == "ITMS" and files["c.raw"]["ms2_activation"] == "CID"
    assert files["c.raw"]["sps_ms3"] == "yes" and files["c.raw"]["ms3_analyzer"] == "FTMS"
    ds = {r["accession"]: r for r in read_csv(out / "dataset_acquisition.tsv", "\t")}
    assert ds["PXD000001"]["heterogeneous"] == "no" and ds["PXD000001"]["n_raw"] == "2"
    assert ds["PXD000002"]["n_files_sps_ms3"] == "1"


def test_summarise_flags_heterogeneous_dataset(tmp_path):
    jd = tmp_path / "json"
    jd.mkdir()
    write_pair(jd, "PXD000001", "a", metadata(), [spectrum(2, ORBI_MS2)])
    write_pair(jd, "PXD000001", "b", metadata(dissoc=("CID",)), [spectrum(2, IT_MS2)])
    ss = sr_samplesheet(tmp_path, [("PXD000001", "a.raw", "raw"), ("PXD000001", "b.raw", "raw")])
    out = tmp_path / "out"
    assert sr.main(["--samplesheet", ss, "--indir", str(jd), "--outdir", str(out)]) == 0
    ds = read_csv(out / "dataset_acquisition.tsv", "\t")[0]
    assert ds["heterogeneous"] == "yes"
    assert ds["ms2_analyzer"] == "FTMS(1);ITMS(1)"


@pytest.mark.parametrize("case", ["missing", "no_sampled_ms2", "unknown_analyzer"])
def test_summarise_failures(tmp_path, case):
    jd = tmp_path / "json"
    jd.mkdir()
    write_pair(jd, "PXD000001", "a", metadata(), [spectrum(2, ORBI_MS2)])
    if case == "no_sampled_ms2":
        write_pair(jd, "PXD000001", "b", metadata(), [spectrum(1, MS1)])
    elif case == "unknown_analyzer":
        write_pair(jd, "PXD000001", "b", metadata(), [spectrum(2, "XYZ + c ms2 1.0@hcd30.00")])
    ss = sr_samplesheet(tmp_path, [("PXD000001", "a.raw", "raw"), ("PXD000001", "b.raw", "raw")])
    assert sr.main(["--samplesheet", ss, "--indir", str(jd), "--outdir", str(tmp_path / "o")]) == 1
