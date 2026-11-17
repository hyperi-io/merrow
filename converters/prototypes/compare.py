"""Side-by-side: AWS's own example slide vs the converted-pack Mermaid render."""
from pathlib import Path
from playwright.sync_api import sync_playwright

OUT = Path("/projects/dfe-infra/.playwright-mcp/stencils")
for theme, ref, bg, fg in (("light", "ref/aws-ref-slide-021.png", "#FFFFFF", "#000"), ("dark", "ref/aws-ref-dark-019.png", "#232F3E", "#FFF")):
    html = f"""<!doctype html><html><body style="margin:0;padding:16px;background:{bg};color:{fg};font:14px Inter,Arial,sans-serif">
<div style="display:grid;grid-template-columns:900px 1500px;gap:24px;align-items:start">
<div><div style="margin-bottom:6px">Reference: AWS Architecture Icons deck, release 24-2026.07.31</div><img src="{ref}" style="width:900px"></div>
<div><div style="margin-bottom:6px">Mermaid 12.2.0 + converted AWS pack + extracted group styles (post-processed)</div><img src="dfe-aws-post-{theme}.png" style="width:1500px"></div>
</div></body></html>"""
    (OUT / f"compare-{theme}.html").write_text(html, encoding="utf-8", newline="\n")
with sync_playwright() as p:
    b = p.chromium.launch(channel="chrome")
    try:
        pg = b.new_page(viewport={"width": 2470, "height": 900})
        for theme in ("light", "dark"):
            pg.goto(f"file://{OUT}/compare-{theme}.html")
            pg.wait_for_load_state("load")
            pg.screenshot(path=str(OUT / f"compare-{theme}.png"), full_page=True)
    finally:
        b.close()
print("ok")
