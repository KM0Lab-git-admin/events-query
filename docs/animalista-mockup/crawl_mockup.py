"""Mockup crawl for El Viajero Animalista.

1. Resolve Google News redirect URLs to the real article URL (batchexecute).
2. Respect robots.txt per domain.
3. Fetch each article once, extract title / description / date / image /
   first paragraphs. Output JSON for manual enrichment.

Usage: python -I crawl.py <workdir>
"""
from __future__ import annotations

import json
import re
import sys
import time
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from urllib.parse import quote, urlparse
from urllib import robotparser

import requests
from bs4 import BeautifulSoup

WORK = Path(sys.argv[1])
OUT = WORK / "out"
OUT.mkdir(exist_ok=True)

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36 ViajeroAnimalista-Mockup/0.1"
ROBOTS_UA = "ViajeroAnimalista-Mockup"
GN_COOKIES = {
    "CONSENT": "YES+cb.20210720-07-p0.en+FX+410",
    "SOCS": "CAESHAgBEhJnd3NfMjAyMzA4MTAtMF9SQzIaAmRlIAEaBgiA_LyaBg",
}
TIMEOUT = 25

session = requests.Session()
session.headers.update({"User-Agent": UA, "Accept-Language": "es-ES,es;q=0.9"})


# ---------------------------------------------------------------- Google News
def gn_decode(gn_url: str) -> str:
    base64_str = urlparse(gn_url).path.rstrip("/").split("/")[-1]
    r = session.get(f"https://news.google.com/articles/{base64_str}",
                    cookies=GN_COOKIES, timeout=TIMEOUT)
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "lxml")
    div = soup.select_one("c-wiz > div")
    if div is None or not div.get("data-n-a-sg"):
        # old format: the real URL may be in an <a> tag
        a = soup.select_one("a[href^=http]")
        if a and "google.com" not in a["href"]:
            return a["href"]
        raise RuntimeError("no decoding params (consent wall?)")
    sig, ts = div["data-n-a-sg"], div["data-n-a-ts"]
    payload = ["Fbv4je",
               f'["garturlreq",[["X","X",["X","X"],null,null,1,1,"US:en",null,1,'
               f'null,null,null,null,null,0,1],"X","X",1,[1,1,1],1,1,null,0,0,null,0],'
               f'"{base64_str}",{ts},"{sig}"]']
    r = session.post("https://news.google.com/_/DotsSplashUi/data/batchexecute",
                     headers={"Content-Type": "application/x-www-form-urlencoded;charset=UTF-8"},
                     data=f"f.req={quote(json.dumps([[payload]]))}",
                     cookies=GN_COOKIES, timeout=TIMEOUT)
    r.raise_for_status()
    parsed = json.loads(r.text.split("\n\n")[1])[:-2]
    return json.loads(parsed[0][2])[1]


# ---------------------------------------------------------------- robots
_robots: dict[str, robotparser.RobotFileParser | None] = {}
_robots_lock = threading.Lock()


def robots_allows(url: str) -> bool:
    host = urlparse(url).scheme + "://" + urlparse(url).netloc
    with _robots_lock:
        rp = _robots.get(host, "unset")
        if rp == "unset":
            rp = robotparser.RobotFileParser()
            try:
                rr = session.get(host + "/robots.txt", timeout=15)
                if rr.status_code == 200:
                    rp.parse(rr.text.splitlines())
                else:
                    rp = None  # no robots -> allowed
            except Exception:
                rp = None
            _robots[host] = rp
    if rp is None:
        return True
    return rp.can_fetch(ROBOTS_UA, url) and rp.can_fetch("*", url)


# ---------------------------------------------------------------- article
def _meta(soup, *names):
    for n in names:
        tag = soup.find("meta", attrs={"property": n}) or soup.find("meta", attrs={"name": n})
        if tag and tag.get("content"):
            return tag["content"].strip()
    return None


def _jsonld(soup) -> dict:
    out = {}
    for s in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(s.string or "")
        except Exception:
            continue
        nodes = data if isinstance(data, list) else [data]
        for node in nodes:
            if not isinstance(node, dict):
                continue
            if "@graph" in node and isinstance(node["@graph"], list):
                nodes.extend(n for n in node["@graph"] if isinstance(n, dict))
                continue
            t = node.get("@type")
            if isinstance(t, list):
                t = t[0] if t else None
            if t in ("NewsArticle", "Article", "BlogPosting", "Event", "WebPage") and "datePublished" in node:
                out.setdefault("datePublished", node.get("datePublished"))
                out.setdefault("headline", node.get("headline"))
                out.setdefault("description", node.get("description"))
                if t == "Event":
                    out["event"] = {k: node.get(k) for k in ("startDate", "endDate", "location", "name")}
    return out


def extract(url: str, html: str) -> dict:
    soup = BeautifulSoup(html, "lxml")
    for tag in soup(["script", "style", "nav", "footer", "aside", "noscript", "iframe", "form", "header", "figure"]):
        if tag.name == "script" and tag.get("type") == "application/ld+json":
            continue
        tag.decompose()
    ld = _jsonld(BeautifulSoup(html, "lxml"))
    container = soup.find("article") or soup.find("main") or soup.body or soup
    paras = [p.get_text(" ", strip=True) for p in container.find_all("p")]
    paras = [p for p in paras if len(p) > 60]
    body = "\n".join(paras)[:3000]
    title = _meta(soup, "og:title") or ld.get("headline") or (soup.title.get_text(strip=True) if soup.title else None)
    return {
        "titulo": title,
        "descripcion": _meta(soup, "og:description", "description") or ld.get("description"),
        "fecha": _meta(soup, "article:published_time", "date", "DC.date.issued", "pubdate") or ld.get("datePublished"),
        "imagen": _meta(soup, "og:image"),
        "canonical": (soup.find("link", rel="canonical") or {}).get("href") or url,
        "evento_jsonld": ld.get("event"),
        "cuerpo": body,
        "n_parrafos": len(paras),
    }


def process(item: dict) -> dict:
    res = dict(item)
    try:
        url = item["url"]
        if "news.google.com" in url:
            url = gn_decode(url)
            res["url_real"] = url
        else:
            res["url_real"] = url
        if not robots_allows(url):
            res["estado"] = "ROBOTS"
            return res
        r = session.get(url, timeout=TIMEOUT, allow_redirects=True)
        res["http"] = r.status_code
        if r.status_code != 200:
            res["estado"] = f"HTTP_{r.status_code}"
            return res
        res.update(extract(r.url, r.text))
        res["url_real"] = r.url
        res["estado"] = "OK"
    except Exception as exc:  # noqa: BLE001
        res["estado"] = "ERROR"
        res["error"] = f"{type(exc).__name__}: {exc}"[:300]
    return res


def load(path: Path) -> list[dict]:
    items = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        iid, medio, hint, url = line.split("|", 3)
        items.append({"id": iid, "medio": medio, "hint": hint, "url": url})
    return items


def main():
    items = load(WORK / "gn_urls.txt") + load(WORK / "direct_urls.txt")
    results = []
    with ThreadPoolExecutor(max_workers=5) as ex:
        futs = {ex.submit(process, it): it for it in items}
        for f in as_completed(futs):
            r = f.result()
            results.append(r)
            print(f"{r['id']:5} {r['estado']:10} {r.get('http','')!s:4} {r.get('url_real','')[:90]}", flush=True)
    results.sort(key=lambda x: x["id"])
    (OUT / "items.json").write_text(json.dumps(results, ensure_ascii=False, indent=1), encoding="utf-8")
    ok = sum(1 for r in results if r["estado"] == "OK")
    print(f"\nTOTAL {len(results)} · OK {ok} · " + ", ".join(
        f"{k} {v}" for k, v in sorted(
            ((s, sum(1 for r in results if r['estado'] == s)) for s in {r['estado'] for r in results}))))


if __name__ == "__main__":
    main()
