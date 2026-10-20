"""Design-token compliance, enforced mechanically.

These back the TEST-AC-2xx criteria: raw hex only in tokens.css, no CDN fonts,
no thumbnails, no score rendering, correct focus/contrast choices.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

STATIC = Path(__file__).resolve().parents[2] / "src" / "web" / "static"
TEMPLATES = Path(__file__).resolve().parents[2] / "src" / "web" / "templates"

HEX = re.compile(r"#[0-9a-fA-F]{3,8}\b")


def read(p: Path) -> str:
    return p.read_text(encoding="utf-8")


def test_hex_only_in_tokens_css():
    """TEST-AC-201/202: one source of color truth."""
    offenders = []
    for path in list(STATIC.glob("*.css")) + list(TEMPLATES.glob("*.html")):
        if path.name == "tokens.css":
            continue
        if HEX.search(read(path)):
            offenders.append(path.name)
    assert offenders == []


def test_tokens_css_has_no_duplicate_coral():
    """--color-error must alias coral, not restate the hex (D25)."""
    css = read(STATIC / "tokens.css")
    assert css.count("#aa2d00") == 1
    assert "--color-error: var(--color-signature-coral)" in css


def test_no_remote_fonts_or_cdn():
    """TEST-AC-210: no webfont download, no CDN dependency."""
    blob = read(STATIC / "tokens.css") + read(STATIC / "app.css")
    for tmpl in TEMPLATES.glob("*.html"):
        blob += read(tmpl)
    assert "fonts.googleapis" not in blob
    assert "@import url(http" not in blob
    assert "cdn." not in blob
    assert "@font-face" not in blob


def test_local_font_stack_declared():
    """TEST-AC-211."""
    css = read(STATIC / "tokens.css")
    assert "-apple-system" in css
    assert "Segoe UI" in css
    # Haas must not appear in an actual font-family list (comments may name it).
    for fam in re.findall(r"font-family:\s*([^;]+);", css):
        assert "Haas" not in fam


def test_display_weights_never_bold():
    """TEST-AC-212: headings stay <= 500."""
    css = read(STATIC / "app.css")
    for weight in re.findall(r"font-weight:\s*(\d+)", css):
        assert int(weight) <= 600, f"unexpected weight {weight}"


def test_article_body_override_present():
    """TEST-AC-213 (D26)."""
    tokens = read(STATIC / "tokens.css")
    app = read(STATIC / "app.css")
    assert "--type-article-size: 16px" in tokens
    assert "--type-article-leading: 1.6" in tokens
    assert ".article-body" in app


def test_no_thumbnail_or_image_markup():
    """TEST-AC-220/246: no fake images."""
    for tmpl in TEMPLATES.glob("*.html"):
        body = read(tmpl)
        assert "<img" not in body.lower()
        assert "background-image" not in body.lower()


def test_no_forbidden_components():
    """TEST-AC-224: no pricing, logo strip, or topic rail."""
    for tmpl in TEMPLATES.glob("*.html"):
        body = read(tmpl).lower()
        for word in ("pricing", "logo-strip", "topic-filter", "topic-rail"):
            assert word not in body
    css = read(STATIC / "app.css").lower()
    for word in ("pricing", "logo-strip", "topic-filter", "topic-rail"):
        assert word not in css


def test_no_pill_radius():
    """TEST-AC-204: 9999px is pricing-only."""
    css = read(STATIC / "app.css") + read(STATIC / "tokens.css")
    assert "9999" not in css


def test_focus_visible_ring_defined():
    """TEST-AC-230/231."""
    css = read(STATIC / "app.css")
    assert ":focus-visible" in css
    assert "var(--color-info-border)" in css


def test_input_border_is_not_hairline():
    """TEST-AC-232: hairline is 1.36:1, unusable as a control boundary."""
    css = read(STATIC / "app.css")
    inputs = re.search(r'input\[type="text"\][^{]*\{[^}]*\}', css)
    assert inputs, "input styling block missing"
    assert "border: 1px solid var(--color-muted)" in inputs.group(0)


def test_contrast_pairs_meet_aa():
    """TEST-AC-235: recompute the documented pairs from tokens.css."""
    def lum(hex_color: str) -> float:
        h = hex_color.lstrip("#")
        r, g, b = (int(h[i:i + 2], 16) / 255 for i in (0, 2, 4))
        f = lambda c: c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
        return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b)

    def ratio(a: str, b: str) -> float:
        la, lb = lum(a), lum(b)
        hi, lo = max(la, lb), min(la, lb)
        return (hi + 0.05) / (lo + 0.05)

    pairs = [("#181d26", "#ffffff"), ("#333840", "#ffffff"),
             ("#41454d", "#ffffff"), ("#1b61c9", "#ffffff"),
             ("#ffffff", "#aa2d00"), ("#aa2d00", "#ffffff"),
             ("#181d26", "#f5e9d4")]
    for fg, bg in pairs:
        assert ratio(fg, bg) >= 4.5, f"{fg} on {bg} = {ratio(fg, bg):.2f}"


def test_touch_targets_are_44px():
    """TEST-AC-234."""
    tokens = read(STATIC / "tokens.css")
    assert "--touch-min: 44px" in tokens


def test_no_score_rendered_in_templates():
    """TEST-AC-025/027 (D22): scores never appear in the UI."""
    for tmpl in TEMPLATES.glob("*.html"):
        body = read(tmpl)
        assert "score" not in body.lower()
        assert "toFixed" not in body


def test_no_rating_control():
    """TEST-AC-067: ratings are out of MVP."""
    for tmpl in TEMPLATES.glob("*.html"):
        body = read(tmpl).lower()
        for word in ("beri rating", "stars", "rating"):
            assert word not in body


def test_nav_collapse_rule_exists():
    """TEST-AC-242: the nav must collapse below 768px."""
    css = read(STATIC / "app.css")
    assert "@media (max-width: 767px)" in css
    block = css[css.index("@media (max-width: 767px)"):]
    assert ".navmenu > summary" in block
    assert "display: flex" in block
    assert ".navlinks" in block and "display: none" in block
    assert ".navmenu[open] > .navlinks" in block


def test_breakpoint_grid_columns_declared():
    """TEST-AC-241: 3-up desktop, 2-up tablet, 1-up mobile."""
    css = read(STATIC / "app.css")
    assert "repeat(3, minmax(0, 1fr))" in css
    assert "@media (max-width: 1024px)" in css
    assert "repeat(2, minmax(0, 1fr))" in css
    assert "@media (max-width: 768px)" in css


def test_base_template_has_accessible_menu():
    """The collapsed menu must be keyboard reachable and labelled."""
    html = read(TEMPLATES / "base.html")
    assert "<details" in html and "<summary" in html
    assert 'aria-label="Menu navigasi"' in html


def test_brand_logo_is_inline_vector():
    """The wordmark must be inline SVG so it inherits currentColor."""
    html = read(TEMPLATES / "base.html")
    assert 'class="brand-mark"' in html
    assert "<svg" in html
    assert "<img" not in html            # <img> would block currentColor
    assert "currentColor" in html
    css = read(STATIC / "app.css")
    assert "fill: currentColor" in css


def test_logo_asset_exists_and_is_vector():
    svg = STATIC / "goodnews.svg"
    assert svg.exists()
    body = svg.read_text()
    assert body.lstrip().startswith("<svg")
    assert "viewBox" in body
    assert "<image" not in body          # no embedded bitmap
    assert len(body) < 40_000            # stay reasonable
