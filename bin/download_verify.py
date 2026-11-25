#!/usr/bin/env python3
"""Download one file over HTTPS, streaming, and verify size and MD5.

Writes to <out>.part and renames to <out> only after the size and MD5 match,
so a failed or partial download never leaves a file that looks complete.
Retries transient network errors (and HTTP 429/5xx) with back-off; a size or
MD5 mismatch after a complete transfer is retried too, then fails.

Standard library only. Exit 0 on verified success, non-zero otherwise.
"""
import argparse
import hashlib
import os
import sys
import time
import urllib.error
import urllib.request

CHUNK = 8 * 1024 * 1024
USER_AGENT = "ptm-download/0.1 (python urllib)"


def log(msg):
    sys.stderr.write("[download_verify] %s\n" % msg)
    sys.stderr.flush()


def fetch_once(url, part, timeout):
    md5 = hashlib.md5()
    n = 0
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=timeout) as resp, open(part, "wb") as out:
        while True:
            buf = resp.read(CHUNK)
            if not buf:
                break
            out.write(buf)
            md5.update(buf)
            n += len(buf)
    return n, md5.hexdigest()


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--url", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--size", type=int, required=True, help="expected size in bytes")
    ap.add_argument("--md5", default="", help="expected MD5 (required unless --allow-no-md5)")
    ap.add_argument("--allow-no-md5", action="store_true",
                    help="verify size only (used for small non-RAW files without a PRIDE checksum)")
    ap.add_argument("--retries", type=int, default=5)
    ap.add_argument("--pause", type=float, default=30.0)
    ap.add_argument("--timeout", type=float, default=300.0)
    a = ap.parse_args(argv)

    if not a.md5 and not a.allow_no_md5:
        log("no expected MD5 given")
        return 2
    if os.path.exists(a.out):
        log("refusing to overwrite existing %s" % a.out)
        return 2
    part = a.out + ".part"
    for attempt in range(1, a.retries + 1):
        try:
            n, digest = fetch_once(a.url, part, a.timeout)
        except urllib.error.HTTPError as e:
            if e.code not in (429, 500, 502, 503, 504):
                log("HTTP %s for %s; not retrying" % (e.code, a.url))
                break
            log("HTTP %s (attempt %d/%d)" % (e.code, attempt, a.retries))
        except (urllib.error.URLError, TimeoutError, ConnectionError, OSError) as e:
            log("network error: %s (attempt %d/%d)" % (e, attempt, a.retries))
        else:
            ok_size = n == a.size
            ok_md5 = (not a.md5) or digest == a.md5.lower()
            if ok_size and ok_md5:
                os.replace(part, a.out)
                log("OK %s: %d bytes, md5 %s%s" % (os.path.basename(a.out), n, digest,
                                                    "" if a.md5 else " (no expected md5; size checked)"))
                return 0
            log("verification failed: size %d (expected %d), md5 %s (expected %s); attempt %d/%d"
                % (n, a.size, digest, a.md5 or "NA", attempt, a.retries))
        if attempt < a.retries:
            time.sleep(a.pause * attempt)
    if os.path.exists(part):
        os.remove(part)
    log("FAILED %s" % a.url)
    return 1


if __name__ == "__main__":
    sys.exit(main())
