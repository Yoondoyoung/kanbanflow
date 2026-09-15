import bleach
from markdown_it import MarkdownIt

ALLOWED_TAGS = [
    "p",
    "br",
    "strong",
    "em",
    "del",
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
    "table",
    "thead",
    "tbody",
    "tr",
    "th",
    "td",
]
ALLOWED_ATTRIBUTES = {"a": ["href", "title"]}
ALLOWED_PROTOCOLS = ["http", "https", "mailto"]

_md = MarkdownIt("commonmark", {"html": False, "linkify": False})


def render_markdown(text: str | None) -> str:
    if not text:
        return ""
    return bleach.clean(
        _md.render(text),
        tags=ALLOWED_TAGS,
        attributes=ALLOWED_ATTRIBUTES,
        protocols=ALLOWED_PROTOCOLS,
        strip=False,
    )
