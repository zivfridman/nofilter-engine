#!/usr/bin/env python3
"""Build dist/ from site/index.template.html + data/*.json.  Run: python3 build.py

What it does
- wraps the single-file site in a proper <html lang="he" dir="rtl"> document
- moves inline base64 posters out to dist/assets/*.jpg (page weight 4MB -> ~300KB)
- injects events / banners / articles / schedule
- prerenders a real HTML page per article (/news/<slug>/) and per event (/event/<slug>/)
  with its own <title>, meta description, canonical, Open Graph and JSON-LD, so search
  engines index each page on its own; the JS app takes over after load
- writes sitemap.xml, robots.txt, _redirects
"""
import json, os, re, shutil, datetime, pathlib, hashlib, base64, html as H

ROOT = pathlib.Path(__file__).parent
SITE_URL = os.environ.get("SITE_URL", "https://nofilteril.com").rstrip("/")
IL_TODAY = (datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=2)).date()
TODAY = IL_TODAY.isoformat()
BRAND = "בְּלִי פִילְטֵרִים"

def load(name): return json.loads((ROOT / "data" / name).read_text(encoding="utf-8"))
def save(name, obj): (ROOT / "data" / name).write_text(json.dumps(obj, ensure_ascii=False, indent=1), encoding="utf-8")
def esc(s): return H.escape(str(s or ""), quote=True)

events, banners, articles = load("events.json"), load("banners.json"), load("articles.json")

# ---- auto-removal of past events / expired banners
keep = [e for e in events if datetime.date.fromisoformat(e["date"]) >= IL_TODAY - datetime.timedelta(days=1)]
if len(keep) != len(events):
    print(f"removed {len(events)-len(keep)} past events"); events = keep; save("events.json", events)
bk = [b for b in banners if datetime.date.fromisoformat(b["show_until"]) >= IL_TODAY - datetime.timedelta(days=1)]
if len(bk) != len(banners): banners = bk; save("banners.json", banners)

live = [a for a in articles if a.get("published", "2000-01-01") <= TODAY]
topics = json.loads((ROOT / "seo" / "topics.json").read_text(encoding="utf-8"))
done = {a["slug"] for a in live}
sched = [[t["publish"], t["title"]] for t in topics if t["slug"] not in done and t["publish"] > TODAY][:12]

# ---- dist skeleton
dist = ROOT / "dist"
if dist.exists(): shutil.rmtree(dist)
(dist / "assets").mkdir(parents=True)
if (ROOT / "data" / "posters").exists(): shutil.copytree(ROOT / "data" / "posters", dist / "posters")
for f in ["favicon.png", "apple-touch-icon.png", "og.jpg", "logo.png", "google775a7364d70e24bc.html"]:
    if (ROOT / "data" / f).exists(): shutil.copy(ROOT / "data" / f, dist / f)

# ---- template: split head/body, externalize big base64 images
tpl = (ROOT / "site" / "index.template.html").read_text(encoding="utf-8")
def ext_img(m):
    kind, b64 = m.group(1), m.group(2)
    if len(b64) < 30000: return m.group(0)
    raw = base64.b64decode(b64); ext = {"jpeg": "jpg", "png": "png", "webp": "webp"}[kind]
    name = hashlib.sha1(raw).hexdigest()[:12] + "." + ext
    (dist / "assets" / name).write_bytes(raw)
    return "/assets/" + name
tpl = re.sub(r'data:image/(jpeg|png|webp);base64,([A-Za-z0-9+/=]+)', ext_img, tpl)
lines = tpl.split("\n"); cut = lines.index("</style>") + 1
HEAD0, BODY0 = "\n".join(lines[:cut]), "\n".join(lines[cut:])
HEAD0 = HEAD0.replace('content="/og.jpg"', f'content="{SITE_URL}/og.jpg"')

def inj(s, key, obj):
    marker = f"/*@@{key}@@*/[]"; assert marker in s, key
    return s.replace(marker, json.dumps(obj, ensure_ascii=False), 1)
for k, v in [("EVENTS", events), ("BANNERS", banners), ("ARTICLES", live), ("SCHED", sched)]:
    BODY0 = inj(BODY0, k, v)

HOME_TITLE = re.search(r"<title>(.*?)</title>", HEAD0).group(1)
HOME_DESC = re.search(r'<meta name="description" content="([^"]*)"', HEAD0).group(1)

def page(title, desc, path, ld=None, pre=None, body_extra=None, og_type="website", og_image=None):
    head = HEAD0.replace(f"<title>{HOME_TITLE}</title>", f"<title>{esc(title)}</title>", 1)
    head = head.replace(f'<meta name="description" content="{HOME_DESC}">', f'<meta name="description" content="{esc(desc)}">', 1)
    url = SITE_URL + path
    extra = [f'<link rel="canonical" href="{url}">', f'<meta property="og:url" content="{url}">', f'<meta property="og:title" content="{esc(title)}">',
             f'<meta property="og:description" content="{esc(desc)}">', f'<meta property="og:type" content="{og_type}">', '<meta property="og:locale" content="he_IL">',
             '<meta name="twitter:card" content="summary_large_image">', f'<link rel="alternate" hreflang="he" href="{url}">']
    if og_image: extra.append(f'<meta property="og:image" content="{og_image}">')
    if ld: extra.append('<script type="application/ld+json" id="ldArticle">' + json.dumps(ld, ensure_ascii=False) + "</script>")
    if pre: extra.append("<script>window.__PRE=" + json.dumps(pre, ensure_ascii=False) + ";</script>")
    body = BODY0
    if body_extra:
        for sel, html in body_extra: body = body.replace(sel, sel + html, 1)
    return ('<!doctype html>\n<html lang="he" dir="rtl">\n<head>\n<meta charset="utf-8">\n<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">\n'
            + head + "\n" + "\n".join(extra) + "\n</head>\n<body>\n" + body + "\n</body>\n</html>\n")

def write(path, content):
    # /news/<slug> -> dist/news/<slug>.html so Netlify serves the slash-less URL directly (no redirect); /news -> dist/news/index.html
    if path == "/": f = dist / "index.html"
    elif path.count("/") == 1: f = dist / path.strip("/") / "index.html"
    else: f = dist / (path.strip("/") + ".html")
    f.parent.mkdir(parents=True, exist_ok=True); f.write_text(content, encoding="utf-8")

ORG = {"@type": "Organization", "name": BRAND, "url": SITE_URL + "/", "logo": SITE_URL + "/logo.png"}
write("/", page(HOME_TITLE, HOME_DESC, "/", ld={"@context": "https://schema.org", "@type": "WebSite", "name": BRAND, "url": SITE_URL + "/", "inLanguage": "he", "publisher": ORG}))

# ---- /news
write("/news", page(f"חדשות ומדריכים למסיבות | {BRAND}", "מדריכים, טיפים וחדשות מעולם המסיבות והלילה בישראל: איך קונים כרטיס, מה לבחור בסופ״ש, ומדריכים לכל ז׳אנר.", "/news",
                    ld={"@context": "https://schema.org", "@type": "CollectionPage", "name": "חדשות ומדריכים", "url": SITE_URL + "/news", "inLanguage": "he", "isPartOf": {"@type": "WebSite", "url": SITE_URL + "/"}},
                    pre={"hash": "#news"}))

# ---- articles
def article_html(a):
    toc = "".join(f'<a href="#" data-i="{i}">{esc(s["h"])}</a>' for i, s in enumerate(a["sections"]))
    body = "".join(f'<section id="as-{i}"><h2>{esc(s["h"])}</h2>' + "".join(f"<p>{esc(p)}</p>" for p in s.get("p", [])) +
                   (("<ul>" + "".join(f"<li>{esc(x)}</li>" for x in s["list"]) + "</ul>") if s.get("list") else "") + "</section>" for i, s in enumerate(a["sections"]))
    faq = ('<section class="afaq"><h2>שאלות נפוצות</h2>' + "".join(f"<details><summary>{esc(q)}</summary><p>{esc(t)}</p></details>" for q, t in a["faq"]) + "</section>") if a.get("faq") else ""
    rel = [x for x in live if x["slug"] in (a.get("related") or [])]
    relh = ('<section class="arel"><h2>כתבות נוספות</h2><div class="agrid">' + "".join(f'<a class="acard" href="/news/{x["slug"]}"><span class="acat">{esc(x["cat"])}</span><b>{esc(x["title"])}</b><span class="adesc">{esc(x["desc"])}</span></a>' for x in rel) + "</div></section>") if rel else ""
    d = datetime.date.fromisoformat(a.get("published", TODAY)).strftime("%d.%m.%Y")
    return (f'<div class="crumb"><a href="/">{BRAND}</a> / <a href="/news">חדשות ומדריכים</a> / <span>{esc(a["cat"])}</span></div>'
            f'<article class="art"><span class="acat">{esc(a["cat"])}</span><h1>{esc(a["title"])}</h1><div class="ameta">מאת מערכת {BRAND} · עודכן {d} · {a.get("read",4)} דק׳ קריאה</div>'
            f'<p class="alead">{esc(a["intro"])}</p><nav class="atoc" aria-label="תוכן עניינים"><b>בכתבה</b>{toc}</nav>{body}{faq}{relh}</article>')

for a in live:
    path = f"/news/{a['slug']}"; url = SITE_URL + path; pub = a.get("published", TODAY)
    ld = [{"@context": "https://schema.org", "@type": "Article", "headline": a["title"], "description": a["desc"], "inLanguage": "he", "datePublished": pub, "dateModified": pub,
           "author": ORG, "publisher": ORG, "mainEntityOfPage": url, "image": SITE_URL + "/og.jpg"},
          {"@context": "https://schema.org", "@type": "BreadcrumbList", "itemListElement": [{"@type": "ListItem", "position": i + 1, "name": n, "item": u} for i, (n, u) in enumerate([(BRAND, SITE_URL + "/"), ("חדשות ומדריכים", SITE_URL + "/news"), (a["title"], url)])]}]
    if a.get("faq"): ld.append({"@context": "https://schema.org", "@type": "FAQPage", "mainEntity": [{"@type": "Question", "name": q, "acceptedAnswer": {"@type": "Answer", "text": t}} for q, t in a["faq"]]})
    write(path, page(f"{a['title']} | {BRAND}", a["desc"], path, ld=ld, pre={"hash": "#article-" + a["slug"]}, og_type="article",
                     body_extra=[('<div class="inner" id="artBox">', article_html(a))]))

# ---- events
def img_url(v):
    if not v: return None
    if v.startswith("/"): return SITE_URL + v
    if v.startswith("http"): return v
    return None
for e in events:
    if not e.get("slug"): continue
    path = f"/event/{e['slug']}"; url = SITE_URL + path
    when = datetime.date.fromisoformat(e["date"]).strftime("%d.%m")
    price = "הרשמה בחינם" if e.get("free") else (f"כרטיסים מ־₪{int(e['price'])}" if e.get("price") else "כרטיסים")
    title = f"{e['name']} – {when} · {e.get('venue') or e.get('city','')} | {BRAND}"
    desc = (e.get("desc") or f"{e['name']} ב{e.get('venue') or e.get('city','')} בתאריך {when}. {price}. כל הפרטים, הליינאפ והקישור לכרטיסים.")[:155]
    ld = {"@context": "https://schema.org", "@type": "Event", "name": e["name"], "startDate": f"{e['date']}T{e.get('start') or '23:00'}:00+02:00", "eventStatus": "https://schema.org/EventScheduled",
          "eventAttendanceMode": "https://schema.org/OfflineEventAttendanceMode", "url": url, "description": desc, "inLanguage": "he",
          "location": {"@type": "Place", "name": e.get("venue") or e.get("city", ""), "address": {"@type": "PostalAddress", "addressLocality": e.get("city", ""), "streetAddress": e.get("address", ""), "addressCountry": "IL"}},
          "organizer": ORG}
    if img_url(e.get("img")): ld["image"] = img_url(e["img"])
    if e.get("lineup"): ld["performer"] = [{"@type": "MusicGroup", "name": n} for n in e["lineup"]]
    if e.get("ticket") and e["ticket"] != "#":
        ld["offers"] = {"@type": "Offer", "url": e["ticket"], "priceCurrency": "ILS", "price": 0 if e.get("free") else (e.get("price") or 0), "availability": "https://schema.org/InStock"}
    write(path, page(title, desc, path, ld=ld, pre={"hash": "#event-" + e["slug"]}, og_type="article", og_image=img_url(e.get("img"))))

# ---- static files
(dist / "_redirects").write_text("/news/*  /index.html  200\n/event/*  /index.html  200\n/dj/*  /index.html  200\n/cat/*  /index.html  200\n")
(dist / "robots.txt").write_text(f"User-agent: *\nAllow: /\nSitemap: {SITE_URL}/sitemap.xml\n")
(dist / "404.html").write_text('<!doctype html><html lang="he"><meta charset="utf-8"><meta http-equiv="refresh" content="0;url=/"></html>')
urls = [("/", TODAY, "daily", "1.0"), ("/news", TODAY, "daily", "0.8")]
urls += [(f"/news/{a['slug']}", a.get("published", TODAY), "weekly", "0.7") for a in live]
urls += [(f"/event/{e['slug']}", TODAY, "daily", "0.6") for e in events if e.get("slug")]
sm = '<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n' + \
     "".join(f"<url><loc>{SITE_URL}{u}</loc><lastmod>{d}</lastmod><changefreq>{c}</changefreq><priority>{p}</priority></url>\n" for u, d, c, p in urls) + "</urlset>\n"
(dist / "sitemap.xml").write_text(sm, encoding="utf-8")
kb = (dist / "index.html").stat().st_size // 1024
print(f"built dist/: {len(events)} events, {len(banners)} banners, {len(live)} articles, {len(sched)} scheduled; index.html {kb}KB; {len(list((dist/'assets').iterdir()))} assets")
