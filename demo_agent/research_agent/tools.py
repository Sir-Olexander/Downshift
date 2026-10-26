"""Read-only research tools: web search and page reading.

Tavily is used when TAVILY_API_KEY is set. Without a key the tools fall back to the Wikipedia API,
which needs no key, so the demo always runs. Both are read-only, which keeps replays safe.
"""

from __future__ import annotations

import html
import os
import re
from typing import Any
from urllib.parse import quote, urlsplit, unquote

import httpx

USER_AGENT = "downshift-demo-research-agent/0.1 (+https://github.com/downshift)"
WIKI_API = "https://en.wikipedia.org/w/api.php"

BUILTIN_SCHEMAS: dict[str, dict[str, Any]] = {
    "web_search": {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "The search query."},
            "max_results": {"type": "integer", "description": "How many results to return (1-8).", "default": 5},
        },
        "required": ["query"],
    },
    "read_page": {
        "type": "object",
        "properties": {"url": {"type": "string", "description": "The URL of the page to read."}},
        "required": ["url"],
    },
}


def _strip_html(text: str) -> str:
    text = re.sub(r"(?is)<(script|style|noscript|svg|header|footer|nav)[^>]*>.*?</\1>", " ", text)
    text = re.sub(r"(?s)<[^>]+>", " ", text)
    text = html.unescape(text)
    return re.sub(r"\s+", " ", text).strip()


class SearchTools:
    def __init__(self, tavily_api_key: str | None = None, *, timeout: float = 25.0):
        self.tavily_key = tavily_api_key if tavily_api_key is not None else os.environ.get("TAVILY_API_KEY")
        self.timeout = timeout
        self._http = httpx.Client(timeout=timeout, headers={"User-Agent": USER_AGENT}, follow_redirects=True)

    @property
    def provider(self) -> str:
        return "tavily" if self.tavily_key else "wikipedia"

    # ---- tool definitions ------------------------------------------------------------------
    def tool_defs(self, harness: Any) -> list[dict[str, Any]]:
        """OpenAI tool definitions, with descriptions (and optional schemas) from the harness."""
        defs = []
        for name, schema in BUILTIN_SCHEMAS.items():
            spec = harness.tools.get(name) if harness is not None else None
            if spec is None:
                continue  # a harness may hide a tool by leaving it out
            defs.append({
                "type": "function",
                "function": {
                    "name": name,
                    "description": spec.description,
                    "parameters": spec.parameters or schema,
                },
            })
        return defs

    def call(self, name: str, args: dict[str, Any]) -> Any:
        if name == "web_search":
            return self.web_search(str(args.get("query", "")), int(args.get("max_results") or 5))
        if name == "read_page":
            return self.read_page(str(args.get("url", "")))
        raise ValueError(f"unknown tool {name}")

    # ---- web_search ----------------------------------------------------------------------
    def web_search(self, query: str, max_results: int = 5) -> dict[str, Any]:
        query = query.strip()
        max_results = max(1, min(int(max_results or 5), 8))
        if not query:
            return {"provider": self.provider, "query": query, "results": [], "error": "empty query"}
        if self.tavily_key:
            try:
                return self._tavily_search(query, max_results)
            except Exception as e:  # fall back rather than fail the run
                wiki = self._wiki_search(query, max_results)
                wiki["note"] = f"tavily failed ({type(e).__name__}); used wikipedia"
                return wiki
        return self._wiki_search(query, max_results)

    def _tavily_search(self, query: str, max_results: int) -> dict[str, Any]:
        r = self._http.post(
            "https://api.tavily.com/search",
            json={"api_key": self.tavily_key, "query": query, "max_results": max_results, "search_depth": "basic", "include_answer": False},
        )
        r.raise_for_status()
        data = r.json()
        results = [
            {"title": x.get("title", ""), "url": x.get("url", ""), "snippet": (x.get("content") or "")[:600]}
            for x in data.get("results", [])
        ]
        return {"provider": "tavily", "query": query, "results": results}

    def _wiki_search(self, query: str, max_results: int) -> dict[str, Any]:
        params = {
            "action": "query", "format": "json", "generator": "search", "gsrsearch": query,
            "gsrlimit": max_results, "prop": "extracts|info", "exintro": 1, "explaintext": 1,
            "exlimit": max_results, "exchars": 600, "inprop": "url",
        }
        r = self._http.get(WIKI_API, params=params)
        r.raise_for_status()
        pages = (r.json().get("query") or {}).get("pages") or {}
        ordered = sorted(pages.values(), key=lambda p: p.get("index", 0))
        results = [
            {"title": p.get("title", ""), "url": p.get("fullurl") or f"https://en.wikipedia.org/wiki/{quote(p.get('title','').replace(' ', '_'))}", "snippet": re.sub(r"\s+", " ", p.get("extract") or "").strip()[:600]}
            for p in ordered
        ]
        return {"provider": "wikipedia", "query": query, "results": results}

    # ---- read_page -----------------------------------------------------------------------
    def read_page(self, url: str, max_chars: int = 4000) -> dict[str, Any]:
        url = url.strip()
        if not url.startswith(("http://", "https://")):
            return {"url": url, "title": "", "text": "", "error": "read_page needs an http(s) URL"}
        try:
            host = urlsplit(url).netloc.lower()
            if host.endswith("wikipedia.org") and "/wiki/" in url:
                return self._wiki_page(url, max_chars)
            if self.tavily_key:
                try:
                    return self._tavily_extract(url, max_chars)
                except Exception:
                    pass
            return self._fetch_page(url, max_chars)
        except Exception as e:
            return {"url": url, "title": "", "text": "", "error": f"{type(e).__name__}: {e}"[:300]}

    def _wiki_page(self, url: str, max_chars: int) -> dict[str, Any]:
        title = unquote(url.split("/wiki/", 1)[1].split("#", 1)[0]).replace("_", " ")
        r = self._http.get(WIKI_API, params={"action": "query", "format": "json", "prop": "extracts", "explaintext": 1, "titles": title, "redirects": 1})
        r.raise_for_status()
        pages = (r.json().get("query") or {}).get("pages") or {}
        page = next(iter(pages.values()), {})
        text = re.sub(r"\n{3,}", "\n\n", (page.get("extract") or "").strip())
        return {"url": url, "title": page.get("title", title), "text": text[:max_chars], "truncated": len(text) > max_chars}

    def _tavily_extract(self, url: str, max_chars: int) -> dict[str, Any]:
        r = self._http.post("https://api.tavily.com/extract", json={"api_key": self.tavily_key, "urls": [url]})
        r.raise_for_status()
        results = r.json().get("results") or []
        if not results:
            raise RuntimeError("no extract")
        text = re.sub(r"\s+", " ", results[0].get("raw_content") or "").strip()
        return {"url": url, "title": results[0].get("title", ""), "text": text[:max_chars], "truncated": len(text) > max_chars}

    def _fetch_page(self, url: str, max_chars: int) -> dict[str, Any]:
        r = self._http.get(url)
        r.raise_for_status()
        body = r.text
        m = re.search(r"(?is)<title[^>]*>(.*?)</title>", body)
        title = html.unescape(m.group(1)).strip() if m else ""
        text = _strip_html(body)
        return {"url": url, "title": title, "text": text[:max_chars], "truncated": len(text) > max_chars}
