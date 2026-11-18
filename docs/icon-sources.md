# Icon pack licence verdicts

Every source merrow knows, with its quoted terms, is in [source-register.md](source-register.md). This page is the verdict for the packs a profile draws with.

| Publisher | Package | Terms (quoted from the publisher) | Commit the converted pack to a repo? |
|---|---|---|---|
| AWS | Icon-package_07312026 + PPTX toolkit, release 24-2026.07.31 | Use them "to create architecture diagrams"; don't crop, flip, rotate or change shapes; predefined size and colour; no groups with non-approved icons; custom service groups allowed (deck slide 26). No redistribution grant; no CC BY-ND on AWS's page | No |
| Azure | V25 zip, Nov 2026 | Use in diagrams, training or docs; "copy, distribute, and display the icons only for the permitted use"; don't crop, rotate or distort. No Visio stencil | Unclear: legal call |
| Google Cloud | Core 19 + category 26 + legacy 216, PDF May 2026 | No terms on the page or in the zips. Iconify's `gcp` pack (v1.2.3, 214) is the deprecated legacy 2-tone set, labelled Apache-2.0 by Iconify only | No |
| Kubernetes | kubernetes/community `icons/` at 70a4bb2 | Apache-2.0 | Yes, with attribution |
| Microsoft 365 Visio | 2024 templates | Same Microsoft terms as Azure | Unclear: legal call |
| IBM Carbon | `@carbon/icons`, the 32 px set without `ibm-*` and `logo-*` | Apache-2.0 (LICENSE in the package) | Yes, with its LICENSE |
| HashiCorp | `@hashicorp/flight-icons`, the 24 px set | MPL-2.0 (LICENSE.md in the package). Product logos stay HashiCorp's trademarks | Yes, with its LICENSE |
| Tabler | `@tabler/icons`, the outline set without `brand-*` | MIT (LICENSE in the package) | Yes, with its LICENSE |
| Red Hat | red-hat-icons `src/standard` | "Red Hat icons are licensed under a Creative Commons Attribution 4.0 International license" and "If you redistribute these icons, Red Hat should be given attribution." | Yes, with attribution |
| Interop Tokyo ShowNet NOC | shownet-icons `svg` | "ShowNet Icons is licensed under a Creative Commons Attribution 4.0 International License." (LICENSE.txt) | Yes, with attribution |
| Apache Software Foundation | Project logos (Kafka, Flink, Iceberg, Spark), one PDF each | "our graphic logos are licensed to the public under the Apache License" (apache.org/foundation/marks). The names and logos stay ASF trademarks | Yes, with attribution |

A diagram rendered with publisher icons is the permitted use ("to create architecture diagrams"), so committing a rendered SVG diagram is fine. Redistributing the icon pack itself is what the terms don't grant.

## What merrow does about it

- Fetches AWS, Azure and GCP packs from the publisher at build time and caches them outside every repo.
- Ships one pack in merrow itself, `starter`: 34 Carbon icons with Carbon's LICENSE beside it.
- Paints a monochrome open set that sets no colour (Carbon, Red Hat) in the theme's icon colour, through the source's `fill`.
- Never recolours or resizes publisher icons. AWS ships separate artwork per size (viewBox 24/40/64/80), and the aws profile draws each icon at its own artwork size.
- Draws AWS groups only in AWS's styles, plus AWS's custom-group recipe for a service group.
- Draws the public subnet solid, as AWS's Groups slide does. AWS's Chef example dashes it.
- Google's current icon set is small, about 45 icons, with most products mapped to a category icon. Its 2-tone set is deprecated.
