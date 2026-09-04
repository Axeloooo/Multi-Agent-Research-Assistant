from unittest.mock import Mock

import pytest

from src.tools import tools


def _response(html: str = "<html><body></body></html>") -> Mock:
    response = Mock()
    response.text = html
    response.raise_for_status.return_value = None
    return response


def test_web_search_requires_api_key_when_invoked(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("TAVILY_API_KEY", raising=False)
    monkeypatch.setattr(tools, "load_dotenv", Mock())

    with pytest.raises(RuntimeError, match="TAVILY_API_KEY is not set"):
        tools.web_search.invoke({"query": "test topic"})


def test_tavily_client_uses_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    client_type = Mock()
    expected_client = Mock()
    client_type.return_value = expected_client
    monkeypatch.setenv("TAVILY_API_KEY", "test-key")
    monkeypatch.setattr(tools, "load_dotenv", Mock())
    monkeypatch.setattr(tools, "TavilyClient", client_type)

    client = tools._get_tavily_client()

    assert client is expected_client
    client_type.assert_called_once_with(api_key="test-key")


def test_web_search_formats_results_and_limits_snippets(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    long_snippet = "x" * 350
    client = Mock()
    client.search.return_value = {
        "results": [
            {
                "title": "First result",
                "url": "https://example.com/first",
                "content": long_snippet,
            },
            {
                "title": "Second result",
                "url": "https://example.com/second",
                "content": "Short summary",
            },
        ]
    }
    monkeypatch.setattr(tools, "_get_tavily_client", lambda: client)

    result = tools.web_search.invoke({"query": "test topic"})

    assert result == (
        "Title: First result\n"
        "URL: https://example.com/first\n"
        f"Snippet: {'x' * 300}\n\n"
        "----\n"
        "Title: Second result\n"
        "URL: https://example.com/second\n"
        "Snippet: Short summary\n"
    )
    client.search.assert_called_once_with(query="test topic", max_results=5, timeout=30)


def test_scrape_url_uses_trafilatura_content(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    extracted = ("Primary   article\ncontent " * 250).strip()
    monkeypatch.setattr(tools.requests, "get", Mock(return_value=_response()))
    monkeypatch.setattr(tools.trafilatura, "extract", Mock(return_value=extracted))

    result = tools.scrape_url.invoke({"url": "https://example.com/article"})

    assert result == " ".join(extracted.split())[:5000]
    assert len(result) <= 5000


def test_scrape_url_falls_back_to_readability(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    readable_text = "Readable article content " * 20
    document = Mock()
    document.summary.return_value = f"<article>{readable_text}</article>"
    monkeypatch.setattr(tools.requests, "get", Mock(return_value=_response()))
    monkeypatch.setattr(tools.trafilatura, "extract", Mock(return_value=None))
    monkeypatch.setattr(tools, "Document", Mock(return_value=document))

    result = tools.scrape_url.invoke({"url": "https://example.com/article"})

    assert result == readable_text.strip()


def test_scrape_url_falls_back_to_full_page(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    page_text = "Fallback page content " * 20
    html = f"<html><script>ignore me</script><main>{page_text}</main></html>"
    document = Mock()
    document.summary.return_value = "<p>Too short</p>"
    monkeypatch.setattr(tools.requests, "get", Mock(return_value=_response(html)))
    monkeypatch.setattr(tools.trafilatura, "extract", Mock(return_value=None))
    monkeypatch.setattr(tools, "Document", Mock(return_value=document))

    result = tools.scrape_url.invoke({"url": "https://example.com/article"})

    assert result == page_text.strip()
    assert "ignore me" not in result


def test_scrape_url_reports_empty_content(monkeypatch: pytest.MonkeyPatch) -> None:
    document = Mock()
    document.summary.return_value = "<html><body></body></html>"
    monkeypatch.setattr(tools.requests, "get", Mock(return_value=_response()))
    monkeypatch.setattr(tools.trafilatura, "extract", Mock(return_value=None))
    monkeypatch.setattr(tools, "Document", Mock(return_value=document))

    result = tools.scrape_url.invoke({"url": "https://example.com/empty"})

    assert result == "Could not extract meaningful content from the page."


def test_scrape_url_reports_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        tools.requests,
        "get",
        Mock(side_effect=tools.requests.exceptions.Timeout),
    )

    result = tools.scrape_url.invoke({"url": "https://example.com/slow"})

    assert result == "Request timed out while scraping the URL."


def test_scrape_url_reports_http_error(monkeypatch: pytest.MonkeyPatch) -> None:
    response = _response()
    response.raise_for_status.side_effect = tools.requests.exceptions.HTTPError(
        "403 Client Error for https://example.com/?token=secret-value"
    )
    monkeypatch.setattr(tools.requests, "get", Mock(return_value=response))

    result = tools.scrape_url.invoke({"url": "https://example.com/forbidden"})

    assert result == "HTTP error occurred while scraping the URL."
    assert "secret-value" not in result


def test_scrape_url_reports_unexpected_extraction_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(tools.requests, "get", Mock(return_value=_response()))
    monkeypatch.setattr(
        tools.trafilatura,
        "extract",
        Mock(side_effect=ValueError("broken extractor: secret-value")),
    )

    result = tools.scrape_url.invoke({"url": "https://example.com/article"})

    assert result == "Could not scrape URL due to an unexpected extraction error."
    assert "secret-value" not in result
