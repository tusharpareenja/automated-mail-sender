from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from uuid import uuid4

from app.models.enums import SignalClassification
from app.services.classification_service import (
    RequestContext,
    classify_request,
    hash_ip,
    network_prefix,
    strongest_classification,
)
from app.services.tracking_service import inject_tracking, is_safe_url, open_label_from_requests


def test_open_redirect_protection():
    assert is_safe_url("https://example.com/path")
    assert not is_safe_url("javascript:alert(1)")
    assert not is_safe_url("/relative")


def test_tracking_rewrites_links_and_adds_pixel():
    email = SimpleNamespace(id=uuid4(), tracking_token="tok_abc")
    html, links = inject_tracking(
        '<html><body><p><a href="https://example.com/offer">Offer</a></p></body></html>',
        "http://localhost:8000",
        email,
    )
    assert "https://example.com/offer" not in html
    assert "/t/c/" in html
    assert "/t/o/tok_abc.png" in html
    assert html.index("/t/o/tok_abc.png") < html.lower().index("</body>")
    assert html.rstrip().lower().endswith("</html>")
    assert len(links) == 1
    assert links[0].destination_url == "https://example.com/offer"


def test_inject_tracking_rewrites_asset_placeholders():
    email = SimpleNamespace(id=uuid4(), tracking_token="tok_asset")
    img_id = uuid4()
    pdf_id = uuid4()
    html, links = inject_tracking(
        '<html><body><p>{{asset_img_abc123}}</p><a href="{{asset_link_pdf999}}">PDF</a></body></html>',
        "https://track.example",
        email,
        assets=[
            SimpleNamespace(
                id=img_id,
                placeholder_key="asset_img_abc123",
                kind="image",
                original_filename="hero.png",
            ),
            SimpleNamespace(
                id=pdf_id,
                placeholder_key="asset_link_pdf999",
                kind="pdf",
                original_filename="deck.pdf",
            ),
        ],
        asset_tokens={img_id: "img-token-1", pdf_id: "pdf-token-1"},
    )
    assert 'src="https://track.example/t/a/img-token-1"' in html
    assert "/t/c/" in html
    assert any(getattr(link, "asset_id", None) == pdf_id for link in links)


def test_hash_ip_never_stores_raw():
    digest = hash_ip("203.0.113.10", "secret")
    assert digest is not None
    assert "203.0.113.10" not in digest
    assert network_prefix("203.0.113.10") == "203.0.113.0/24"
    assert hash_ip("not-an-ip", "secret") is None


def test_classify_scanner_and_early_open_as_automated():
    sent = datetime.now(timezone.utc) - timedelta(seconds=5)
    result = classify_request(
        RequestContext(
            client_ip="8.8.8.8",
            user_agent="Mozilla/5.0 GoogleImageProxy",
            sent_at=sent,
            automated_window_seconds=30,
        )
    )
    assert result.classification == SignalClassification.AUTOMATED.value
    assert any("scanner_ua" in reason or "within_30s" in reason for reason in result.reasons)


def test_classify_delayed_scanner_as_open_not_automated():
    sent = datetime.now(timezone.utc) - timedelta(minutes=5)
    result = classify_request(
        RequestContext(
            client_ip="8.8.8.8",
            user_agent="Mozilla/5.0 GoogleImageProxy",
            sent_at=sent,
            automated_window_seconds=30,
        )
    )
    assert result.classification != SignalClassification.AUTOMATED.value


def test_classify_delayed_browser_as_possible_human():
    sent = datetime.now(timezone.utc) - timedelta(minutes=5)
    result = classify_request(
        RequestContext(
            client_ip="203.0.113.50",
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0",
            sent_at=sent,
            prior_request_count=1,
            prior_ip_hashes={"otherhash"},
            current_ip_hash="currenthash",
            automated_window_seconds=30,
        )
    )
    assert result.classification == SignalClassification.POSSIBLE_HUMAN.value


def test_strongest_and_open_labels():
    assert strongest_classification(
        ["automated", "possible_human", "proxy_or_uncertain"]
    ) == "possible_human"
    assert open_label_from_requests(["automated"]) == "likely_automated"
    assert open_label_from_requests(["possible_human"]) == "opened"
    assert open_label_from_requests(["automated", "opened"]) == "opened"
    assert open_label_from_requests([]) == "none"


def test_asset_storage_rejects_bad_type(tmp_path, monkeypatch):
    from app.core.config import Settings
    from app.core.exceptions import ValidationError
    from app.services import asset_storage

    settings = Settings(
        secret_key="x" * 64,
        encryption_key="y" * 32,
        database_url="postgresql+asyncpg://u:p@localhost/db",
        asset_storage_dir=str(tmp_path),
    )
    try:
        asset_storage.save_asset_bytes(
            settings,
            uuid4(),
            "note.exe",
            b"MZ\x90\x00not-a-real-pe",
            "application/octet-stream",
        )
        assert False, "expected ValidationError"
    except ValidationError:
        pass


def test_asset_storage_accepts_png(tmp_path):
    from app.core.config import Settings
    from app.services import asset_storage

    settings = Settings(
        secret_key="x" * 64,
        encryption_key="y" * 32,
        database_url="postgresql+asyncpg://u:p@localhost/db",
        asset_storage_dir=str(tmp_path),
        azure_storage_connection_string="",
    )
    png = (
        b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
        b"\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc\x00\x01"
        b"\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
    )
    saved = asset_storage.save_asset_bytes(settings, uuid4(), "pixel.png", png, "image/png")
    assert saved["kind"] == "image"
    assert saved["placeholder_key"].startswith("asset_img_")
    assert saved.get("storage") == "local"
    assert saved["absolute_path"].is_file()
