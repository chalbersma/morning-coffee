"""Tiny Tiny RSS integration: top/recent stories, with mark-as-read.

Uses the TTRSS JSON API (a single ``POST {url}/api/`` endpoint). The API must be
enabled server-side (Preferences -> "Enable API access"). We log in for a
session id, fetch the "Fresh" feed by default, and normalize headlines into
``FeedItem``s. Stories can be marked read individually (``updateArticle``) or all
at once (``catchupFeed``). On session expiry we re-login once and retry.
"""

from __future__ import annotations

from datetime import datetime

import httpx

from ..models import FeedItem
from ..ui.icons import CHECK_GLYPH, ICON_FONT
from .base import BulkAction, FeedTab, Integration, ItemAction, Tab


class TtrssIntegration(Integration):
    name = "Top Stories"
    config_key = "ttrss"

    def _api_url(self) -> str:
        base = str(self.settings.get("url", "")).rstrip("/")
        if not base:
            raise ValueError("ttrss.url is not configured")
        return f"{base}/api/"

    def _call(self, client: httpx.Client, body: dict) -> dict:
        """POST a JSON op to the API and return the parsed envelope."""
        resp = client.post(self._api_url(), json=body)
        resp.raise_for_status()
        return resp.json()

    def _login(self, client: httpx.Client) -> str:
        payload = {
            "op": "login",
            "user": self.settings.get("username", ""),
            "password": self.settings.get("password", ""),
        }
        data = self._call(client, payload)
        if data.get("status") != 0:
            error = (data.get("content") or {}).get("error", "unknown")
            raise RuntimeError(f"TTRSS login failed: {error}")
        return data["content"]["session_id"]

    def _run(self, fn):
        """Open a client, log in, run ``fn(client, sid)``; retry once on expiry."""
        verify = bool(self.settings.get("verify_tls", True))
        with httpx.Client(timeout=15.0, verify=verify) as client:
            sid = self._login(client)
            try:
                return fn(client, sid)
            except RuntimeError as exc:
                # Session may have expired mid-flight: re-login once, retry.
                if "NOT_LOGGED_IN" in str(exc):
                    return fn(client, self._login(client))
                raise

    def _get_headlines(self, client: httpx.Client, sid: str) -> list[dict]:
        body = {
            "op": "getHeadlines",
            "sid": sid,
            "feed_id": int(self.settings.get("feed_id", -3)),
            "view_mode": "unread",
            "order_by": "feed_dates",
            "limit": int(self.settings.get("limit", 25)),
            "show_excerpt": True,
        }
        data = self._call(client, body)
        if data.get("status") != 0:
            error = (data.get("content") or {}).get("error", "unknown")
            raise RuntimeError(f"TTRSS getHeadlines failed: {error}")
        return data.get("content") or []

    def _update_article(self, client: httpx.Client, sid: str, ids: list) -> None:
        """Mark the given article ids read (field=2 unread, mode=0 -> false)."""
        body = {
            "op": "updateArticle",
            "sid": sid,
            "article_ids": ",".join(str(i) for i in ids),
            "mode": 0,
            "field": 2,
        }
        data = self._call(client, body)
        if data.get("status") != 0:
            error = (data.get("content") or {}).get("error", "unknown")
            raise RuntimeError(f"TTRSS updateArticle failed: {error}")

    def _catchup(self, client: httpx.Client, sid: str, feed_id: int) -> None:
        """Mark an entire feed read."""
        body = {"op": "catchupFeed", "sid": sid, "feed_id": feed_id, "is_cat": False}
        data = self._call(client, body)
        if data.get("status") != 0:
            error = (data.get("content") or {}).get("error", "unknown")
            raise RuntimeError(f"TTRSS catchupFeed failed: {error}")

    def fetch(self) -> list[FeedItem]:
        headlines = self._run(self._get_headlines)
        items: list[FeedItem] = []
        for h in headlines:
            updated = h.get("updated")
            ts = datetime.fromtimestamp(updated) if isinstance(updated, (int, float)) else None
            feed_title = h.get("feed_title") or ""
            excerpt = h.get("excerpt") or ""
            subtitle = " — ".join(part for part in (feed_title, excerpt) if part)
            items.append(
                FeedItem(
                    title=h.get("title", "(untitled)"),
                    subtitle=subtitle,
                    url=h.get("link"),
                    timestamp=ts,
                    source=self.name,
                    meta={"article_id": h.get("id")},
                )
            )
        return items

    def mark_read(self, item: FeedItem) -> None:
        """Mark a single story read. Raises on error."""
        aid = item.meta.get("article_id")
        if aid is None:
            raise RuntimeError("article has no id")
        self._run(lambda c, sid: self._update_article(c, sid, [aid]))

    def mark_all_read(self) -> None:
        """Mark the whole configured feed read. Raises on error."""
        feed_id = int(self.settings.get("feed_id", -3))
        self._run(lambda c, sid: self._catchup(c, sid, feed_id))

    def tabs(self) -> list[Tab]:
        return [
            FeedTab(
                title=self.name,
                fetch=self.fetch,
                item_action=ItemAction(
                    "read", self.mark_read, icon=CHECK_GLYPH, icon_font=ICON_FONT
                ),
                bulk_action=BulkAction("Mark all read", self.mark_all_read),
            )
        ]
