"""Render the DFE AWS deployment with the converted AWS pack and group styles.

Run: uv run --with playwright==1.64.1 python -I proof.py
Writes PNG + SVG for {raw, post} x {light, dark} under the Playwright root.
  raw  = what live Mermaid renders (docs site): AWS icons, AWS group colours/dashes.
  post = raw plus a post-render pass for pre-rendered SVG: group icon flush in the
         top-left corner and a left-aligned title, as AWS's deck draws groups.
"""

import json
import re
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

ST = Path("/projects/dfe-infra/.hyperi-ai/tmp/stencils")
OUT = Path("/projects/dfe-infra/.playwright-mcp/stencils")
MERMAID = "https://cdn.jsdelivr.net/npm/mermaid@12.2.0/dist/mermaid.esm.min.mjs"

AWS = json.loads((ST / "out/aws.json").read_text(encoding="utf-8"))["icons"]
GROUPS = {t: {g["name"] + ("|dash" if g["name"] == "Generic group" and g["dash"] != "solid" else ""): g
              for g in json.loads((ST / f"out/aws-groups-{t.title()}.json").read_text(encoding="utf-8"))}
          for t in ("light", "dark")}

# subgraph id -> (AWS group name on the deck's Groups slide, group icon key or None)
SUBGRAPHS = {
    "cloud": ("AWS Cloud", "group-aws-cloud-logo"),
    "region": ("Region", "group-region"),
    "vpc": ("Virtual private cloud (VPC)", "group-virtual-private-cloud-vpc"),
    "pub": ("Public subnet", "group-public-subnet"),
    "priv": ("Private subnet", "group-private-subnet"),
}
# AWS's "custom group for a service": the service's category colour plus its 32 icon (deck slide 26).
CUSTOM = {"eks": ("#ED7100", "amazon-elastic-kubernetes-service")}

DARK_SWAP = {"group-aws-cloud-logo": "group-aws-cloud-logo-dark"}


def icon(i, key, label, h=48):
    return f'  {i}@{{ icon: "aws:{key}", label: "{label}", pos: "b", h: {h} }}'


def house(i, name, sub):
    return f"  {i}(\"<b>{name}</b><br/><span style='font-size:12px;color:#475569'>{sub}</span>\")"


def src(theme):
    res = (lambda k: k + "-dark" if theme == "dark" and k + "-dark" in AWS else k)
    L = [
        "flowchart LR",
        icon("senders", res("res-users"), "Log and metric senders"),
        icon("ops", res("res-user"), "Operators"),
        'subgraph cloud["AWS Cloud"]',
        "  direction LR",
        icon("r53", "amazon-route-53", "Amazon Route 53<br/>public + private zones"),
        icon("trail", "aws-cloudtrail", "AWS CloudTrail"),
        ' subgraph region["Region"]',
        "  direction LR",
        '  subgraph vpc["VPC"]',
        "   direction LR",
        icon("igw", res("res-amazon-vpc-internet-gateway"), "Internet gateway"),
        '   subgraph pub["Public subnets x3"]',
        "    direction TB",
        icon("nlbr", res("res-elastic-load-balancing-network-load-balancer"), "Receiver NLB<br/>Elastic IPs"),
        icon("nlbg", res("res-elastic-load-balancing-network-load-balancer"), "Gateway NLB<br/>console, APIs"),
        icon("nat", res("res-amazon-vpc-nat-gateway"), "NAT gateway"),
        "   end",
        '   subgraph priv["Private subnets x3, one per AZ"]',
        "    direction LR",
        '    subgraph eks["Amazon EKS cluster, Graviton"]',
        "     direction LR",
        house("rcv", "dfe-receiver", "every protocol"),
        house("ldr", "dfe-loader", "schema-free insert"),
        house("ch", "ClickHouse", "hot tier on EBS"),
        house("ui", "DFE console", "search, hunts, admin"),
        icon("karp", res("res-amazon-ec2-instances"), "Nodes: system pool<br/>+ Karpenter"),
        "    end",
        icon("msk", "amazon-managed-streaming-for-apache-kafka", "Amazon MSK<br/>Express, one broker per AZ"),
        "   end",
        icon("s3ep", res("res-amazon-vpc-endpoints"), "S3 gateway<br/>endpoint"),
        "  end",
        icon("s3", "amazon-simple-storage-service", "Amazon S3<br/>ClickHouse object store, logs"),
        icon("kms", "aws-key-management-service", "AWS KMS<br/>customer-managed key"),
        icon("sm", "aws-secrets-manager", "AWS Secrets Manager"),
        icon("ecr", "amazon-elastic-container-registry", "Amazon ECR<br/>pull-through cache"),
        icon("sqs", "amazon-simple-queue-service", "Amazon SQS<br/>interruption queue"),
        icon("cw", "amazon-cloudwatch", "Amazon CloudWatch Logs"),
        " end",
        "end",
        "senders --> nlbr --> rcv",
        "ops --> nlbg --> ui",
        "rcv --> msk --> ldr --> ch --> ui",
        "ch --> s3ep --> s3",
        "eks -.-> sm",
        "eks -.-> ecr",
        "sqs -.-> karp",
        "trail --> s3",
        "trail --> cw",
        "eks -.-> r53",
        "priv -.-> nat --> igw",
        "classDef ingest fill:#FFFFFF,stroke:#0E8A7D,stroke-width:3px,color:#0F172A",
        "classDef load fill:#FFFFFF,stroke:#0072B2,stroke-width:3px,color:#0F172A",
        "classDef store fill:#FFFFFF,stroke:#00785A,stroke-width:3px,color:#0F172A",
        "classDef uicls fill:#FFFFFF,stroke:#D9480F,stroke-width:3px,color:#0F172A",
        "class rcv ingest",
        "class ldr load",
        "class ch store",
        "class ui uicls",
    ]
    dash = {"solid": "", "sysDash": ",stroke-dasharray:3 3", "dash": ",stroke-dasharray:8 6"}
    for sg, (gname, _) in SUBGRAPHS.items():
        g = GROUPS[theme][gname]
        L.append(f"style {sg} fill:none,stroke:{g['stroke']},stroke-width:1.5px,color:{g['label_colour']}{dash[g['dash']]}")
    for sg, (stroke, _) in CUSTOM.items():
        lab = GROUPS[theme]["AWS Cloud"]["label_colour"]
        L.append(f"style {sg} fill:none,stroke:{stroke},stroke-width:1.5px,color:{lab}")
    return "\n".join(L)


def used_icons(text):
    keys = set(re.findall(r'icon: "aws:([^"]+)"', text))
    keys |= {k for _, k in SUBGRAPHS.values() if k} | {DARK_SWAP.get(k, k) for _, k in SUBGRAPHS.values() if k}
    keys |= {k for _, k in CUSTOM.values()}
    return {k: AWS[k] for k in keys}


def page(theme, post):
    s = src(theme)
    bg = "#FFFFFF" if theme == "light" else "#232F3E"
    text_col = "#000000" if theme == "light" else "#FFFFFF"
    groups = {sg: (DARK_SWAP.get(k, k) if theme == "dark" else k) for sg, (_, k) in SUBGRAPHS.items()}
    groups.update({sg: k for sg, (_, k) in CUSTOM.items()})
    init = {
        "theme": "base", "look": "classic", "layout": "elk",
        "flowchart": {"curve": "linear", "nodeSpacing": 28, "rankSpacing": 44, "padding": 14, "htmlLabels": True},
        "themeVariables": {"fontFamily": "Inter", "fontSize": "14px", "lineColor": "#545B64" if theme == "light" else "#D5DBDB",
                           "primaryTextColor": text_col, "edgeLabelBackground": bg, "clusterBkg": "transparent"},
    }
    return f"""<!doctype html><html><head><meta charset="utf-8">
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap">
<style>body{{margin:0;padding:16px;background:{bg};font-family:Inter,system-ui,sans-serif}}
#wrap{{width:fit-content;padding:12px}} .label foreignObject div, .nodeLabel {{color:{text_col}}}</style></head><body>
<div id="wrap"></div><script type="text/plain" id="src">{s}</script>
<script type="module">
import mermaid from '{MERMAID}';
window.__errors=[];
try {{
mermaid.registerIconPacks([{{ name: 'aws', icons: {json.dumps({"prefix": "aws", "icons": used_icons(s)})} }}]);
await document.fonts.load('600 14px Inter'); await document.fonts.load('400 12px Inter'); await document.fonts.ready;
mermaid.initialize(Object.assign({{startOnLoad:false, fontFamily:'Inter', securityLevel:'loose'}}, {json.dumps(init)}));
const r = await mermaid.render('m1', document.getElementById('src').textContent);
const wrap = document.getElementById('wrap'); wrap.innerHTML = r.svg;
const sv = wrap.querySelector('svg'); const vb = sv.viewBox.baseVal; sv.style.maxWidth='none'; sv.setAttribute('width', vb.width); sv.setAttribute('height', vb.height);
if ({json.dumps(post)}) {{
  const pack = {json.dumps(used_icons(s))};
  const groups = {json.dumps(groups)};
  for (const c of sv.querySelectorAll('g.cluster')) {{
    const id = Object.keys(groups).find(k => c.id === k || c.id.endsWith('-' + k));
    if (!id) continue;
    const rect = c.querySelector('rect'); const x = +rect.getAttribute('x'), y = +rect.getAttribute('y');
    const ic = pack[groups[id]]; const S = 32;
    const g = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
    g.setAttribute('x', x); g.setAttribute('y', y); g.setAttribute('width', S); g.setAttribute('height', S);
    g.setAttribute('viewBox', `${{ic.left||0}} ${{ic.top||0}} ${{ic.width}} ${{ic.height}}`); g.innerHTML = ic.body;
    c.parentNode.insertBefore(g, c.nextSibling);  // outside g.cluster: Mermaid's `.cluster rect` CSS would repaint the icon
    const lab = c.querySelector('.cluster-label');
    if (lab) {{ const bb = lab.getBBox(); lab.setAttribute('transform', `translate(${{x + S + 8}}, ${{y + (S - bb.height) / 2}})`); }}
  }}
}}
}} catch(e) {{ window.__errors.push(String(e && e.stack || e)); }}
window.__done=true;
</script></body></html>"""


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    report = {}
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="chrome")
        try:
            ctx = browser.new_context(viewport={"width": 2200, "height": 1400}, device_scale_factor=1)
            for theme in ("light", "dark"):
                for post in (False, True):
                    name = f"dfe-aws-{'post' if post else 'raw'}-{theme}"
                    pg = ctx.new_page()
                    logs = []
                    pg.on("console", lambda m: logs.append(f"{m.type}: {m.text}"))
                    html = page(theme, post)
                    (OUT / f"{name}.html").write_text(html, encoding="utf-8", newline="\n")
                    pg.set_content(html)
                    pg.wait_for_function("window.__done===true", timeout=60000)
                    pg.wait_for_timeout(300)
                    errs = pg.evaluate("window.__errors")
                    if not errs:
                        pg.locator("#wrap").screenshot(path=str(OUT / f"{name}.png"))
                        (OUT / f"{name}.svg").write_text(pg.evaluate("document.querySelector('#wrap').innerHTML"), encoding="utf-8")
                    report[name] = {"errors": errs, "console": [l for l in logs if l.startswith(("error", "warn"))][:5]}
                    pg.close()
        finally:
            browser.close()
    print(json.dumps(report, indent=1))


if __name__ == "__main__":
    main()
