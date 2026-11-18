---
name: merrow-diagrams
description: Draw, render and lint a diagram with merrow, from a diagram file or hand-written Mermaid. Use when a page needs a new or changed Mermaid diagram, or a diagram fails merrow lint.
---

# Drawing a diagram with merrow

An agent writes a diagram file, never Mermaid styling. merrow turns the file into Mermaid in the profile's look, renders it and lints it. The rules are style/diagrams.md in the merrow repo (https://github.com/hyperi-io/merrow/blob/main/style/diagrams.md), and lint holds a diagram to them. This page is the loop.

1. Pick the level (L0 to L4) and a pattern. `merrow config get | jq '.patterns | keys'` lists them. A path through several components is `data-path`, and config flowing to a runtime is `gitops-control`. Nothing fits: write the graph yourself.
2. Pick the objects. `merrow config get | jq '.objects | keys'` lists them, such as `aws.msk`, and a reference repo adds its own. `icon.server`, `icon.database`, `icon.queue` and 31 more always draw, from the icon pack merrow ships. An object brings its `label`, `subtitle`, `class` and `shape`. A thing with no object is a fill or node with a `label` alone, drawn in the profile's plain `part` class.
3. Write the file. `merrow graph schema` prints its JSON Schema. A file takes a pattern, its own `nodes`, `edges` and `groups`, or both: add nodes and edges beside a pattern when it lacks a box you need.

   ```yaml
   title: L2 Services -- Log pipeline
   description: Log shippers reach the collector through a Network Load Balancer. The collector produces to Amazon MSK, and the archiver writes Amazon S3.
   pattern: data-path
   fills:
     senders: [{label: Log shippers}]
     intake: [aws.nlb, {label: Collector}]
     bus: [aws.msk]
     loader: [{label: Archiver}]
     store: [aws.s3]
   ```

4. `merrow graph validate file.yaml`. Fix every line it prints and run it again.
5. `merrow graph render file.yaml --out out/` writes `out/file.mmd` and a light and a dark SVG.
6. `merrow diagram lint out/file.mmd` renders it and measures it against the profile's column, height, node and arrow limits. Fix a layout finding in the file: split the diagram, move detail down a level, or mark a path optional. Never fix it with styling.
7. Open both SVGs. Lint can't see contrast, lines drawn on top of each other, or a box that isn't in the code.
8. Put the Mermaid from `out/file.mmd` in a `mermaid` fence, with a caption under it: `*Figure N. <title>.* Up: <parent>.`

No Chrome on the host: `merrow diagram lint --no-render` runs the source pass alone. Say "not rendered" when you report it.

Hand-written Mermaid works too. Write the body with its `accTitle` and `accDescr` lines, and name each object as `bus:::aws-msk`, the object id with dots as hyphens, after a shape if you want your own label (`topics[("Raw topics")]:::aws-msk`). `merrow diagram apply page.md` adds the frontmatter and the class block, and fills in a bare object's label. A label you wrote stays. A sequence, ER or class diagram names no object, so apply gives it the frontmatter alone. Never type frontmatter, `classDef` or `style` lines.

## What goes wrong

- A home-made renderer or apply script. merrow's commands are the tooling.
- A long chain in one row. The writer stacks a chain past four ranks in stages, so let it. Edges between stages join stage to stage, so the picture no longer says which box hands over. Where that matters, say it in the caption or draw the hand-over as its own L4 diagram. A system boundary whose inside runs past the profile's `stack_after` columns is stacked the same way: the boundary lays out across, its neighbours sit above and below, and their arrows land on the boundary, not the box inside.
- A dropped optional path. Mark the edge `optional: true` and it draws dotted, with its label.
- A node or arrow that isn't in the code. Diagrams come from reading the code, never from imagination.
- An L2 to L4 diagram drawn without its parent. Open the parent first and reuse its ids, labels and objects. A box the parent lacks is a change to the parent in the same PR.
- ASCII art or a `text` block standing in for a diagram. Convert any you find on a page you edit to Mermaid, and never turn Mermaid into text or an image.
- An intro or caption that restates the picture, or names a colour or a dash. Words beside a diagram carry only what the picture can't show: why, the limits, what is optional.
- Hexagons, `graph TD` and `style` lines. Lint fails them.
- A copy of every Availability Zone. Draw the zone once, labelled with its count (`Availability Zones x2`), with one subnet group per tier inside it and one node per tier (`Web servers`, subtitle `Auto Scaling group`). Mermaid can't draw a group that crosses another, so an Auto Scaling group or subnet group that spans zones becomes a subtitle, not a group. Say how many zones in the description.
