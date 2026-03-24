"""Director web search tool — search the internet and fetch URLs."""

import os
import re
import json
import urllib.request
import urllib.parse


def web_search(query: str, num_results: int = 6) -> dict:
    """
    Search the internet for information.
    Uses Brave Search API if BRAVE_SEARCH_API_KEY is set, otherwise DuckDuckGo fallback.
    """
    try:
        encoded_query = urllib.parse.quote(query)
        brave_key = os.getenv("BRAVE_SEARCH_API_KEY", "")

        if brave_key:
            url = (
                f"https://api.search.brave.com/res/v1/web/search"
                f"?q={encoded_query}&count={num_results}"
            )
            req = urllib.request.Request(
                url,
                headers={
                    "Accept": "application/json",
                    "Accept-Encoding": "gzip",
                    "X-Subscription-Token": brave_key,
                },
            )
            with urllib.request.urlopen(req, timeout=12) as resp:
                data = json.loads(resp.read())
            results = [
                {
                    "title": r.get("title", ""),
                    "url": r.get("url", ""),
                    "description": r.get("description", ""),
                }
                for r in data.get("web", {}).get("results", [])[:num_results]
            ]
            return {"query": query, "source": "brave", "results": results}

        # Fallback: DuckDuckGo Instant Answer API
        url = (
            f"https://api.duckduckgo.com/?q={encoded_query}"
            f"&format=json&no_html=1&skip_disambig=1"
        )
        req = urllib.request.Request(url, headers={"User-Agent": "Director-AI/1.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read())

        results = []
        if data.get("AbstractText"):
            results.append({
                "title": data.get("Heading", query),
                "url": data.get("AbstractURL", ""),
                "description": data.get("AbstractText", ""),
            })
        for topic in data.get("RelatedTopics", [])[:num_results]:
            if isinstance(topic, dict) and topic.get("Text"):
                results.append({
                    "title": topic.get("Text", "")[:120],
                    "url": topic.get("FirstURL", ""),
                    "description": topic.get("Text", ""),
                })

        return {
            "query": query,
            "source": "duckduckgo_fallback",
            "note": "BRAVE_SEARCH_API_KEY eklenerek daha kapsamlı arama yapılabilir.",
            "results": results[:num_results],
        }

    except Exception as e:
        print(f"[DirectorWebSearch] web_search error: {e}")
        return {"error": str(e), "query": query}


def fetch_url(url: str, max_chars: int = 6000) -> dict:
    """
    Fetch and read the textual content of a URL.
    Strips HTML tags, returns plain text.
    """
    try:
        req = urllib.request.Request(
            url, headers={"User-Agent": "Director-AI/1.0"}
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            content_type = resp.headers.get("Content-Type", "")
            raw = resp.read().decode("utf-8", errors="ignore")

        # Strip scripts, styles, then tags
        text = re.sub(r"<script[^>]*>.*?</script>", "", raw, flags=re.DOTALL)
        text = re.sub(r"<style[^>]*>.*?</style>", "", text, flags=re.DOTALL)
        text = re.sub(r"<[^>]+>", " ", text)
        text = re.sub(r"\s+", " ", text).strip()

        return {
            "url": url,
            "content_type": content_type,
            "length": len(text),
            "content": text[:max_chars],
            "truncated": len(text) > max_chars,
        }

    except Exception as e:
        print(f"[DirectorWebSearch] fetch_url error: {e}")
        return {"error": str(e), "url": url}
