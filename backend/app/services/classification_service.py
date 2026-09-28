"""Rule-based classification for email tracking requests.

Exact human reads cannot be proven from pixel loads. This module estimates
whether a request looks automated, proxy/uncertain, or possibly human.
"""

from __future__ import annotations

import hashlib
import ipaddress
import re
from dataclasses import dataclass
from datetime import datetime, timezone

from app.models.enums import SignalClassification

SCANNER_UA_PATTERNS = [
    r"googleimageproxy",
    r"ggpht\.com",
    r"yahoo.*mail",
    r"yahoomailproxy",
    r"proofpoint",
    r"barracuda",
    r"mimecast",
    r"messagelabs",
    r"symantec",
    r"trendmicro",
    r"spamassassin",
    r"mailscanner",
    r"security.?scanner",
    r"url.?filter",
    r"safelinks",
    r"microsoft.?office",
    r"outlook-ios",
    r"curl/",
    r"wget/",
    r"python-requests",
    r"go-http-client",
    r"java/",
    r"libwww",
    r"bot\b",
    r"crawler",
    r"spider",
    r"preview",
    r"facebookexternalhit",
    r"slackbot",
    r"twitterbot",
    r"linkedinbot",
]

PROXY_HEADER_HINTS = (
    "via",
    "x-forwarded-for",
    "forwarded",
    "cf-connecting-ip",
    "true-client-ip",
)


@dataclass
class RequestContext:
    client_ip: str | None = None
    user_agent: str | None = None
    referrer: str | None = None
    method: str = "GET"
    range_header: str | None = None
    forwarded_for: str | None = None
    via_header: str | None = None
    sent_at: datetime | None = None
    prior_request_count: int = 0
    prior_ip_hashes: set[str] | None = None
    prior_user_agents: set[str] | None = None
    current_ip_hash: str | None = None
    automated_window_seconds: float = 30.0


@dataclass
class ClassificationResult:
    classification: str
    confidence: float
    reasons: list[str]
    seconds_after_send: float | None


def hash_ip(ip: str | None, secret: str) -> str | None:
    if not ip:
        return None
    try:
        ipaddress.ip_address(ip.strip())
    except ValueError:
        return None
    digest = hashlib.sha256(f"{secret}:{ip.strip()}".encode("utf-8")).hexdigest()
    return digest


def network_prefix(ip: str | None) -> str | None:
    if not ip:
        return None
    try:
        addr = ipaddress.ip_address(ip.strip())
    except ValueError:
        return None
    if isinstance(addr, ipaddress.IPv4Address):
        network = ipaddress.ip_network(f"{addr}/24", strict=False)
        return str(network)
    network = ipaddress.ip_network(f"{addr}/48", strict=False)
    return str(network)


def _ua_matches_scanner(user_agent: str | None) -> str | None:
    if not user_agent:
        return "missing_user_agent"
    lowered = user_agent.lower()
    for pattern in SCANNER_UA_PATTERNS:
        if re.search(pattern, lowered):
            return f"scanner_ua:{pattern}"
    return None


def classify_request(ctx: RequestContext) -> ClassificationResult:
    """Only the first few seconds after send count as an automated open.

    Mailbox image proxies (Gmail, Outlook) fetch pixels immediately. A request
    after that window is recorded as an open, whatever the user-agent is.
    """
    seconds_after_send: float | None = None
    now = datetime.now(timezone.utc)
    if ctx.sent_at is not None:
        sent = ctx.sent_at
        if sent.tzinfo is None:
            sent = sent.replace(tzinfo=timezone.utc)
        seconds_after_send = max(0.0, (now - sent).total_seconds())

    window = ctx.automated_window_seconds
    if seconds_after_send is not None and seconds_after_send < window:
        return ClassificationResult(
            classification=SignalClassification.AUTOMATED.value,
            confidence=0.9,
            reasons=[f"within_{int(window)}s_of_send"],
            seconds_after_send=seconds_after_send,
        )
    if seconds_after_send is not None:
        return ClassificationResult(
            classification=SignalClassification.POSSIBLE_HUMAN.value,
            confidence=0.7,
            reasons=["after_automated_window"],
            seconds_after_send=seconds_after_send,
        )
    return ClassificationResult(
        classification=SignalClassification.PROXY_OR_UNCERTAIN.value,
        confidence=0.45,
        reasons=["missing_send_time"],
        seconds_after_send=None,
    )


def strongest_classification(values: list[str]) -> str:
    order = {
        SignalClassification.POSSIBLE_HUMAN.value: 3,
        SignalClassification.PROXY_OR_UNCERTAIN.value: 2,
        SignalClassification.AUTOMATED.value: 1,
    }
    if not values:
        return "none"
    return max(values, key=lambda item: order.get(item, 0))
