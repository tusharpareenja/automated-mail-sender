import html
import re
from html.parser import HTMLParser

import bleach

from app.core.exceptions import AppError

VARIABLE_RE = re.compile(r"\{\{\s*([a-zA-Z0-9_]+)\s*\}\}")

ALLOWED_TAGS = [
    "a",
    "b",
    "blockquote",
    "br",
    "div",
    "em",
    "h1",
    "h2",
    "h3",
    "h4",
    "hr",
    "i",
    "img",
    "li",
    "ol",
    "p",
    "span",
    "strong",
    "table",
    "tbody",
    "td",
    "th",
    "thead",
    "tr",
    "u",
    "ul",
]
ALLOWED_ATTRS = {
    "*": ["class", "align"],
    "a": ["href", "title", "target", "rel"],
    "img": ["src", "alt", "width", "height", "border"],
    "table": ["width", "cellpadding", "cellspacing", "border", "role", "align"],
    "td": ["width", "valign", "align", "colspan"],
}
BLOCK_TAG_RE = re.compile(r"<(p|div|br|h[1-6]|table|ul|ol|li|hr)\b", re.I)
SIGNOFF_RE = re.compile(r"\b(best regards|kind regards|warm regards|sincerely|thanks,|thank you,)\b", re.I)


class _TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []

    def handle_data(self, data: str) -> None:
        self.parts.append(data)

    def handle_starttag(self, tag: str, attrs) -> None:
        if tag in {"p", "div", "tr", "h1", "h2", "h3", "li"}:
            self.parts.append("\n")
        elif tag == "br":
            self.parts.append("\n")


def sanitize_html(raw: str) -> str:
    cleaned = bleach.clean(
        raw,
        tags=ALLOWED_TAGS,
        attributes=ALLOWED_ATTRS,
        strip=True,
    )
    if "<script" in raw.lower() or "javascript:" in raw.lower():
        raise AppError("unsafe_html", "Template HTML contains disallowed content", 400)
    return cleaned


def extract_variables(*parts: str) -> list[str]:
    found: set[str] = set()
    for part in parts:
        found.update(VARIABLE_RE.findall(part or ""))
    return sorted(found)


def html_to_text(raw_html: str) -> str:
    parser = _TextExtractor()
    parser.feed(raw_html)
    text = "".join(parser.parts)
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"\n[ \t]+", "\n", text)
    text = re.sub(r"[ \t]{2,}", " ", text)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def plaintext_to_html(text: str) -> str:
    chunks = [part.strip() for part in re.split(r"\n\s*\n", text.strip()) if part.strip()]
    if not chunks:
        return "<p></p>"
    blocks: list[str] = []
    for chunk in chunks:
        lines = [line.rstrip() for line in chunk.split("\n") if line.strip()]
        if all(re.match(r"^[-*•]\s+", line) for line in lines) and len(lines) > 1:
            items = "".join(f"<li>{_inline_html(re.sub(r'^[-*•]\s+', '', line))}</li>" for line in lines)
            blocks.append(f"<ul style='margin:0 0 16px;padding-left:20px;'>{items}</ul>")
            continue
        blocks.append(
            "<p style='margin:0 0 16px;'>"
            + "<br>".join(_inline_html(line) for line in lines)
            + "</p>"
        )
    return "".join(blocks)


def _inline_html(text: str) -> str:
    return html.escape(text)


def ensure_html_blocks(content: str) -> str:
    raw = (content or "").strip()
    if not raw:
        return "<p></p>"
    if BLOCK_TAG_RE.search(raw):
        return raw
    return plaintext_to_html(raw)


def wrap_outbound_email(
    html_body: str,
    text_body: str = "",
    *,
    from_name: str = "",
    company: str = "",
    physical_address: str = "",
) -> tuple[str, str]:
    inner = ensure_html_blocks(html_body)
    has_signoff = bool(SIGNOFF_RE.search(inner) or SIGNOFF_RE.search(text_body or ""))
    signoff_name = (from_name or "").strip()
    signoff_company = (company or "").strip()
    if not has_signoff and (signoff_name or signoff_company):
        lines = ["Best regards,"]
        if signoff_name:
            lines.append(html.escape(signoff_name))
        if signoff_company:
            lines.append(html.escape(signoff_company))
        inner += (
            "<p style='margin:28px 0 0;color:#0a0b0d;'>"
            + "<br>".join(lines)
            + "</p>"
        )
    address = html.escape((physical_address or "").strip())
    footer_bits = [
        'If you no longer want emails from us, <a href="{{unsubscribe_url}}" style="color:#5b616e;">unsubscribe here</a>.'
    ]
    if address:
        footer_bits.append(address)
    footer = (
        "<p style='margin:32px 0 0;padding-top:16px;border-top:1px solid #dee1e6;"
        "font-size:12px;line-height:1.5;color:#7c828a;'>"
        + "<br>".join(footer_bits)
        + "</p>"
    )
    wrapped = f"""<!DOCTYPE html>
<html lang="en">
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"></head>
<body style="margin:0;padding:0;background:#f7f7f7;">
  <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#f7f7f7;padding:24px 12px;">
    <tr>
      <td align="center">
        <table role="presentation" width="560" cellpadding="0" cellspacing="0" style="width:560px;max-width:100%;background:#ffffff;border-radius:16px;">
          <tr>
            <td style="padding:32px 28px;font-family:Arial,Helvetica,sans-serif;font-size:16px;line-height:1.65;color:#0a0b0d;">
              {inner}
              {footer}
            </td>
          </tr>
        </table>
      </td>
    </tr>
  </table>
</body>
</html>"""
    text = (text_body or "").strip() or html_to_text(inner)
    if not has_signoff and (signoff_name or signoff_company):
        text = text.rstrip() + "\n\nBest regards,"
        if signoff_name:
            text += f"\n{signoff_name}"
        if signoff_company:
            text += f"\n{signoff_company}"
    text += "\n\nUnsubscribe: {{unsubscribe_url}}"
    if physical_address:
        text += f"\n{physical_address.strip()}"
    return wrapped, text


def render_template(text: str, context: dict[str, str]) -> str:
    def replace(match: re.Match[str]) -> str:
        key = match.group(1)
        value = context.get(key, "")
        return html.escape(str(value)) if "<" in text and "{{" in text else str(value)

    def lookup(match: re.Match[str]) -> str | None:
        key = match.group(1)
        # Asset placeholders are rewritten later into tracked image URLs.
        if key.startswith("asset_"):
            return match.group(0)
        return None

    # Escape substitutions in HTML bodies; leave plaintext as-is.
    if "<" in text:

        def html_replace(match: re.Match[str]) -> str:
            preserved = lookup(match)
            if preserved is not None:
                return preserved
            return html.escape(str(context.get(match.group(1), ""))).replace("\n", "<br>")

        return VARIABLE_RE.sub(html_replace, text)

    def text_replace(match: re.Match[str]) -> str:
        preserved = lookup(match)
        if preserved is not None:
            return preserved
        return str(context.get(match.group(1), ""))

    return VARIABLE_RE.sub(text_replace, text)


def default_signoff(from_name: str = "", company: str = "") -> str:
    lines = ["Best regards,"]
    if from_name.strip():
        lines.append(from_name.strip())
    if company.strip():
        lines.append(company.strip())
    return "\n".join(lines)


def apply_sender_context(
    context: dict[str, str],
    *,
    from_name: str = "",
    company: str = "",
) -> dict[str, str]:
    filled = dict(context)
    if not str(filled.get("signoff") or "").strip():
        filled["signoff"] = default_signoff(from_name, company)
    if not str(filled.get("opener") or "").strip():
        lead_company = str(filled.get("company") or company or "your company")
        industry = str(filled.get("industry") or "your space")
        filled["opener"] = (
            f"Saw that {lead_company} is active in {industry} — "
            "figured this might be relevant to your team."
        )
    return filled


def lead_context(lead) -> dict[str, str]:
    context = {
        "email": lead.email or "",
        "first_name": lead.first_name or "",
        "last_name": lead.last_name or "",
        "company": lead.company or "",
        "title": lead.title or "",
        "industry": lead.industry or "",
        "website": lead.website or "",
        "country": getattr(lead, "country", None) or "",
        "study_opportunity": getattr(lead, "study_opportunity", None) or "",
    }
    custom = lead.custom_fields or {}
    for key, value in custom.items():
        context[str(key)] = "" if value is None else str(value)
    return context
