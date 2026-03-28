from __future__ import annotations

from html.parser import HTMLParser
from socket import timeout as SocketTimeout
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen


DEFAULT_READ_TIMEOUT_SECONDS = 10
DEFAULT_MAX_READ_BYTES = 262144
DEFAULT_MAX_TEXT_CHARS = 8000


class _BodyTextParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self._parts: list[str] = []

    def handle_data(self, data: str) -> None:
        text = data.strip()
        if text:
            self._parts.append(text)

    def get_text(self) -> str:
        return "\n".join(self._parts)


def read_html(url: str) -> str:
    normalized = url.strip().strip("\"'")
    if not normalized:
        return "ReadHTML error: empty URL."

    parsed = urlparse(normalized)
    if parsed.scheme not in {"http", "https"}:
        return f"ReadHTML error: unsupported URL scheme `{parsed.scheme or 'unknown'}`."

    request = Request(normalized, headers={"User-Agent": "AutoPT/1.0"})
    try:
        with urlopen(request, timeout=DEFAULT_READ_TIMEOUT_SECONDS) as response:  # nosec B310 - URL comes from explicit tool usage
            raw_html = response.read(DEFAULT_MAX_READ_BYTES + 1)
    except HTTPError as exc:
        return f"ReadHTML error: HTTP {exc.code} for {normalized}"
    except (URLError, TimeoutError, SocketTimeout, ValueError) as exc:
        return f"ReadHTML error: {exc}"
    except Exception as exc:  # pragma: no cover - defensive fallback
        return f"ReadHTML error: unexpected failure: {exc}"

    truncated = len(raw_html) > DEFAULT_MAX_READ_BYTES
    html = raw_html[:DEFAULT_MAX_READ_BYTES].decode("utf-8", "ignore")
    parser = _BodyTextParser()
    parser.feed(html)
    text = parser.get_text() or html
    if len(text) > DEFAULT_MAX_TEXT_CHARS:
        text = text[:DEFAULT_MAX_TEXT_CHARS].rstrip() + "\n...[truncated]"
    elif truncated:
        text = text.rstrip() + "\n...[truncated]"
    return text
