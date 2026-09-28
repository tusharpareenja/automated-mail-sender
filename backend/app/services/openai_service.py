import json
import logging
import re
from typing import Any

from app.core.config import Settings

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You personalize one outbound sales email so it reads as a note to a single person, not a bulk blast.
You receive the sender's template, their instructions, and one lead (name, title, company, website, and any extra fields).

Search the public web for one news item about that company from the last 30 days only. Use the company website domain so you do not pick a different company with a similar name.
The item must be something you can point to on a page, with a real date inside the last 30 days. If you are unsure of a product name, guide title, or feature, or the only items are older than 30 days or undated, set company_note to an empty string. Never guess or paraphrase a detail you cannot verify.

Rules:
- subject: one short line a busy person understands immediately. Plain words, no jargon, and do not use "mind-set", "mindset", or "mind-set map". Do not use the pattern "Name, a ... for Company". Under 60 characters. Example shape: "Before &Collar's next launch".
- opener: exactly one sentence. Do not mention the news item. Do not repeat the person's name if the template already says hello. Do not add a second sentence.
- company_note: exactly one sentence with the dated fact, or an empty string. Do not put this sentence in opener or anywhere else.
- The ask must speak to the reader as "you". Never use their job title as the subject. Write "Would you be open to a 20-minute call" and not "Would Co-Founder and CMO be open".
- Do not write a sign-off. No "Best", "Best regards", "Thanks", or the sender's name at the end. The mail system adds one sign-off.
- Keep the sender's offer. Do not replace it with a different pitch.
- Keep every {{asset_img_...}}, {{asset_link_...}}, {{unsubscribe_url}}, and {{view_url}} placeholder exactly as written.
- Return JSON only, with keys subject, opener, company_note, signoff, html_body, text_body. Set signoff to an empty string.
"""

_LOCKED_RE = re.compile(
    r"\{\{\s*(asset_[a-zA-Z0-9_]+|unsubscribe_url|view_url)\s*\}\}"
)


def generate_personalization(
    settings: Settings,
    lead_fields: dict[str, Any],
    instructions: str | None,
    *,
    subject: str = "",
    html_body: str = "",
    text_body: str = "",
) -> dict[str, str]:
    """Async wrapper used by previews. The OpenAI client call is synchronous underneath."""
    return generate_personalization_sync(
        settings,
        lead_fields,
        instructions,
        subject=subject,
        html_body=html_body,
        text_body=text_body,
    )


def generate_personalization_sync(
    settings: Settings,
    lead_fields: dict[str, Any],
    instructions: str | None,
    *,
    subject: str = "",
    html_body: str = "",
    text_body: str = "",
) -> dict[str, str]:
    if not settings.openai_api_key:
        return _fallback(lead_fields)

    lead = {
        k: v
        for k, v in lead_fields.items()
        if v and k not in {"html_body", "text_body", "subject", "opener", "signoff", "company_note"}
    }
    user_prompt = json.dumps(
        {
            "lead": lead,
            "instructions": instructions
            or "Make this feel personally written to this person, using their role and company.",
            "template": {
                "subject": subject,
                "html_body": html_body,
                "text_body": text_body,
            },
        }
    )
    try:
        from openai import OpenAI

        client = OpenAI(api_key=settings.openai_api_key, timeout=90)
        response = client.responses.create(
            model=settings.openai_model or "gpt-5.6-luna",
            tools=[{"type": "web_search"}],
            reasoning={"effort": "low"},
            input=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
        )
        parsed = parse_personalization(
            getattr(response, "output_text", "") or "",
            source_html=html_body,
            source_text=text_body,
            lead_fields=lead_fields,
        )
        if not parsed.get("opener") and not parsed.get("subject"):
            return _fallback(lead_fields)
        return parsed
    except Exception as exc:
        logger.info(
            "ai_generation_failed",
            extra={"event": "ai_generation_failed", "error": type(exc).__name__},
        )
        return _fallback(lead_fields)


def parse_personalization(
    raw: str,
    *,
    source_html: str = "",
    source_text: str = "",
    lead_fields: dict[str, Any] | None = None,
) -> dict[str, str]:
    data = _extract_json(raw)
    fields = lead_fields or {}
    company_note = _first_sentence(str(data.get("company_note") or ""))[:400]
    opener = _first_sentence(str(data.get("opener") or ""))[:500]
    opener = _drop_overlap(opener, company_note)
    subject = _clean_subject(str(data.get("subject") or ""), fields)
    html_body = _address_the_reader(str(data.get("html_body") or "").strip(), str(fields.get("title") or ""))
    text_body = _address_the_reader(str(data.get("text_body") or "").strip(), str(fields.get("title") or ""))
    html_body = _strip_trailing_signoff(html_body)
    text_body = _strip_trailing_signoff(text_body)

    if html_body and not _placeholders_kept(source_html, html_body):
        html_body = ""
    if text_body and not _placeholders_kept(source_text, text_body):
        text_body = ""
    if html_body and ("<script" in html_body.lower() or "javascript:" in html_body.lower()):
        html_body = ""

    result = {
        "opener": opener,
        "company_note": company_note,
        "signoff": "",
    }
    if subject:
        result["subject"] = subject
    if html_body:
        result["html_body"] = html_body[:20000]
    if text_body:
        result["text_body"] = text_body[:8000]
    if not result.get("opener"):
        result = {**_fallback(lead_fields or {}), **{k: v for k, v in result.items() if v}}
    return result


def _fallback(lead_fields: dict[str, Any]) -> dict[str, str]:
    first = str(lead_fields.get("first_name") or "").strip()
    company = str(lead_fields.get("company") or "").strip()
    title = str(lead_fields.get("title") or "").strip()
    if first and company and title:
        opener = f"I wanted to reach out to you as {title} at {company}."
    elif first and company:
        opener = f"I wanted to reach out to you at {company}."
    elif first:
        opener = f"I wanted to share a brief note with you, {first}."
    else:
        opener = "I wanted to share a brief note."
    subject = f"{first}, a note for {company}".strip(" ,") if first or company else ""
    result = {"opener": opener, "signoff": "Best regards", "company_note": ""}
    if subject:
        result["subject"] = subject[:140]
    return result


_BORING_SUBJECT_RE = re.compile(r"^.+,\s+a\s+.+\bfor\b", re.IGNORECASE)
_SIGNOFF_TAIL_RE = re.compile(
    r"(?is)(?:\s|<br\s*/?>)*(?:<p\b[^>]*>\s*)?(?:best regards|kind regards|warm regards|sincerely|thanks|thank you|best),?(?:(?!</p>)[\s\S]){0,160}(?:</p>)?\s*$"
)


def _clean_subject(value: str, lead_fields: dict[str, Any] | None = None) -> str:
    line = " ".join(value.replace("\n", " ").split())
    lowered = line.lower()
    if (
        not line
        or "mind-set" in lowered
        or "mindset" in lowered
        or _BORING_SUBJECT_RE.match(line)
    ):
        company = str((lead_fields or {}).get("company") or "").strip()
        first = str((lead_fields or {}).get("first_name") or "").strip()
        if company:
            line = f"Before {company}'s next launch"
        elif first:
            line = f"A note for {first}"
        else:
            line = ""
    return line[:60]


def _first_sentence(value: str) -> str:
    text = " ".join(value.replace("\n", " ").split()).strip()
    if not text:
        return ""
    match = re.match(r"^(.+?[.!?])(?:\s|$)", text)
    return (match.group(1) if match else text).strip()


def _drop_overlap(opener: str, company_note: str) -> str:
    note = company_note.strip().rstrip(".")
    if opener and note and note.lower() in opener.lower():
        opener = re.sub(re.escape(note), "", opener, count=1, flags=re.IGNORECASE)
        opener = _first_sentence(opener.strip(" ."))
    return opener.strip()


def _address_the_reader(text: str, title: str) -> str:
    title = title.strip()
    if not text or not title:
        return text
    return re.sub(
        rf"\bWould\s+{re.escape(title)}\b",
        f"Would you, as {title},",
        text,
        count=1,
        flags=re.IGNORECASE,
    )


def _strip_trailing_signoff(text: str) -> str:
    current = text.strip()
    previous = None
    while current and current != previous:
        previous = current
        current = _SIGNOFF_TAIL_RE.sub("", current).strip()
    return current


def _placeholders_kept(source: str, rewritten: str) -> bool:
    needed = set(_LOCKED_RE.findall(source or ""))
    if not needed:
        return True
    found = set(_LOCKED_RE.findall(rewritten or ""))
    return needed <= found


def _extract_json(raw: str) -> dict[str, Any]:
    text = (raw or "").strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}")
        if start < 0 or end <= start:
            return {}
        data = json.loads(text[start : end + 1])
    return data if isinstance(data, dict) else {}
