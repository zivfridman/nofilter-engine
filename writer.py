#!/usr/bin/env python3
"""Nightly article writer: writes up to N articles whose publish date has arrived (seo/topics.json)
into data/articles.json using the Anthropic API. Fully automatic. Run: python3 writer.py [N]"""
import json, os, sys, re, datetime, pathlib, urllib.request

ROOT = pathlib.Path(__file__).parent
N = int(sys.argv[1]) if len(sys.argv) > 1 else 5
MODEL = os.environ.get("WRITER_MODEL", "claude-sonnet-4-5")
KEY = os.environ["ANTHROPIC_API_KEY"]
TODAY = (datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=2)).date().isoformat()
# optional: also write topics due within the next N days (manual test runs); published date stays TODAY
DUE_BY = (datetime.date.fromisoformat(TODAY) + datetime.timedelta(days=int(os.environ.get("WRITER_DAYS_AHEAD") or 0))).isoformat()

topics = json.loads((ROOT / "seo/topics.json").read_text(encoding="utf-8"))
arts = json.loads((ROOT / "data/articles.json").read_text(encoding="utf-8"))
have = {a["slug"] for a in arts}
EMBED = {"חגים": "all", "כרטיסים": "all", "מקומות": "tlv", "ז׳אנרים": "techno", "ערים": "all", "פסטיבלים": "nature",
         "חו״ל": "all", "קהלים": "all", "טיפים ומדריכים": "all", "תרבות": "all", "המלצות השבוע": "picks", "ברזיל": "brazil", "קופנגן": "phangan"}

SYSTEM = """אתה כותב התוכן של "בְּלִי פִילְטֵרִים" – אתר מסיבות ואירועי לילה בישראל. כתוב בעברית טבעית, בגוף שני רבים, ישיר וקצר, בלי קלישאות.
כללים קשיחים:
- מילים מקוריות בלבד. אין להעתיק משפטים מאתרים אחרים ואין להזכיר אתרים מתחרים.
- אין להמציא עובדות: לא מחירים, לא תאריכים, לא שמות אירועים ספציפיים, לא טענות על מקומות שאינך בטוח בהן. כשפרט תלוי באירוע מסוים – הפנה לבדיקה בעמוד האירוע באתר.
- המטרה: לעזור לקוראים לבחור מסיבה ולקנות כרטיס נכון. שלב באופן טבעי הפניה לעמודי האתר (קטגוריות, הרשמה בחינם, קבוצות הווטסאפ שלנו).
- מבנה: intro של 2–3 משפטים שעונה על השאלה, 4–6 פרקים עם כותרות H2 (לפחות מחציתן מנוסחות כשאלות), רשימות כשזה עוזר, 3–4 שאלות נפוצות עם תשובות של 1–2 משפטים.
- אורך: 450–800 מילים בסך הכול.
החזר JSON בלבד, בלי טקסט לפניו או אחריו, במבנה:
{"title":"כותרת סופית (עד 60 תווים, עם מילת המפתח)","desc":"meta description 120–155 תווים","intro":"...","read":4,
"sections":[{"h":"...","p":["פסקה","פסקה"],"list":["...","..."]}],"faq":[["שאלה","תשובה"]]}
השדה list אופציונלי. אין Markdown בתוך הטקסטים."""

def ask(topic):
    body = {"model": MODEL, "max_tokens": 3000, "system": SYSTEM,
            "messages": [{"role": "user", "content": f"כותרת העבודה: {topic['title']}\nמילת מפתח: {topic['keyword']}\nקטגוריה: {topic['category']}\nכתוב את הכתבה."}]}
    req = urllib.request.Request("https://api.anthropic.com/v1/messages", data=json.dumps(body).encode(),
                                 headers={"x-api-key": KEY, "anthropic-version": "2023-06-01", "content-type": "application/json"})
    with urllib.request.urlopen(req, timeout=180) as r:
        txt = json.loads(r.read())["content"][0]["text"]
    m = re.search(r"\{[\s\S]*\}", txt)
    return json.loads(m.group(0))

def valid(a):
    words = len(re.findall(r"\S+", a["intro"] + " ".join(p for s in a["sections"] for p in s.get("p", []) + s.get("list", []))))
    return 4 <= len(a["sections"]) <= 7 and len(a.get("faq", [])) >= 3 and 350 <= words <= 1100 and 100 <= len(a["desc"]) <= 170

due = [t for t in topics if t["slug"] not in have and t["publish"] <= DUE_BY]
due.sort(key=lambda t: (t["publish"], t["n"]))
written = 0
for t in due[:N]:
    for attempt in range(2):
        try:
            a = ask(t)
            if not valid(a): raise ValueError("quality check failed")
            cat = t["category"]
            related = [x["slug"] for x in arts if x["cat"] == cat][-2:] or [x["slug"] for x in arts[-2:]]
            arts.append({"slug": t["slug"], "title": a["title"], "cat": cat, "embed": EMBED.get(cat, "all"), "read": a.get("read", 4),
                         "desc": a["desc"], "intro": a["intro"], "sections": a["sections"], "faq": a["faq"], "related": related, "published": TODAY})
            written += 1; print("wrote", t["slug"]); break
        except Exception as e:
            print("retry", t["slug"], e)
(ROOT / "data/articles.json").write_text(json.dumps(arts, ensure_ascii=False, indent=1), encoding="utf-8")
print(f"done: {written} new articles, {len(arts)} total")
if due and not written: sys.exit("error: articles were due but none were written")
