# nofilter-engine — בְּלִי פִילְטֵרִים

Static site + two bots. Netlify builds `dist/` from `site/index.template.html` + `data/*.json` on every push.

- `data/events.json` – events (auto-removed after they pass). `pick:true` = "הבחירות של בלי פילטרים".
- `data/banners.json` – hero promo banners (show_from / show_until).
- `data/articles.json` – published articles. `seo/topics.json` – the 321-topic plan with publish dates.
- `build.py` – injects data into the template, writes sitemap.xml / robots.txt / _redirects.
- `writer.py` – writes up to 5 due articles a night with the Anthropic API (GitHub Action `daily publish`, 06:00 Israel).
- `netlify/functions/telegram.mjs` – Telegram bot: send an event link → parsed → asks ⭐ special / regular → commits → site redeploys.
  Commands: `/list`, `/del_<slug>`. Add a date or price to the message if the page lacks them: `https://... 14.11 ₪90`.

Env (Netlify → Site configuration → Environment variables): TELEGRAM_BOT_TOKEN, ALLOWED_CHAT_IDS, GITHUB_TOKEN, GITHUB_REPO, SITE_URL.
GitHub → Settings → Secrets: ANTHROPIC_API_KEY. Variables: SITE_URL.
