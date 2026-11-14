// Runs the real Worker with fake KV / assets / network. Invoked from tests/test_webhook.py.
import worker from "../dashboard/src/worker.js";

const store = new Map();
const calls = [];
globalThis.fetch = async (url, init) => { calls.push({ url: String(url), body: init && init.body }); return new Response("{}"); };
const env = {
  DATA: { get: async (k) => store.get(k) ?? null, put: async (k, v) => { store.set(k, v); } },
  ASSETS: { fetch: async () => new Response("<html>", { headers: { "Content-Type": "text/html" } }) },
  TG_WEBHOOK_SECRET: "s3cret", TELEGRAM_CHAT_ID: "42", TELEGRAM_BOT_TOKEN: "T", GH_DISPATCH_TOKEN: "G", GH_REPO: "me/newsroom",
  DASHBOARD_KEY: "open",
};
const pending = [];
const ctx = { waitUntil: (p) => pending.push(p) };
const tg = (body, secret = "s3cret") => new Request("https://w.dev/tg", { method: "POST",
  headers: { "X-Telegram-Bot-Api-Secret-Token": secret, "Content-Type": "application/json" }, body: JSON.stringify(body) });
const fail = (m) => { console.error("FAIL:", m); process.exit(1); };

let r = await worker.fetch(tg({ update_id: 1, message: { chat: { id: 42 }, text: "/add NVDA" } }, "wrong"), env, ctx);
if (r.status !== 404 || store.size) fail("wrong secret must be rejected");
r = await worker.fetch(tg({ update_id: 2, message: { chat: { id: 7 }, text: "/add TSLA" } }), env, ctx);
if (r.status !== 200 || store.size) fail("stranger must be ignored quietly");
r = await worker.fetch(tg({ update_id: 3, message: { chat: { id: 42 }, text: "hello" } }), env, ctx);
if (store.size) fail("non-commands are not queued");
r = await worker.fetch(tg({ update_id: 4, message: { chat: { id: 42 }, text: "/add NVDA" } }), env, ctx);
await Promise.all(pending);
if (!store.has("tg:4")) fail("owner command must be queued");
const dispatch = calls.find((c) => c.url.includes("/actions/workflows/newsroom.yml/dispatches"));
if (!dispatch || JSON.parse(dispatch.body).inputs.task !== "bot") fail("workflow must be dispatched with task=bot");
if (!calls.some((c) => c.url.includes("/sendMessage"))) fail("owner must get an acknowledgement");
// dashboard lock
r = await worker.fetch(new Request("https://w.dev/data.json"), env, ctx);
if (r.status !== 404) fail("locked dashboard must 404 without the key");
r = await worker.fetch(new Request("https://w.dev/?k=open"), env, ctx);
if (r.status !== 302 || !(r.headers.get("Set-Cookie") || "").includes("nr_k=open")) fail("key must set the cookie");
store.set("data.json", '{"ok":1}');
r = await worker.fetch(new Request("https://w.dev/data.json", { headers: { Cookie: "nr_k=open" } }), env, ctx);
if (r.status !== 200 || (await r.text()) !== '{"ok":1}') fail("cookie must open data.json");
console.log("worker ok");
