// Telegram bot: send an event link -> bot parses it -> asks "special or regular?" -> commits to data/*.json on GitHub -> Netlify redeploys.
// Env: TELEGRAM_BOT_TOKEN, ALLOWED_CHAT_IDS (comma separated), GITHUB_TOKEN (repo scope), GITHUB_REPO (owner/name), SITE_URL
import { getStore } from "@netlify/blobs";

const TG = `https://api.telegram.org/bot${process.env.TELEGRAM_BOT_TOKEN}`;
const [OWNER, REPO] = (process.env.GITHUB_REPO || "").split("/");
const SITE = (process.env.SITE_URL || "https://nofilteril.com").replace(/\/$/, "");
const ALLOWED = (process.env.ALLOWED_CHAT_IDS || "").split(",").map(s => s.trim()).filter(Boolean);
const GENRE = [["trance", /(trance|psy|goa|טראנס|פסיי|טבע|nature|festival|פסטיבל|open air)/i], ["techno", /(techno|house|טכנו|האוס|melodic|afro|minimal|rave)/i], ["hiphop", /(hip ?hop|היפ ?הופ|rap|ראפ|trap)/i], ["main", /(mainstream|מיינסטרים|hits|להיטים|ישראלי|מזרחית|90s|80s|שנות ה)/i]];
const TYPES = [["openbar", /(open ?bar|אלכוהול חופשי|בר חופשי|all you can drink)/i], ["40plus", /(40\+|30\+|40 פלוס|30 פלוס|נוסטלגי)/i], ["wine", /(יין|wine|יקב)/i], ["youth", /(נוער|youth|תיכון)/i], ["halloween", /(halloween|האלווין|הלואין|הלוואין)/i], ["purim", /(purim|פורים)/i], ["beach", /(חוף|beach)/i], ["brazil", /(brazil|ברזיל|samba|סמבה|funk)/i], ["phangan", /(phangan|פנגן|קופנגן|full moon)/i]];
const CITIES = [["תל אביב", /(תל.?אביב|tel.?aviv|tlv|יפו|נמל)/i], ["חיפה", /(חיפה|haifa)/i], ["ירושלים", /(ירושלים|jerusalem)/i], ["הרצליה", /(הרצליה|herzliya)/i], ["באר שבע", /(באר שבע|beer.?sheva)/i], ["אילת", /(אילת|eilat)/i], ["הערבה", /(ערבה|arava|שיטים)/i]];
const slugify = t => t.toLowerCase().replace(/[^\p{L}\p{N}]+/gu, "-").replace(/^-|-$/g, "");
const isWeekend = d => [4, 5, 6].includes(new Date(d + "T12:00:00").getDay());
const ilDate = d => d.toLocaleDateString("sv-SE", { timeZone: "Asia/Jerusalem" });
const ilTime = d => d.toLocaleTimeString("he-IL", { hour: "2-digit", minute: "2-digit", timeZone: "Asia/Jerusalem" });

async function tg(method, body) { return (await fetch(`${TG}/${method}`, { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify(body) })).json(); }
const GH = (path, init = {}) => fetch(`https://api.github.com/repos/${OWNER}/${REPO}/contents/${path}`, { ...init, headers: { authorization: `Bearer ${process.env.GITHUB_TOKEN}`, accept: "application/vnd.github+json", "content-type": "application/json", ...(init.headers || {}) } });
async function ghRead(path) { const r = await GH(path); if (!r.ok) return { sha: null, text: null }; const j = await r.json(); return { sha: j.sha, text: Buffer.from(j.content, "base64").toString("utf8") }; }
async function ghWrite(path, content, message, sha) { const b64 = Buffer.isBuffer(content) ? content.toString("base64") : Buffer.from(content, "utf8").toString("base64"); const r = await GH(path, { method: "PUT", body: JSON.stringify({ message, content: b64, sha: sha || undefined }) }); if (!r.ok) throw new Error("github " + r.status + " " + (await r.text()).slice(0, 200)); }

function parse(url, html, hint = "") {
  const text = html.replace(/<script[\s\S]*?<\/script>|<style[\s\S]*?<\/style>/g, " ").replace(/<[^>]+>/g, " ").replace(/\s+/g, " ");
  const meta = n => (html.match(new RegExp(`<meta[^>]+(?:property|name)=["']${n}["'][^>]+content=["']([^"']+)`, "i")) || html.match(new RegExp(`<meta[^>]+content=["']([^"']+)["'][^>]+(?:property|name)=["']${n}["']`, "i")) || [])[1];
  let ld = null;
  for (const m of html.matchAll(/<script[^>]+application\/ld\+json[^>]*>([\s\S]*?)<\/script>/gi)) {
    try { const j = JSON.parse(m[1]); const arr = Array.isArray(j) ? j : (j["@graph"] || [j]); const f = arr.find(x => /Event/.test(x["@type"] || "")); if (f) { ld = f; break; } } catch (_) { }
  }
  const ev = { src: url, ticket: url, bg: "#1b1b21", tags: [], lineup: [], free: false, price: null, age: 18 };
  if (ld) {
    ev.name = ld.name; const sd = ld.startDate ? new Date(ld.startDate) : null, ed = ld.endDate ? new Date(ld.endDate) : null;
    if (sd) { ev.date = ilDate(sd); ev.start = ilTime(sd); } if (ed) ev.end = ilTime(ed);
    const loc = ld.location || {}; ev.venue = (loc.name || "").split(",")[0].trim(); ev.city = loc.address?.addressLocality || ""; ev.address = loc.address?.streetAddress || "";
    ev.img = Array.isArray(ld.image) ? ld.image[0] : (ld.image?.url || ld.image); ev.desc = (ld.description || "").slice(0, 600);
    const offers = [].concat(ld.offers || []); const prices = offers.map(o => +o.price).filter(n => n > 0); if (prices.length) ev.price = Math.min(...prices);
    if (offers.some(o => +o.price === 0 || /חינם|free/i.test(o.name || ""))) ev.free = true;
  } else {
    ev.name = (meta("og:title") || (html.match(/<title>([^<]+)/i) || [])[1] || "אירוע חדש").trim();
    ev.img = meta("og:image"); ev.desc = (meta("og:description") || "").slice(0, 600);
    const t2 = ev.name + " " + ev.desc + " " + text;
    const d = t2.match(/(\d{1,2})[./](\d{1,2})[./](\d{4})/); if (d) ev.date = `${d[3]}-${d[2].padStart(2, "0")}-${d[1].padStart(2, "0")}`;
    const p = t2.match(/₪\s?(\d{2,4})/); if (p) ev.price = +p[1]; if (/חינם|free entry|כניסה חופשית/i.test(t2)) ev.free = true;
  }
  ev.name = (ev.name || "").replace(/\s*\|\s*\d{1,2}\.\d{1,2}.*$/, "").trim();
  const blob = [ev.name, ev.venue, ev.desc, text.slice(0, 4000)].join(" ");
  const g = GENRE.find(([, r]) => r.test(blob)); ev.genre = g ? g[0] : "techno";
  ev.tags = [ev.genre === "trance" ? "trance" : ev.genre === "hiphop" ? "hiphop" : ev.genre];
  TYPES.forEach(([k, r]) => { if (r.test(blob)) ev.tags.push(k); });
  if (ev.free) ev.tags.push("free"); if (ev.date && isWeekend(ev.date)) ev.tags.push("weekend");
  if (!ev.city) { const c = CITIES.find(([, r]) => r.test(blob)); ev.city = c ? c[0] : "תל אביב"; }
  if (/תל אביב-יפו/.test(ev.city)) ev.city = "תל אביב"; if (!ev.venue) ev.venue = ev.city;
  const lu = new Set(); for (const m of blob.matchAll(/(?:line ?up|ליינאפ|hosting|b2b|מארחים?)[:\s]*([\s\S]{0,200})/gi)) m[1].split(/\n|,|\||•|·|\/|&|\+/).map(x => x.trim()).filter(x => /^[A-Z0-9][A-Z0-9 .\-']{1,28}$/.test(x)).forEach(x => lu.add(x));
  ev.lineup = [...lu].slice(0, 8);
  const hd = hint.match(/(\d{1,2})[./](\d{1,2})(?:[./](\d{4}))?/); if (hd) { const y = hd[3] || String(new Date().getFullYear()); ev.date = `${y}-${hd[2].padStart(2, "0")}-${hd[1].padStart(2, "0")}`; }
  const hp = hint.match(/₪\s?(\d{2,4})|(\d{2,4})\s?₪/); if (hp) ev.price = +(hp[1] || hp[2]);
  ev.noDate = !ev.date; ev.date = ev.date || ilDate(new Date()); ev.start = ev.start || "23:00"; ev.end = ev.end || "";
  ev.slug = slugify(ev.name) + "-" + ev.date.slice(5).replace("-", "-");
  return ev;
}
const summary = e => `*${e.name}*\n📅 ${e.date} · ${e.start}${e.end ? "–" + e.end : ""}\n📍 ${e.venue}${e.city && e.city !== e.venue ? ", " + e.city : ""}\n🎧 ${e.genre}${e.tags.filter(t => !["techno", "trance", "main", "hiphop"].includes(t)).map(t => " · " + t).join("")}\n💸 ${e.free ? "הרשמה בחינם" : e.price ? "מ־₪" + e.price : "מחיר לא זוהה"}\n${e.lineup.length ? "🎚 " + e.lineup.join(", ") + "\n" : ""}${e.img ? "🖼 פוסטר נמצא" : "⚠️ לא נמצא פוסטר"}`;

async function publish(draft, special) {
  const today = ilDate(new Date());
  let img = "";
  if (draft.img) { try { const r = await fetch(draft.img); const buf = Buffer.from(await r.arrayBuffer()); if (buf.length < 3e6) { const ext = /png/i.test(r.headers.get("content-type") || "") ? "png" : "jpg"; img = `/posters/${draft.slug}.${ext}`; const cur = await ghRead(`data/posters/${draft.slug}.${ext}`); await ghWrite(`data/posters/${draft.slug}.${ext}`, buf, `poster ${draft.slug}`, cur.sha); } } catch (_) { img = draft.img; } }
  const ev = { name: draft.name, date: draft.date, tags: [...new Set(draft.tags)], bg: draft.bg, pick: special, venue: draft.venue, city: draft.city, address: draft.address || "", lineup: draft.lineup, price: draft.price, free: draft.free, start: draft.start, end: draft.end, age: draft.age, ticket: draft.ticket, src: draft.src, img, slug: draft.slug, desc: draft.desc || "" };
  const ef = await ghRead("data/events.json"); const events = JSON.parse(ef.text || "[]").filter(e => e.slug !== ev.slug); events.push(ev);
  await ghWrite("data/events.json", JSON.stringify(events, null, 1), `event: ${ev.name}${special ? " (special)" : ""}`, ef.sha);
  if (special) {
    const bf = await ghRead("data/banners.json"); const banners = JSON.parse(bf.text || "[]").filter(b => b.id !== ev.slug);
    const d = new Date(ev.date + "T12:00:00"); const when = d.toLocaleDateString("he-IL", { weekday: "long", day: "numeric", month: "numeric" });
    banners.unshift({ id: ev.slug, kicker: "ממולץ" + (ev.free ? " · הרשמה בחינם" : ev.tags.includes("openbar") ? " · אלכוהול חופשי" : ""), title: ev.name, subtitle: `${when} · ${ev.start}${ev.end ? "–" + ev.end : ""} · ${ev.venue}${ev.price ? " · מ-₪" + ev.price : ""}`, link: "#event-" + ev.slug, img, bg: "", show_from: today, show_until: ev.date, sort: 0 });
    await ghWrite("data/banners.json", JSON.stringify(banners, null, 1), `banner: ${ev.name}`, bf.sha);
  }
  return ev;
}

export default async (req) => {
  if (req.method !== "POST") return new Response("ok");
  const u = await req.json(); const store = getStore("pending");
  const msg = u.message, cb = u.callback_query; const chat = String((msg || cb?.message)?.chat?.id || "");
  if (ALLOWED.length && !ALLOWED.includes(chat)) return new Response("ignored");
  try {
    if (cb) {
      const [act, id] = cb.data.split(":"); const draft = await store.get(id, { type: "json" });
      await tg("answerCallbackQuery", { callback_query_id: cb.id });
      if (!draft) return reply(chat, "הטיוטה פגה. שלחו את הקישור שוב.");
      if (act === "x") { await store.delete(id); return reply(chat, "בוטל."); }
      const ev = await publish(draft, act === "s"); await store.delete(id);
      return reply(chat, `✓ עלה כ${act === "s" ? "אירוע מיוחד (באנר + המלצות)" : "אירוע רגיל"}.\nיופיע באתר תוך כ־2 דקות:\n${SITE}/event/${ev.slug}`);
    }
    const text = msg?.text || msg?.caption || "";
    if (/^\/list/.test(text)) { const { text: t } = await ghRead("data/events.json"); const today = ilDate(new Date()); const l = JSON.parse(t || "[]").filter(e => e.date >= today).sort((a, b) => a.date.localeCompare(b.date)); return reply(chat, l.map(e => `${e.date} · ${e.name}${e.pick ? " ⭐" : ""}\n/del_${e.slug.replace(/-/g, "_")}`).join("\n\n") || "אין אירועים קרובים"); }
    const del = text.match(/^\/del[_ ](.+)/);
    if (del) { const slug = del[1].trim().replace(/_/g, "-"); const ef = await ghRead("data/events.json"); const ev = JSON.parse(ef.text || "[]"); const left = ev.filter(e => e.slug !== slug); if (left.length === ev.length) return reply(chat, "לא נמצא."); await ghWrite("data/events.json", JSON.stringify(left, null, 1), `remove ${slug}`, ef.sha); const bf = await ghRead("data/banners.json"); const b = JSON.parse(bf.text || "[]"); if (b.some(x => x.id === slug)) await ghWrite("data/banners.json", JSON.stringify(b.filter(x => x.id !== slug), null, 1), `remove banner ${slug}`, bf.sha); return reply(chat, "הוסר ✓"); }
    const url = (text.match(/https?:\/\/\S+/) || [])[0];
    if (!url) return reply(chat, "שלחו לי קישור לאירוע (Eventer, Go-Out, Zygo, Popit, Facebook וכו׳) ואני אעלה אותו לאתר.\n/list – אירועים קרובים");
    const r = await fetch(url, { headers: { "user-agent": "Mozilla/5.0 (compatible; NoFilterBot/1.0)", "accept-language": "he,en" }, redirect: "follow" });
    const draft = parse(url, await r.text(), text.replace(url, ""));
    const id = Date.now().toString(36); await store.setJSON(id, draft);
    await tg("sendMessage", { chat_id: chat, text: summary(draft) + (draft.noDate ? "\n\n⚠️ לא זיהיתי תאריך. שלחו שוב את הקישור עם התאריך (למשל: 14.11)" : "") + "\n\nאיך להעלות?", parse_mode: "Markdown", reply_markup: { inline_keyboard: [[{ text: "⭐ אירוע מיוחד (באנר + המלצות)", callback_data: "s:" + id }], [{ text: "אירוע רגיל", callback_data: "r:" + id }, { text: "❌ ביטול", callback_data: "x:" + id }]] } });
  } catch (e) { await reply(chat, "שגיאה: " + e.message.slice(0, 200)); }
  return new Response("ok");
};
async function reply(chat, text) { await tg("sendMessage", { chat_id: chat, text, disable_web_page_preview: true }); return new Response("ok"); }
export const config = { path: "/api/telegram" };
