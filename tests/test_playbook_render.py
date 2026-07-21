from __future__ import annotations

from vamp.playbooks.render import render_markdown


def test_headings_and_paragraphs():
    html = render_markdown("# Title\n\nA paragraph here.\n")
    assert "<h1>Title</h1>" in html
    assert "<p>A paragraph here.</p>" in html


def test_unordered_and_ordered_lists():
    html = render_markdown("- one\n- two\n\n1. first\n2. second\n")
    assert "<ul>" in html and "<li>one</li>" in html
    assert "<ol>" in html and "<li>first</li>" in html


def test_inline_formatting():
    html = render_markdown("Some **bold** and *italic* and `code` here.")
    assert "<strong>bold</strong>" in html
    assert "<em>italic</em>" in html
    assert "<code>code</code>" in html


def test_safe_links_only():
    html = render_markdown("[OK](https://example.test/x) and [bad](javascript:alert(1))")
    assert '<a href="https://example.test/x"' in html
    # javascript: URLs are not matched by the link regex, so they stay inert text.
    assert "javascript:alert" not in html or '<a href="javascript' not in html


def test_html_is_escaped_no_injection():
    html = render_markdown("watch <script>alert('x')</script> me")
    assert "<script>" not in html
    assert "&lt;script&gt;" in html


def test_blockquote_and_hr():
    html = render_markdown("> a quote\n\n---\n")
    assert "<blockquote>a quote</blockquote>" in html
    assert "<hr>" in html
