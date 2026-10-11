#!/usr/bin/env python3
"""Download the gesetze-im-internet.de table of contents and every law's xml.zip.

Usage: fetch.py [RAW_DIR]   (default: ../../_raw/de relative to this script)

Files are cached: an existing zip is not downloaded again unless --refresh is given.
"""
import argparse
import os
import sys
import time
import concurrent.futures as cf
from pathlib import Path
from urllib.parse import urlparse

import requests
from lxml import etree

UA = "LawCodex/1.0 (+https://github.com/LawCodex)"
TOC_URL = "https://www.gesetze-im-internet.de/gii-toc.xml"
WORKERS = 4


def get(session, url, tries=6):
    delay = 2
    for i in range(tries):
        try:
            r = session.get(url, timeout=120)
            if r.status_code == 200:
                return r.content
            if r.status_code == 404:
                return None
            print(f"  HTTP {r.status_code} {url}", file=sys.stderr)
        except requests.RequestException as e:
            print(f"  error {e} {url}", file=sys.stderr)
        time.sleep(delay)
        delay *= 2
    return None


def main():
    here = Path(__file__).resolve().parent
    ap = argparse.ArgumentParser()
    ap.add_argument("raw", nargs="?", default=str(here.parent.parent / "_raw" / "de"))
    ap.add_argument("--refresh", action="store_true")
    args = ap.parse_args()
    raw = Path(args.raw)
    (raw / "zip").mkdir(parents=True, exist_ok=True)
    s = requests.Session()
    s.headers["User-Agent"] = UA

    toc = raw / "gii-toc.xml"
    if args.refresh or not toc.exists():
        data = get(s, TOC_URL)
        if not data:
            sys.exit("cannot fetch TOC")
        toc.write_bytes(data)
    root = etree.parse(str(toc))
    items = []
    for it in root.iter("item"):
        link = it.findtext("link").strip()
        slug = urlparse(link).path.strip("/").split("/")[0]
        items.append((slug, link.replace("http://", "https://")))
    print(f"{len(items)} entries in TOC")

    def job(item):
        slug, url = item
        dest = raw / "zip" / f"{slug}.zip"
        if dest.exists() and not args.refresh:
            return slug, "cached"
        data = get(s, url)
        if data is None:
            return slug, "FAILED"
        tmp = dest.with_suffix(".tmp")
        tmp.write_bytes(data)
        os.replace(tmp, dest)
        return slug, "ok"

    failed = []
    with cf.ThreadPoolExecutor(WORKERS) as ex:
        for n, (slug, st) in enumerate(ex.map(job, items), 1):
            if st == "FAILED":
                failed.append(slug)
            if n % 250 == 0:
                print(f"  {n}/{len(items)}")
    print(f"done, {len(failed)} failed: {failed}")


if __name__ == "__main__":
    main()
