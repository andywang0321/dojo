"""Minimal HTML → plain text for LeetCode problem content (stdlib only).

The output is a seed-statement body: paragraphs, preformatted blocks, and
list items survive; all other markup is stripped. No dependency budget for
BeautifulSoup — LeetCode content is regular enough for a small parser.
"""

from __future__ import annotations

import re
from html.parser import HTMLParser


class HTMLToText(HTMLParser):
    BLOCK_TAGS = {"p", "pre", "ul", "ol", "div", "table", "tr", "blockquote"}
    END_TAGS = BLOCK_TAGS | {"li", "br"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self._out: list[str] = []
        self._in_block = False

    def _open_block(self) -> None:
        if not self._in_block:
            if self._out and not self._out[-1].endswith("\n\n"):
                self._out.append("\n\n")
            self._in_block = True

    def handle_starttag(self, tag: str, attrs) -> None:
        if tag in self.BLOCK_TAGS:
            self._open_block()
        if tag == "li":
            self._open_block()
            self._out.append("* ")
        if tag == "br":
            self._out.append("\n")
            self._in_block = False

    def handle_endtag(self, tag: str) -> None:
        if tag in self.END_TAGS:
            self._out.append("\n")
            self._in_block = False

    def handle_data(self, data: str) -> None:
        if data:
            self._out.append(data)

    def convert(self, html: str) -> str:
        self.feed(html)
        text = "".join(self._out)
        text = text.replace("\xa0", " ")  # &nbsp; → normal space
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text.strip()
