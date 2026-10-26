#!/usr/bin/env python3
"""Build dist/ from site/index.template.html + data/*.json. Run: python3 build.py"""
import json, os, re, shutil, datetime, pathlib
ROOT = pathlib.Path(__file__).parent
SITE_URL = os.environ.get("SITE_URL", "https://nofilteril.com").rstrip("/")
IL_TODAY = (datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=2)).date()

def load(name):
    return json.loads((ROOT / "data" / name).read_text(encoding="utf-8"))

def save(name, obj):
    (ROOT / "data" / name).write_text(json.dumps(obj, ensure_ascii=False, indent=1), encoding="utf-8")

events, banners, articles = load("events.json"), load("banners.json"), load("articles.json")

# auto-removal: drop events that ended more than 1 day ago, and banners past show_until
keep = [e for e in events if datetime.date.fromisoformat(e["date"]) >= IL_TODAY - datetime.timedelta(days=1)]
if len(keep) != len(events):
    print(f"removed {len(events)-len(keep)} past events"); events = keep; save("events.json", events)
bk = [b for b in banners if datetime.date.fromisoformat(b["show_until"]) >= IL_TODAY - datetime.timedelta(days=1)]
if len(bk) != len(banners):
    banners = bk; save("banners.json", banners)

# only articles whose publish date arrived
live = [a for a in articles if a.get("published", "2000-01-01") <= IL_TODAY.isoformat()]
topics = json.loads((ROOT / "seo" / "topics.json").read_text(encoding="utf-8"))
done = {a["slug"] for a in live}
sched = [[t["publish"], t["title"]] for t in topics if t["slug"] not in done and t["publish"] > IL_TODAY.isoformat()][:12]

tpl = (ROOT / "site" / "index.template.html").read_text(encoding="utf-8")
def inj(s, key, obj):
    marker = f"/*@@{key}@@*/[]"
    assert marker in s, key
    return s.replace(marker, json.dumps(obj, ensure_ascii=False), 1)
html = tpl
for k, v in [("EVENTS", events), ("BANNERS", banners), ("ARTICLES", live), ("SCHED", sched)]:
    html = inj(html, k, v)

dist = ROOT / "dist"
if dist.exists(): shutil.rmtree(dist)
dist.mkdir()
(dist / "index.html").write_text(html, encoding="utf-8")
if (ROOT / "data" / "posters").exists():
    shutil.copytree(ROOT / "data" / "posters", dist / "posters")
(dist / "_redirects").write_text("/news/*  /index.html  200\n/news  /index.html  200\n/event/*  /index.html  200\n/dj/*  /index.html  200\n/cat/*  /index.html  200\n")
(dist / "robots.txt").write_text(f"User-agent: *\nAllow: /\nSitemap: {SITE_URL}/sitemap.xml\n")
(dist / "404.html").write_text('<!doctype html><meta charset="utf-8"><meta http-equiv="refresh" content="0;url=/">')
urls = [("/", IL_TODAY.isoformat()), ("/news", IL_TODAY.isoformat())]
urls += [(f"/news/{a['slug']}", a.get("published", IL_TODAY.isoformat())) for a in live]
urls += [(f"/event/{e['slug']}", IL_TODAY.isoformat()) for e in events if e.get("slug")]
sm = '<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n' + \
     "".join(f"<url><loc>{SITE_URL}{u}</loc><lastmod>{d}</lastmod></url>\n" for u, d in urls) + "</urlset>\n"
(dist / "sitemap.xml").write_text(sm, encoding="utf-8")
print(f"built dist/: {len(events)} events, {len(banners)} banners, {len(live)} articles, {len(sched)} scheduled")
