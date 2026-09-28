import pytest

from app.core.exceptions import AppError
from app.services.template_service import (
    extract_variables,
    html_to_text,
    render_template,
    sanitize_html,
)


def test_extract_and_render_variables():
    source = "Hello {{ first_name }} at {{company}}"
    assert extract_variables(source) == ["company", "first_name"]
    assert render_template(source, {"first_name": "Ada", "company": "Acme"}) == "Hello Ada at Acme"


def test_render_keeps_asset_placeholders():
    html = '<p>Hi {{first_name}}</p><img src="{{asset_img_abc123}}" alt="photo.jpg">'
    rendered = render_template(html, {"first_name": "Ada"})
    assert "Hi Ada" in rendered
    assert 'src="{{asset_img_abc123}}"' in rendered


def test_html_render_escapes():
    html = "<p>Hi {{first_name}}</p>"
    rendered = render_template(html, {"first_name": "<script>x</script>"})
    assert "<script>" not in rendered
    assert "&lt;script&gt;" in rendered


def test_sanitize_rejects_javascript():
    with pytest.raises(AppError):
        sanitize_html('<a href="javascript:alert(1)">x</a>')


def test_html_to_text():
    text = html_to_text("<p>Hello</p><p>World</p>")
    assert "Hello" in text
    assert "World" in text


def test_pdf_is_attached_as_a_file_and_removed_from_the_body():
    from types import SimpleNamespace

    from app.services.asset_service import strip_pdf_placeholders
    from app.services.smtp_service import build_message

    html = strip_pdf_placeholders(
        '<p>Hi Jordan,</p><p><a href="{{asset_link_abc}}">{{asset_link_abc}}</a></p>',
        ["asset_link_abc"],
    )
    assert "asset_link_abc" not in html
    account = SimpleNamespace(from_name="Tushar", from_email="tushar@example.com")
    message = build_message(
        account,
        "jordan@example.com",
        "Before the next launch",
        html,
        "Hi Jordan",
        attachments=[("one-pager.pdf", "application/pdf", b"%PDF-1.4 sample")],
    )
    assert message.get_content_type() == "multipart/mixed"
    files = list(message.iter_attachments())
    assert len(files) == 1
    assert files[0].get_filename() == "one-pager.pdf"
    assert files[0].get_content_disposition() == "attachment"


def test_wrap_plaintext_adds_paragraphs_and_signoff():
    from app.services.template_service import wrap_outbound_email

    html, text = wrap_outbound_email(
        "Hi Ada,\n\nThis is a test note.\n\n- Point one\n- Point two",
        "",
        from_name="Tushar Pareenja",
        company="Mindsurve",
        physical_address="Harbor Street",
    )
    assert "<p" in html
    assert "Best regards" in html
    assert "Tushar Pareenja" in html
    assert "Mindsurve" in html
    assert "{{unsubscribe_url}}" in html
    assert "Best regards," in text
    assert "unsubscribe" in text.lower()


def test_preview_fills_signoff_and_opener():
    from app.services.template_service import apply_sender_context, render_template

    context = apply_sender_context(
        {"first_name": "Ada", "company": "Northwind", "industry": "Software"},
        from_name="Tushar Pareenja",
        company="Mindsurve",
    )
    html = render_template("<p>Hi {{first_name}},</p><p>{{opener}}</p><p>{{signoff}}</p>", context)
    assert "Ada" in html
    assert "Northwind" in html
    assert "Best regards," in html
    assert "Tushar Pareenja" in html
    assert "<br>" in html


def test_wrap_skips_duplicate_signoff():
    from app.services.template_service import wrap_outbound_email

    html, _text = wrap_outbound_email(
        "<p>Hi Ada,</p><p>Best regards,<br>Ada</p>",
        "",
        from_name="Other Person",
    )
    assert html.count("Best regards") == 1
