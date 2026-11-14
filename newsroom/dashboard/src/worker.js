/**
 * חדר החדשות · Cloudflare Worker (free plan).
 *  - /data.json    the latest dashboard data, written to KV by each GitHub Actions run
 *  - POST /tg      Telegram webhook (instant bot commands, optional):
 *                  verify Telegram's secret header and the owner's chat id, queue the update in KV
 *                  (key tg:<update_id>), acknowledge in Telegram, and start the GitHub workflow
 *                  with task=bot. Python then reads the queue and answers.
 *  - everything else: the static files in ./public
 * Optional privacy: with the DASHBOARD_KEY secret set, the first visit must be /?k=<key>;
 * the key is kept in a cookie for a year and anything else gets a plain 404.
 *
 * Secrets (wrangler secret put, done by .github/workflows/dashboard.yml):
 *   DASHBOARD_KEY, TG_WEBHOOK_SECRET, TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, GH_DISPATCH_TOKEN, GH_REPO
 */
const COOKIE = "nr_k";

function hasKey(request, key) {
  const c = request.headers.get("Cookie") || "";
  return c.split(/;\s*/).some((p) => p === `${COOKIE}=${encodeURIComponent(key)}`);
}

function safeEqual(a, b) {
  if (typeof a !== "string" || typeof b !== "string" || a.length !== b.length) return false;
  let r = 0;
  for (let i = 0; i < a.length; i++) r |= a.charCodeAt(i) ^ b.charCodeAt(i);
  return r === 0;
}

async function telegramWebhook(request, env, ctx) {
  if (request.method !== "POST" || !env.TG_WEBHOOK_SECRET ||
      !safeEqual(request.headers.get("X-Telegram-Bot-Api-Secret-Token") || "", env.TG_WEBHOOK_SECRET)) {
    return new Response("Not found", { status: 404 });
  }
  let update;
  try { update = await request.json(); } catch (e) { return new Response("ok"); }
  const msg = update && update.message;
  // Telegram retries anything that is not 200, so strangers and junk get a quiet 200.
  if (!msg || String(msg.chat && msg.chat.id) !== String(env.TELEGRAM_CHAT_ID)) return new Response("ok");
  const text = (msg.text || "").trim();
  if (!text.startsWith("/")) return new Response("ok");
  await env.DATA.put(`tg:${update.update_id}`, JSON.stringify(update), { expirationTtl: 7 * 86400 });
  ctx.waitUntil((async () => {
    const tasks = [];
    if (env.TELEGRAM_BOT_TOKEN) {
      tasks.push(fetch(`https://api.telegram.org/bot${env.TELEGRAM_BOT_TOKEN}/sendMessage`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ chat_id: msg.chat.id, text: "⏳ קיבלתי, מטפל בזה. תשובה תוך כדקה.", disable_notification: true }),
      }));
    }
    if (env.GH_DISPATCH_TOKEN && env.GH_REPO) {
      tasks.push(fetch(`https://api.github.com/repos/${env.GH_REPO}/actions/workflows/newsroom.yml/dispatches`, {
        method: "POST",
        headers: { Authorization: `Bearer ${env.GH_DISPATCH_TOKEN}`, Accept: "application/vnd.github+json",
                   "User-Agent": "newsroom-worker", "X-GitHub-Api-Version": "2022-11-28" },
        body: JSON.stringify({ ref: env.GH_REF || "main", inputs: { task: "bot" } }),
      }));
    }
    await Promise.allSettled(tasks);
  })());
  return new Response("ok");
}

export default {
  async fetch(request, env, ctx) {
    const url = new URL(request.url);
    if (url.pathname === "/tg") return telegramWebhook(request, env, ctx);   // has its own secret check

    const key = env.DASHBOARD_KEY;
    if (key) {
      if (url.searchParams.get("k") === key) {
        url.searchParams.delete("k");
        return new Response(null, {
          status: 302,
          headers: {
            Location: url.pathname + (url.search || "") + url.hash,
            "Set-Cookie": `${COOKIE}=${encodeURIComponent(key)}; Max-Age=31536000; Path=/; HttpOnly; Secure; SameSite=Lax`,
          },
        });
      }
      if (!hasKey(request, key)) return new Response("Not found", { status: 404 });
    }
    if (url.pathname === "/data.json") {
      const body = await env.DATA.get("data.json");
      if (!body) return new Response("{}", { status: 404, headers: { "Content-Type": "application/json" } });
      return new Response(body, {
        headers: { "Content-Type": "application/json; charset=utf-8", "Cache-Control": "no-store",
                   "X-Content-Type-Options": "nosniff" },
      });
    }
    const res = await env.ASSETS.fetch(request);
    const h = new Headers(res.headers);
    h.set("X-Content-Type-Options", "nosniff");
    h.set("Referrer-Policy", "no-referrer");
    h.set("Content-Security-Policy",
      "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' https://fonts.googleapis.com; " +
      "font-src https://fonts.gstatic.com; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'");
    if (url.pathname.endsWith(".html") || url.pathname === "/") h.set("Cache-Control", "no-cache");
    return new Response(res.body, { status: res.status, headers: h });
  },
};
