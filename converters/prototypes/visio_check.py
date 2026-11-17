"""Render converted Visio output: template pages as Mermaid, masters as a Mermaid icon grid."""
import json
from pathlib import Path
from playwright.sync_api import sync_playwright

ST = Path("/projects/dfe-infra/.hyperi-ai/tmp/stencils")
OUT = Path("/projects/dfe-infra/.playwright-mcp/stencils/visio")
MERMAID = "https://cdn.jsdelivr.net/npm/mermaid@12.2.0/dist/mermaid.esm.min.mjs"


def grid(prefix, keys):
    rows = ["flowchart LR"]
    for i, k in enumerate(keys):
        rows.append(f'  i{i}@{{ icon: "{prefix}:{k}", label: "{k[:22]}", pos: "b", h: 48 }}')
    return "\n".join(rows)


def html(src, packs):
    reg = ",".join(f"{{name:'{n}',icons:{json.dumps(p)}}}" for n, p in packs.items())
    return f"""<!doctype html><html><body style="margin:0;padding:16px;background:#fff;font-family:Arial">
<div id="wrap" style="width:fit-content"></div><script type="text/plain" id="src">{src}</script>
<script type="module">
import mermaid from '{MERMAID}'; window.__errors=[];
try {{ mermaid.registerIconPacks([{reg}]);
mermaid.initialize({{startOnLoad:false, theme:'base', layout:'elk', flowchart:{{curve:'linear', htmlLabels:true}}}});
const r = await mermaid.render('m1', document.getElementById('src').textContent);
document.getElementById('wrap').innerHTML = r.svg;
const sv=document.querySelector('#wrap svg'); const vb=sv.viewBox.baseVal; sv.style.maxWidth='none'; sv.setAttribute('width', vb.width); sv.setAttribute('height', vb.height);
}} catch(e) {{ window.__errors.push(String(e)); }} window.__done=true;
</script></body></html>"""


jobs = {}
for p in (3, 5, 9):
    src = "\n".join(l for l in (ST / f"out/m365-page{p}.mmd").read_text(encoding="utf-8").splitlines() if not l.startswith("%%"))
    jobs[f"page{p}-mermaid"] = html(src, {})
for name, d, pref, n in (("m365-clouds", "out/m365-clouds", "m365clouds", 32), ("m365-concepts", "out/m365-concepts", "m365concepts", 40),
                         ("m365-basic", "out/m365-basic", "m365basic", 28), ("k8s-vssx", "out/k8s-vssx", "k8svssx", 40)):
    pack = json.loads((ST / d / f"{pref}.json").read_text(encoding="utf-8"))
    keys = sorted(pack["icons"])[:n]
    # a grid: chunk into rows of 10 with invisible links so ELK lays them out
    lines = ["flowchart TB"]
    for r in range(0, len(keys), 10):
        lines.append(f"  subgraph r{r}[\" \"]\n  direction LR")
        for i, k in enumerate(keys[r:r + 10], start=r):
            lines.append(f'  i{i}@{{ icon: "{pref}:{k}", label: "{k[:20]}", pos: "b", h: 48 }}')
        lines.append("  end")
    jobs[name] = html("\n".join(lines), {pref: pack})
    # k8s/vendor svg packs too
for vendor in ("azure", "gcp", "k8s"):
    pack = json.loads((ST / f"out/{vendor}.json").read_text(encoding="utf-8"))
    pick = {"azure": ["kubernetes-services", "event-hubs", "storage-accounts", "key-vaults", "virtual-networks", "load-balancers", "dns-zones", "monitor", "azure-data-explorer-clusters", "managed-identities"],
            "gcp": ["gke", "cloud-storage", "bigquery", "compute-engine", "category-networking", "category-security-identity", "legacy-google-kubernetes-engine", "legacy-cloud-storage", "legacy-pubsub", "legacy-key-management-service"],
            "k8s": ["pod", "deploy", "sts", "svc", "ing", "pvc", "node", "control-plane", "ns", "secret"]}[vendor]
    have = [k for k in pick if k in pack["icons"]]
    lines = ["flowchart LR"] + [f'  i{i}@{{ icon: "{vendor}:{k}", label: "{k[:24]}", pos: "b", h: 48 }}' for i, k in enumerate(have)]
    jobs[f"{vendor}-sample"] = html("\n".join(lines), {vendor: {"prefix": vendor, "icons": {k: pack["icons"][k] for k in have}}})
    print(vendor, "missing from pick:", [k for k in pick if k not in pack["icons"]])

report = {}
with sync_playwright() as p:
    b = p.chromium.launch(channel="chrome")
    try:
        ctx = b.new_context(viewport={"width": 1800, "height": 1000})
        for name, h in jobs.items():
            pg = ctx.new_page()
            pg.set_content(h)
            pg.wait_for_function("window.__done===true", timeout=60000)
            errs = pg.evaluate("window.__errors")
            if not errs:
                pg.locator("#wrap").screenshot(path=str(OUT / f"{name}.png"))
            report[name] = errs
            pg.close()
    finally:
        b.close()
print(json.dumps(report))
