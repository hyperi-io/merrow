# merrow

Mermaid diagram automation for people, now updated for AI too.

You describe a diagram as a small YAML file, or write the Mermaid yourself. merrow writes it as Mermaid in a house style, ready to drop into Markdown. It renders that Mermaid to light and dark SVG for places that don't run Mermaid, and checks it against a diagram standard. Agents get the same loop people do: write, render, lint, fix.

The point is one look from many sources. Your diagrams arrive as Visio pages, PowerPoint slides, draw.io files, Structurizr models and publisher icon sets, each styled differently. merrow reads them into one graph and draws them all the same way. Where a source has style rules worth keeping, merrow keeps them: AWS diagrams keep AWS's group styles and icon sizes. [tests/test_one_look.py](tests/test_one_look.py) and [tests/test_aws_profile.py](tests/test_aws_profile.py) check both.

## What it does

- Draws a graph of nodes, groups and arrows as Mermaid, in a profile's look. No hand-typed colours or `style` lines.
- Keeps a library of objects (`aws.s3`, or your `shop.orders`) so a thing looks the same in every diagram that uses it.
- Builds icon packs from the SVG, Visio, PowerPoint or PDF files AWS, Kubernetes, GCP, IBM Carbon, Tabler, the ASF and others publish, and draws AWS diagrams with AWS's icons and group styles.
- Ships 34 generic icons from IBM Carbon (Apache-2.0), so `icon.server`, `icon.database` and the like draw before any pack is built.
- Renders light and dark SVGs, and lints each diagram for size, crossed lines, skip arrows, labels and captions.
- Reads draw.io, PPTX, Visio, Excalidraw, Graphviz, Structurizr and PDF files into the same graph. A PDF keeps only ink, so its boxes, labels and arrows are rebuilt from where they are drawn.

## Quick start

It's a CLI for Linux and macOS. The installer uses your uv, or fetches a pinned uv release and checks its SHA256 when you have none. Then it installs merrow, the pinned Mermaid bundle and a headless browser. On Debian and Ubuntu it also asks sudo for the browser's system libraries.

```bash
git clone https://github.com/hyperi-io/merrow
./merrow/install.sh
merrow graph render demo.yaml --out out
```

Already have uv? `uv tool install --python 3.14 'merrow[all]'` takes the release from PyPI, then run `merrow tools ensure`. Plain `merrow` is the core for a CI job or a generator: it writes, applies and source-lints diagrams (`diagram lint --no-render`), with no browser and no pack builds. `merrow[render]` adds rendering and `merrow[packs]` the icon pack builds. uv caches PyPI's index, so for a version out in the last few minutes add `--refresh`.

Windows is best effort, and we guarantee nothing there because we don't run it. Install [uv](https://docs.astral.sh/uv/) yourself, then run the same two commands.

With a `demo.yaml` like this one:

```yaml
title: L2 Services -- Log pipeline
description: Shippers send logs to a collector, which writes them to a store.
nodes:
  - {id: shippers, label: Log shippers}
  - {id: collector, label: Collector}
  - {id: store, label: Log store}
edges:
  - {source: shippers, target: collector, label: logs}
  - {source: collector, target: store}
```

you get the Mermaid and a light and a dark SVG:

```text
{"diagram": "demo", "theme": "light", "svg": "out/demo-light.svg"}
{"diagram": "demo", "theme": "dark", "svg": "out/demo-dark.svg"}
```

`merrow diagram lint out/demo.mmd` then measures it. `merrow graph write` writes the Mermaid alone, with no browser. `merrow --help` lists the rest.

## Configuration

Settings come in layers: merrow's defaults, then the reference repos you list, then `settings.yaml` in the working directory, then `MERROW_*` environment variables. A reference repo is where your company's objects, profiles and brand live, so merrow itself stays neutral. Ours is `hyperi-merrow`.

| Setting | What it does |
|---|---|
| `references` | Your reference repo directories, org first, then personal |
| `profile` | The look to draw in: `house`, `aws`, or one a reference repo adds |
| `destination` | Where it is published: `page`, `slide`, or one a reference repo adds. It sets the width and height limits and the themes rendered |
| `font` | One font stack for every profile, such as `[Arial, Helvetica, sans-serif]` for PowerPoint and Visio |
| `packs_dir`, `cache_dir` | Where built icon packs and downloads go. Neither is ever in a repo |

`merrow config get` prints every setting with all the layers merged.

## Documentation

- [docs/examples/](docs/examples/) -- worked examples: the diagram file, its Mermaid and its SVGs.
- [docs/architecture.md](docs/architecture.md) -- how the pieces fit, with diagrams.
- [style/diagrams.md](style/diagrams.md) -- the diagram standard lint holds you to, and [style/diagram-templates.md](style/diagram-templates.md) to start from.
- [src/merrow/skill/SKILL.md](src/merrow/skill/SKILL.md) -- the agent loop. `merrow skill install` puts it where Claude Code loads skills.
- [docs/icon-sources.md](docs/icon-sources.md) and [docs/source-register.md](docs/source-register.md) -- icon publishers and their terms. Publisher packs never go in a repo, apart from the Apache-2.0 starter pack merrow ships.

## Getting help

Open an issue: https://github.com/hyperi-io/merrow/issues

## Contributing

Read [CONTRIBUTING.md](CONTRIBUTING.md) first. Start with its Context section.

## Licence

Apache-2.0. See [LICENSE](LICENSE).

Why Merrow? Because Lee, SQUIRREL!
