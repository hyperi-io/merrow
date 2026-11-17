# merrow

Diagram automation on Mermaid. merrow puts a house style in every diagram, renders it to SVG and lints it. Its converters turn the stencils and icon sets AWS, Azure, GCP, Kubernetes and others publish into Mermaid icon packs, so an AWS diagram comes out in the form AWS architects expect.

SVG is the master format. Headline diagrams are pre-rendered to committed SVG. Everything below that stays live Mermaid.

## Two repos: the tool and your reference data

merrow is general purpose. Org and personal data lives in reference repos, loaded as layers:

1. merrow base (this repo)
2. an org reference repo
3. a personal reference repo

A later layer overrides an earlier one. Config lists the reference repos in layer order, under any name. Ours, for example, is `hyperi-merrow`: the standards we add on top of merrow's defaults. See [reference/](reference/).

## Icon packs are never committed

Icon packs are fetched from their publisher at build time and cached outside the repo. Most publishers allow diagrams drawn with their icons but grant no right to redistribute the icons. A rendered diagram is fine to commit. The pack is not. Terms per publisher: [docs/icon-sources.md](docs/icon-sources.md).

## Layout

| Directory | What goes there |
|---|---|
| [style/](style/) | The house style: frontmatter, classDefs, label forms |
| [render/](render/) | Mermaid to SVG, light and dark |
| [lint/](lint/) | Checks a diagram carries the house style byte for byte |
| [converters/](converters/) | Published stencils, icon sets and decks to Mermaid packs |
| packs/ | Generated packs. Ignored by git |
| [reference/](reference/) | How a reference repo plugs in |
| [docs/](docs/) | Design notes and the icon licence verdicts |
