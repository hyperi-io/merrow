---
name: merrow-diagrams
description: Draw, render and lint a diagram with merrow, from a diagram file or hand-written Mermaid. Use when a page needs a new or changed Mermaid diagram, or a diagram fails merrow lint.
---

# Drawing a diagram with merrow

An agent writes a diagram file, never Mermaid styling. merrow turns the file into Mermaid in the profile's look, renders it and lints it. The rules are style/diagrams.md in the merrow repo (https://github.com/hyperi-io/merrow/blob/main/style/diagrams.md), and lint holds a diagram to them. This page is the loop.

1. Pick the level (L0 to L4) and a pattern. `merrow config get | jq '.patterns | keys'` lists them. A path through several components is `data-path`, and config flowing to a runtime is `gitops-control`. Nothing fits: write the graph yourself.
2. Pick the objects. `merrow config get | jq '.objects | keys'` lists them, such as `dfe.loader`. An object brings its label, subtitle, class and shape.
3. Write the file. `merrow graph schema` prints its JSON Schema.

   ```yaml
   title: L2 Services -- DFE data path
   description: Senders reach dfe-receiver, which produces to Kafka. dfe-loader writes ClickHouse.
   pattern: data-path
   fills:
     senders: [{label: Push clients, object: dfe.proxy}]
     intake: [dfe.receiver]
     bus: [dfe.kafka]
     loader: [dfe.loader]
     store: [dfe.clickhouse]
   ```

4. `merrow graph validate file.yaml`. Fix every line it prints and run it again.
5. `merrow graph render file.yaml --out out/` writes `out/file.mmd` and a light and a dark SVG.
6. `merrow diagram lint out/file.mmd` renders it and measures it against the profile's column, height, node and arrow limits. Fix a layout finding in the file: split the diagram, move detail down a level, or mark a path optional. Never fix it with styling.
7. Open both SVGs. Lint can't see contrast, lines drawn on top of each other, or a box that isn't in the code.
8. Put the Mermaid from `out/file.mmd` in a `mermaid` fence, with a caption under it: `*Figure N. <title>.* Up: <parent>.`

No Chrome on the host: `merrow diagram lint --no-render` runs the source pass alone. Say "not rendered" when you report it.

Hand-written Mermaid works too. Write the body only and name each object as `loader:::dfe-loader`, the object id with dots as hyphens. `merrow diagram apply page.md` adds the frontmatter and the class block, and fills in each bare object's label. Never type frontmatter, `classDef` or `style` lines.

## What goes wrong

- A home-made renderer or apply script. merrow's commands are the tooling.
- A long chain in one row. The writer stacks a chain past four ranks in stages, so let it.
- A dropped optional path. Mark the edge `optional: true` and it draws dotted, with its label.
- A node or arrow that isn't in the code. Diagrams come from reading the code, never from imagination.
- An intro or caption that restates the picture, or names a colour or a dash. Words beside a diagram carry only what the picture can't show: why, the limits, what is optional.
- Hexagons, `graph TD` and `style` lines. Lint fails them.
