import pytest

from app.core.exceptions import AppError
from app.models.campaign import Campaign
from app.models.enums import CampaignStatus
from app.services.campaign_service import transition
from app.services.lead_service import inspect_csv, suggest_mapping
from app.services.openai_service import _fallback, parse_personalization
from app.services.tracking_service import is_safe_url


def test_preview_replaces_asset_placeholder_with_url():
    from types import SimpleNamespace

    from app.services.asset_service import embed_preview_asset_urls

    asset = SimpleNamespace(
        user_id="u",
        stored_filename="photo.jpg",
        content_type="image/jpeg",
        placeholder_key="asset_img_abc",
    )
    html = '<p>Hi</p><img src="{{asset_img_abc}}" alt="photo.jpg">'

    def fake_url(settings, user_id, stored_filename, content_type):
        return "https://cdn.example/photo.jpg?sig=1&se=2"

    import app.services.asset_service as asset_service

    original = asset_service.blob_preview_url
    asset_service.blob_preview_url = fake_url
    try:
        rendered = embed_preview_asset_urls(None, [asset], html)
    finally:
        asset_service.blob_preview_url = original
    assert "{{asset_img_abc}}" not in rendered
    assert 'src="https://cdn.example/photo.jpg?sig=1&amp;se=2"' in rendered
    assert 'alt="photo.jpg"' in rendered


def test_prospect_email_prefers_work_address():
    from app.services.lead_service import choose_prospect_email, split_person_name

    assert choose_prospect_email("Ada@Acme.com", "ada@gmail.com") == ("ada@acme.com", "work")
    assert choose_prospect_email("", "ada@gmail.com") == ("ada@gmail.com", "personal")
    assert choose_prospect_email("not-an-email", "") is None
    assert split_person_name("Barry Hott") == ("Barry", "Hott")


def test_personalization_requires_news_from_the_last_30_days():
    from app.services.openai_service import SYSTEM_PROMPT

    assert "30 days" in SYSTEM_PROMPT
    assert "12 months" not in SYSTEM_PROMPT


def test_group_name_comes_from_csv_filename():
    from app.services.lead_service import group_name_from_file

    assert group_name_from_file("csv 1.csv") == "csv 1"
    assert group_name_from_file("") == "Imported leads"


def test_valid_and_invalid_transitions():
    campaign = Campaign(name="Test", status=CampaignStatus.DRAFT.value)
    transition(campaign, CampaignStatus.QUEUED)
    assert campaign.status == CampaignStatus.QUEUED.value
    with pytest.raises(AppError):
        transition(campaign, CampaignStatus.DRAFT)


def test_csv_header_mapping():
    mapping = suggest_mapping(["Email Address", "First Name", "Company", "LinkedIn"])
    assert mapping["Email Address"] == "email"
    assert mapping["First Name"] == "first_name"
    assert mapping["Company"] == "company"
    assert mapping["LinkedIn"] == "linkedin"


def test_inspect_csv():
    csv_text = "Email,First Name\nada@example.com,Ada\n"
    result = inspect_csv(csv_text)
    assert result["row_count"] == 1
    assert "Email" in result["headers"]


def test_ai_fallback_does_not_invent_facts():
    result = _fallback({"first_name": "Ada", "company": "Acme"})
    assert "Acme" in result["opener"]
    assert "visited" not in result["opener"].lower()
    assert result["company_note"] == ""


def test_personalization_uses_one_opener_plain_subject_and_no_signoff():
    raw = """
    {
      "subject": "Jordan, a mind-set map for &Collar's next launch",
      "opener": "Saw &Collar's shirts. On September 9, &Collar added a packing guide.",
      "company_note": "On September 9, &Collar added a packing guide.",
      "signoff": "Best, Tushar",
      "html_body": "<p>Hi Jordan,</p><p>Would Co-Founder and CMO at &Collar be open to a call?</p><p>Best,<br>Tushar</p>",
      "text_body": "Would Co-Founder and CMO at &Collar be open?\\n\\nBest,\\nTushar"
    }
    """
    parsed = parse_personalization(
        raw,
        source_html="<p>Hi</p>",
        source_text="Hi",
        lead_fields={"first_name": "Jordan", "company": "&Collar", "title": "Co-Founder and CMO"},
    )
    assert parsed["subject"] == "Before &Collar's next launch"
    assert parsed["opener"] == "Saw &Collar's shirts."
    assert parsed["signoff"] == ""
    assert "Would you, as Co-Founder and CMO," in parsed["html_body"]
    assert "Best" not in parsed["html_body"]
    assert "Tushar" not in parsed["html_body"]


def test_personalization_keeps_asset_placeholders_and_subject():
    raw = """
    {
      "subject": "Priya, the new Lux soap design",
      "opener": "Priya, as a design engineer at Lux, I noticed the new soap design.",
      "company_note": "Lux publicly launched a new soap design.",
      "signoff": "Best regards",
      "html_body": "<p>Hi Priya,</p><img src=\\"{{asset_img_abc}}\\" alt=\\"x\\"><p>The new soap design stood out.</p>",
      "text_body": "Hi Priya"
    }
    """
    parsed = parse_personalization(
        raw,
        source_html='<img src="{{asset_img_abc}}" alt="x">',
        source_text="Hi",
        lead_fields={"first_name": "Priya", "company": "Lux"},
    )
    assert parsed["subject"] == "Priya, the new Lux soap design"
    assert "{{asset_img_abc}}" in parsed["html_body"]
    assert "soap" in parsed["company_note"]


def test_personalization_drops_rewrite_that_removes_images():
    raw = """
    {
      "subject": "Priya at Lux",
      "opener": "Hello Priya",
      "company_note": "",
      "signoff": "Best regards",
      "html_body": "<p>Hello Priya, no image here.</p>",
      "text_body": "Hello"
    }
    """
    parsed = parse_personalization(
        raw,
        source_html='<img src="{{asset_img_abc}}">',
        source_text="",
        lead_fields={"first_name": "Priya"},
    )
    assert "html_body" not in parsed
    assert parsed["subject"] == "Priya at Lux"


def test_open_redirect_protection():
    assert is_safe_url("https://example.com/path")
    assert not is_safe_url("javascript:alert(1)")
    assert not is_safe_url("/relative")


def test_detect_startup_url_uses_uvicorn_port():
    import sys

    from app.core.runtime import detect_startup_url

    old = sys.argv
    sys.argv = ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "9000"]
    try:
        assert detect_startup_url() == "http://127.0.0.1:9000"
    finally:
        sys.argv = old


def test_tracking_rewrites_links_and_adds_pixel():
    from types import SimpleNamespace
    from uuid import uuid4

    from app.services.tracking_service import inject_tracking

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


def test_untrusted_tracking_host_skips_pixel_and_rewritten_links():
    from types import SimpleNamespace
    from uuid import uuid4

    from app.core.runtime import untrusted_tracking_host
    from app.services.tracking_service import inject_tracking

    assert untrusted_tracking_host("https://example.trycloudflare.com")
    assert not untrusted_tracking_host("https://mail.example.com")
    email = SimpleNamespace(id=uuid4(), tracking_token="tok_abc")
    html, links = inject_tracking(
        '<html><body><p><a href="https://example.com/offer">Offer</a></p></body></html>',
        "https://example.trycloudflare.com",
        email,
        track_engagement=False,
    )
    assert "https://example.com/offer" in html
    assert "/t/o/" not in html
    assert links == []
