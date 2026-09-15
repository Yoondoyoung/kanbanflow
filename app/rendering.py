import bleach
from markdown_it import MarkdownIt

ALLOWED_TAGS = [
    "p",
    "br",
    "strong",
    "em",
    "del",  # strikethrough, and "table"..."td" below, are inert under the
    "code",
    "pre",
    "blockquote",
    "ul",
    "ol",
    "li",
    "h1",
    "h2",
    "h3",
    "h4",
    "h5",
    "h6",
    "a",
    "hr",
    "table",  # commonmark preset below (no plugins): no Markdown syntax
    "thead",  # reaches these tags today. Kept on the allow-list anyway so a
    "tbody",  # future preset change (GFM tables/strikethrough) needs no
    "tr",  # second edit here — don't take their presence as "supported now".
    "th",
    "td",
]
ALLOWED_ATTRIBUTES = {"a": ["href", "title"]}
ALLOWED_PROTOCOLS = ["http", "https", "mailto"]

_md = MarkdownIt("commonmark", {"html": False, "linkify": False})


def render_markdown(text: str | None) -> str:
    if not text:
        return ""
    # Two nets under different holes, not one: html=False above neutralizes
    # raw HTML in the source, while bleach here constrains tags markdown-it
    # itself generates (e.g. `![alt](x)` -> a live <img>). Removing either
    # leaves a real gap — see test_removing_bleach_would_leak_a_live_tag.
    return bleach.clean(
        _md.render(text),
        tags=ALLOWED_TAGS,
        attributes=ALLOWED_ATTRIBUTES,
        protocols=ALLOWED_PROTOCOLS,
        strip=False,
    )
