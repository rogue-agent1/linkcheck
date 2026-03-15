#!/usr/bin/env python3
"""linkcheck - Check URLs in markdown/text files for broken links.

Usage:
    linkcheck.py FILE [FILE...]         Check links in files
    linkcheck.py --dir PATH             Check all .md files in directory
    linkcheck.py URL                    Check single URL
    linkcheck.py --timeout 5 FILE       Custom timeout (default: 10s)
"""

import sys, re, os, json, argparse, urllib.request, urllib.error, ssl
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

URL_RE = re.compile(r'https?://[^\s\)\]>"\'`]+')

def extract_urls(text: str) -> list:
    urls = URL_RE.findall(text)
    # Clean trailing punctuation
    return [u.rstrip('.,;:!?)') for u in urls]

def check_url(url: str, timeout: int = 10) -> dict:
    ctx = ssl.create_default_context()
    try:
        req = urllib.request.Request(url, method="HEAD",
            headers={"User-Agent": "linkcheck/1.0"})
        resp = urllib.request.urlopen(req, timeout=timeout, context=ctx)
        return {"url": url, "status": resp.status, "ok": True}
    except urllib.error.HTTPError as e:
        # Some servers reject HEAD, try GET
        if e.code == 405:
            try:
                req2 = urllib.request.Request(url, headers={"User-Agent": "linkcheck/1.0"})
                resp2 = urllib.request.urlopen(req2, timeout=timeout, context=ctx)
                return {"url": url, "status": resp2.status, "ok": True}
            except:
                pass
        return {"url": url, "status": e.code, "ok": e.code < 400, "error": str(e.reason)}
    except Exception as e:
        return {"url": url, "status": 0, "ok": False, "error": str(e)[:80]}

def check_file(path: str, timeout: int = 10) -> list:
    text = open(path).read()
    urls = list(set(extract_urls(text)))
    if not urls:
        return []
    
    results = []
    with ThreadPoolExecutor(max_workers=8) as pool:
        futures = {pool.submit(check_url, u, timeout): u for u in urls}
        for f in as_completed(futures):
            results.append(f.result())
    return sorted(results, key=lambda r: (r["ok"], r["url"]))

def main():
    parser = argparse.ArgumentParser(description="Check links in files")
    parser.add_argument("targets", nargs="*")
    parser.add_argument("--dir", help="Check all .md files in dir")
    parser.add_argument("--timeout", type=int, default=10)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    files = []
    if args.dir:
        files = sorted(Path(args.dir).rglob("*.md"))
    elif args.targets:
        for t in args.targets:
            if t.startswith("http"):
                r = check_url(t, args.timeout)
                icon = "✅" if r["ok"] else "❌"
                print(f"{icon} {r['status']} {r['url']}", end="")
                if "error" in r: print(f" — {r['error']}", end="")
                print()
                return
            else:
                files.append(Path(t))
    else:
        parser.print_help()
        return

    total_ok, total_bad, total = 0, 0, 0
    all_results = []
    for f in files:
        if not f.exists():
            print(f"⚠️  {f} not found")
            continue
        results = check_file(str(f), args.timeout)
        if not results:
            continue
        bad = [r for r in results if not r["ok"]]
        total += len(results)
        total_ok += len(results) - len(bad)
        total_bad += len(bad)
        all_results.extend(results)

        if bad:
            print(f"\n📄 {f} ({len(bad)} broken / {len(results)} total)")
            for r in bad:
                err = r.get("error", "")
                print(f"  ❌ {r['status']} {r['url']}" + (f" — {err}" if err else ""))

    if args.json:
        print(json.dumps(all_results, indent=2))
    else:
        print(f"\n{'='*40}")
        print(f"Total: {total} links, {total_ok} ok, {total_bad} broken")

if __name__ == "__main__":
    main()
