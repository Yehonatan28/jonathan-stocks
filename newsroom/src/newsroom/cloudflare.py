"""Cloudflare Workers KV over the REST API: the dashboard data and the queue of bot commands."""
from __future__ import annotations

import json
import os
from urllib.parse import quote

from .http import SourceError, get_json, request

BASE = "https://api.cloudflare.com/client/v4/accounts/{acc}/storage/kv/namespaces/{ns}"


class KV:
    def __init__(self, account: str, namespace: str, token: str):
        self.base = BASE.format(acc=account, ns=namespace)
        self.h = {"Authorization": f"Bearer {token}"}

    @classmethod
    def from_env(cls) -> "KV | None":
        acc, ns, tok = (os.environ.get(k, "").strip() for k in ("CLOUDFLARE_ACCOUNT_ID", "CF_KV_NAMESPACE_ID",
                                                                "CLOUDFLARE_API_TOKEN"))
        return cls(acc, ns, tok) if (acc and ns and tok) else None

    def put(self, key: str, body: str) -> None:
        request("PUT", f"{self.base}/values/{quote(key, safe='')}", data=body.encode("utf-8"),
                headers={**self.h, "Content-Type": "application/json"}, timeout=20, retries=2)

    def get(self, key: str) -> str | None:
        try:
            return request("GET", f"{self.base}/values/{quote(key, safe='')}", headers=self.h,
                           timeout=15, retries=1).text
        except SourceError as exc:
            if "404" in str(exc):
                return None
            raise

    def delete(self, key: str) -> None:
        request("DELETE", f"{self.base}/values/{quote(key, safe='')}", headers=self.h, timeout=15, retries=1)

    def keys(self, prefix: str) -> list[str]:
        d = get_json(f"{self.base}/keys", params={"prefix": prefix, "limit": 1000}, headers=self.h,
                     timeout=15, retries=1)
        return [k["name"] for k in d.get("result", [])]


def take_bot_updates(kv: KV) -> list[dict]:
    """Updates the Worker queued (keys tg:<update_id>), oldest first. Each is deleted once read,
    so a command is handled exactly once even if the next run overlaps."""
    out = []
    for key in sorted(kv.keys("tg:"), key=lambda k: int(k.split(":", 1)[1]) if k.split(":", 1)[1].isdigit() else 0):
        raw = kv.get(key)
        kv.delete(key)
        if raw:
            try:
                out.append(json.loads(raw))
            except ValueError:
                continue
    return out
