"""Tiny Tiny RSS integration: top/recent stories of the day.

Uses the TTRSS JSON API (a single ``POST {url}/api/`` endpoint). The API must be
enabled server-side (Preferences -> "Enable API access"). We log in for a
session id, fetch the "Fresh" feed by default, and normalize headlines into
``FeedItem``s. On session expiry we re-login once and retry.
"""

from __future__ import annotations

from datetime import datetime

import httpx

from ..models import FeedItem
from .base import Integration


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

    def fetch(self) -> list[FeedItem]:
        self._error = None
        verify = bool(self.settings.get("verify_tls", True))
        try:
            with httpx.Client(timeout=15.0, verify=verify) as client:
                sid = self._login(client)
                try:
                    headlines = self._get_headlines(client, sid)
                except RuntimeError as exc:
                    # Session may have expired mid-flight: re-login once, retry.
                    if "NOT_LOGGED_IN" in str(exc):
                        sid = self._login(client)
                        headlines = self._get_headlines(client, sid)
                    else:
                        raise
        except Exception as exc:  # noqa: BLE001 - surface any failure in the panel
            self._error = str(exc)
            return []

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
                )
            )
        return items
