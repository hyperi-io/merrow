# merrow

Diagram automation on Mermaid. merrow puts a house style in every diagram, renders it to SVG and lints it. Its converters turn the stencils and icon sets AWS, Azure, GCP, Kubernetes and others publish into Mermaid icon packs, so an AWS diagram comes out in the form AWS architects expect.

SVG is the master format. Headline diagrams are pre-rendered to committed SVG. Everything below that stays live Mermaid.

## Install

merrow is a CLI, installed with uv. It needs Python 3.14 and Node.js 22.13 or later on the PATH. Linux and macOS are supported, Windows is best effort.

```bash
uv tool install git+https://github.com/hyperi-io/merrow
merrow tools ensure    # installs the pinned mermaid-cli and its browser, once
```

## Use

```bash
merrow source list                      # the publisher sources and their pinned versions
merrow pack build aws-icons             # fetch the pinned download, build the icon pack
merrow diagram render arch.md --out svg # every mermaid fence, light and dark, icons registered
merrow config get                       # every setting, all layers merged
```

Each command prints JSON on stdout. Logs go to stderr.

## Two repos: the tool and your reference data

merrow is general purpose. Org and personal data lives in reference repos, loaded as layers:

1. merrow base (this repo)
2. an org reference repo
3. a personal reference repo

A later layer overrides an earlier one. Config lists the reference repos in layer order, under any name. Ours, for example, is `hyperi-merrow`: the standards we add on top of merrow's defaults. See [reference/](reference/).

## Nothing is hard-coded

Sources, icon naming rules, aliases, size limits, themes and pinned versions are config: `defaults.yaml`, `sources.yaml` and `sources.lock.yaml` in [src/merrow/](src/merrow/). A reference repo adds or overrides any of them. A new publisher in a known format is a config entry. A new release from one arrives as a PR the weekly Sources workflow opens.

## Icon packs are never committed

Icon packs are fetched from their publisher at build time and cached outside the repo. Most publishers allow diagrams drawn with their icons but grant no right to redistribute the icons. A rendered diagram is fine to commit. The pack is not. Terms per publisher: [docs/icon-sources.md](docs/icon-sources.md).

## Layout

| Path | What goes there |
|---|---|
| [src/merrow/](src/merrow/) | The CLI and its config: sources, converters, render, lint |
| [style/](style/) | The diagram standard and house style |
| [converters/prototypes/](converters/prototypes/) | The first working versions the converters came from |
| [reference/](reference/) | How a reference repo plugs in |
| [docs/](docs/) | Design notes and the icon licence verdicts |
| [tests/](tests/) | pytest, run with `hyperi-ci check` |

Why Merrow? Because Lee, SQUIRREL!
