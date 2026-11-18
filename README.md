# merrow

Mermaid diagram automation for people, now updated for AI too.

You describe a diagram as a small YAML file, or write the Mermaid yourself. merrow writes it as Mermaid in a house style, ready to drop into Markdown, renders that Mermaid to light and dark SVG for places that don't run Mermaid, and checks it against a diagram standard. Agents get the same loop people do: write, render, lint, fix.

## What it does

- Draws a graph of nodes, groups and arrows as Mermaid, in a profile's look. No hand-typed colours or `style` lines.
- Keeps a library of objects (`aws.s3`, or your `shop.orders`) so a thing looks the same in every diagram that uses it.
- Builds icon packs from what AWS, Kubernetes, GCP and others publish, and draws AWS diagrams with AWS's icons and group styles.
- Renders light and dark SVGs, and lints each diagram for size, crossed lines, skip arrows, labels and captions.
- Reads draw.io, PPTX, Visio, Excalidraw, Graphviz and Structurizr files into the same graph.

## Quick start

It's a CLI, installed with uv. It runs on Linux, macOS and Windows, on the Python version `pyproject.toml` asks for.

```bash
uv tool install git+https://github.com/hyperi-io/merrow
merrow tools ensure          # the pinned Mermaid bundle and a headless browser
merrow graph render demo.yaml --out out
```

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

`merrow diagram lint out/demo.mmd` then measures it. `merrow --help` lists the rest.

## Configuration

Settings come in layers: merrow's defaults, then the reference repos you list, then `settings.yaml` in the working directory, then `MERROW_*` environment variables. A reference repo is where your company's objects, profiles and brand live, so merrow itself stays neutral. Ours is `hyperi-merrow`.

| Setting | What it does |
|---|---|
| `references` | Your reference repo directories, org first, then personal |
| `profile` | The look to draw in: `house`, `aws`, or one a reference repo adds |
| `font` | One font stack for every profile, such as `[Arial, Helvetica, sans-serif]` for PowerPoint and Visio |
| `packs_dir`, `cache_dir` | Where built icon packs and downloads go. Neither is ever in a repo |

`merrow config get` prints every setting with all the layers merged.

## Documentation

- [docs/architecture.md](docs/architecture.md) -- how the pieces fit, with diagrams.
- [style/diagrams.md](style/diagrams.md) -- the diagram standard lint holds you to, and [style/diagram-templates.md](style/diagram-templates.md) to start from.
- [src/merrow/skill/SKILL.md](src/merrow/skill/SKILL.md) -- the agent loop. `merrow skill install` puts it where Claude Code loads skills.
- [docs/icon-sources.md](docs/icon-sources.md) and [docs/source-register.md](docs/source-register.md) -- icon publishers and their terms. Publisher packs never go in a repo.

## Getting help

Open an issue: https://github.com/hyperi-io/merrow/issues

## Contributing

Read [CONTRIBUTING.md](CONTRIBUTING.md) first. Start with its Context section.

## Licence

Apache-2.0. See [LICENSE](LICENSE).

Why Merrow? Because Lee, SQUIRREL!
