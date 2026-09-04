import os
import re
from typing import Any

import requests
import trafilatura
from bs4 import BeautifulSoup
from dotenv import load_dotenv
from langchain.tools import tool
from readability import Document
from requests import Response
from tavily import TavilyClient


def _get_tavily_client() -> TavilyClient:
    """Create a Tavily client from the local environment."""
    load_dotenv()
    api_key = os.getenv("TAVILY_API_KEY")
    if not api_key:
        raise RuntimeError("TAVILY_API_KEY is not set")
    return TavilyClient(api_key=api_key)


@tool
def web_search(query: str) -> str:
    """Search the web for recent, reliable information with Tavily.

    Args:
        query (str): The topic to search for.

    Returns:
        A formatted list of titles, URLs, and content snippets.
    """
    results: dict[str, Any] = _get_tavily_client().search(
        query=query, max_results=5, timeout=30
    )

    out: list[str] = []

    for result in results["results"]:
        out.append(
            f"Title: {result['title']}\n"
            f"URL: {result['url']}\n"
            f"Snippet: {result['content'][:300]}\n"
        )

    return "\n----\n".join(out)


@tool
def scrape_url(url: str) -> str:
    """Extract readable content from a URL with multiple fallback strategies.

    Args:
        url: The HTTP or HTTPS page to retrieve.

    Returns:
        Cleaned page text or an agent-readable error message.
    """

    headers: dict[str, str] = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0 Safari/537.36"
        ),
        "Accept-Language": "en-US,en;q=0.9",
        "Referer": "https://www.google.com/",
    }

    try:
        # ── Fetch page ─────────────────────────────────────
        response: Response = requests.get(url, headers=headers, timeout=15)

        response.raise_for_status()

        html: str = response.text

        # ──────────────────────────────────────────────────
        # Strategy 1 → trafilatura (BEST for articles/blogs)
        # ──────────────────────────────────────────────────
        extracted: str | None = trafilatura.extract(
            html, include_comments=False, include_tables=False
        )

        if extracted and len(extracted.strip()) > 200:
            cleaned: str = re.sub(r"\s+", " ", extracted)
            return cleaned[:5000]

        # ──────────────────────────────────────────────────
        # Strategy 2 → readability
        # ──────────────────────────────────────────────────
        doc: Document = Document(html)
        clean_html: Any = doc.summary()

        soup: BeautifulSoup = BeautifulSoup(clean_html, "html.parser")

        for tag in soup(
            ["script", "style", "nav", "footer", "header", "aside", "form"]
        ):
            tag.decompose()

        text: str = soup.get_text(separator=" ", strip=True)

        if text and len(text.strip()) > 200:
            cleaned: str = re.sub(r"\s+", " ", text)
            return cleaned[:5000]

        # ──────────────────────────────────────────────────
        # Strategy 3 → fallback full page extraction
        # ──────────────────────────────────────────────────
        soup: BeautifulSoup = BeautifulSoup(html, "html.parser")

        for tag in soup(
            ["script", "style", "nav", "footer", "header", "aside", "form"]
        ):
            tag.decompose()

        text: str = soup.get_text(separator=" ", strip=True)

        cleaned: str = re.sub(r"\s+", " ", text)

        if cleaned:
            return cleaned[:5000]

        return "Could not extract meaningful content from the page."

    except requests.exceptions.Timeout:
        return "Request timed out while scraping the URL."

    except requests.exceptions.HTTPError:
        return "HTTP error occurred while scraping the URL."

    except Exception:
        return "Could not scrape URL due to an unexpected extraction error."
