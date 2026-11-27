#!/usr/bin/env python3
"""Verify a downloaded file against the size and MD5 recorded in the step 0 manifest.

The transfer itself is done by pridepy (FTP). This is an independent check
against the manifest values, so a file that pridepy accepted but that differs
from what step 0 recorded still fails the task.

Streams the file (constant memory). Exit 0 if size and MD5 match, 1 if not,
2 on bad arguments. Standard library only.
"""
import argparse
import hashlib
import os
import re
import sys

CHUNK = 8 * 1024 * 1024


def log(msg):
    sys.stderr.write("[verify_file] %s\n" % msg)
    sys.stderr.flush()


def md5sum(path):
    h = hashlib.md5()
    with open(path, "rb") as fh:
        while True:
            buf = fh.read(CHUNK)
            if not buf:
                break
            h.update(buf)
    return h.hexdigest()


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--file", required=True)
    ap.add_argument("--size", type=int, required=True, help="expected size in bytes")
    ap.add_argument("--md5", default="", help="expected MD5 (required unless --allow-no-md5)")
    ap.add_argument("--allow-no-md5", action="store_true",
                    help="check size only (small non-RAW files without a PRIDE checksum)")
    a = ap.parse_args(argv)

    if a.md5 and not re.match(r"^[0-9a-fA-F]{32}$", a.md5):
        log("not an MD5: %r" % a.md5)
        return 2
    if not a.md5 and not a.allow_no_md5:
        log("no expected MD5 given")
        return 2
    if not os.path.isfile(a.file):
        log("missing file: %s" % a.file)
        return 1
    size = os.path.getsize(a.file)
    if size != a.size:
        log("FAILED %s: size %d, expected %d" % (a.file, size, a.size))
        return 1
    if not a.md5:
        log("OK %s: %d bytes (no expected md5; size checked)" % (a.file, size))
        return 0
    digest = md5sum(a.file)
    if digest != a.md5.lower():
        log("FAILED %s: md5 %s, expected %s" % (a.file, digest, a.md5.lower()))
        return 1
    log("OK %s: %d bytes, md5 %s" % (a.file, size, digest))
    return 0


if __name__ == "__main__":
    sys.exit(main())
