/**
 * חדר החדשות · Cloudflare Worker.
 *  - /data.json  -> the latest dashboard data, written to KV by the GitHub Actions run
 *  - everything else -> the static files in ./public
 * Optional privacy: when the DASHBOARD_KEY secret is set, the first visit must be
 * https://<worker>/?k=<key>. The key is then kept in a cookie for a year, and every
 * request without it gets a plain 404.
 */
const COOKIE = "nr_k";

function hasKey(request, key) {
  const c = request.headers.get("Cookie") || "";
  return c.split(/;\s*/).some((p) => p === `${COOKIE}=${encodeURIComponent(key)}`);
}

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
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
