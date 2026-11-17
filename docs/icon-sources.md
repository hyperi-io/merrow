# Vendor stencil and icon packs: feasibility and licence verdicts

Read 2026-11-17. Downloads under this directory, converters under `tools/`, renders under `/projects/dfe-infra/.playwright-mcp/stencils/`.

## Feasibility

| Part | Verdict | Evidence |
|---|---|---|
| Vendor SVG icons to a Mermaid icon pack | Works | `tools/svg2iconify.py`: AWS 857, Azure 644, GCP 261, Kubernetes 72 icons, 0 failures, all render in Mermaid 12.2.0 |
| AWS group styles (Cloud, Region, AZ, VPC, subnets, security group, ASG ...) | Works | `tools/ooxml_groups.py` read all 19 from the PPTX toolkit deck (slide 25 light, 23 dark): colour, dash, weight, label colour, corner icon. Out: `out/aws-groups-{Light,Dark}.json`. AWS publishes no Visio stencil, only the icon zip and the PPTX toolkit |
| Visio stencil masters to icons | Works | `tools/vsx2mermaid.py masters`: M365 concepts 206/206, M365 clouds 32/32, Kubernetes 40/40. 5 M365 palette masters render blank. The Kubernetes .vssx is PNG-based: use its SVGs |
| Visio template pages to Mermaid flowcharts | Topology only | M365 pages have no glued connectors, so edges are matched by endpoint position: 10 of 11 right on the flowchart page. Mermaid re-lays the page, so Visio positions are lost |
| DFE AWS deployment drawn from the library | Works, about 80% of a hand-built AWS diagram | `dfe-aws-post-{light,dark}.png`, `compare-{light,dark}.png`. Raw live Mermaid gives AWS colours and dashes with centred titles; a post-render step (for pre-rendered SVG) puts the group icon flush top-left and left-aligns the title. Limits: no group crossing another group (an AZ across a VPC), narrow label wrap, long edges messy |

## Licence verdicts

| Vendor | Package | Terms (quoted from the vendor) | Commit the converted pack to a repo? |
|---|---|---|---|
| AWS | Icon-package_07312026 + PPTX toolkit, release 24-2026.07.31 | Use them "to create architecture diagrams"; don't crop, flip, rotate or change shapes; predefined size and colour; no groups with non-approved icons; custom service groups allowed (deck slide 26). No redistribution grant; no CC BY-ND on AWS's page | No |
| Azure | V25 zip, Nov 2026 | Use in diagrams, training or docs; "copy, distribute, and display the icons only for the permitted use"; don't crop, rotate or distort. No Visio stencil | Unclear: legal call |
| Google Cloud | Core 19 + category 26 + legacy 216, PDF May 2026 | No terms on the page or in the zips. Iconify's `gcp` pack (v1.2.3, 214) is the deprecated legacy 2-tone set, labelled Apache-2.0 by Iconify only | No |
| Kubernetes | kubernetes/community `icons/` at 70a4bb2 | Apache-2.0 | Yes, with attribution |
| Microsoft 365 Visio | 2024 templates | Same Microsoft terms as Azure | Unclear: legal call |

A diagram rendered with vendor icons is the permitted use ("to create architecture diagrams"), so committing a rendered SVG diagram is fine. Redistributing the icon pack itself is what the terms don't grant.

## Consequences for the build

- Don't commit AWS, Azure or GCP icon packs to any repo. The converter downloads from the vendor at build or render time and caches outside the repo.
- Don't recolour or resize vendor icons. AWS ships separate artwork per size (viewBox 24/40/64/80): the pack carries the size it renders at, never a scaled one (the proof scaled 64 to 48, which the deck forbids: fix in the real build).
- Don't invent AWS group styles beyond AWS's custom-group recipe.
- AWS contradicts itself on the public subnet (solid on the Groups slide, dashed in its Chef example): follow the Groups slide.
- Google's current icon set is small (about 45, most products mapped to a category icon) and its 2-tone set is deprecated.

## What hyperi-ai builds (estimates, not measured)

| Piece | Size |
|---|---|
| Vendor downloader + SVG-to-Iconify converter | about 300 lines |
| PPTX/OOXML group-style extractor | about 150 lines |
| Visio stencil + page converter | about 500 lines |
| Post-render step for group icons and titles (pre-rendered SVG only) | about 80 lines of JS |
| Short-name alias table (`aws:amazon-eks` for `amazon-elastic-kubernetes-service`) | hand-written |

Prototypes: `tools/svg2iconify.py`, `tools/ooxml_groups.py`, `tools/vsx2mermaid.py`, `tools/proof.py`, `tools/compare.py`, `tools/visio_check.py`. GitHub's renderer was not tested.
