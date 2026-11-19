# Architecture

merrow turns a description of a diagram into Mermaid in a fixed look, then renders and checks it. A diagram file goes through the writer, render and lint in that order, fed by icon packs and config.

```mermaid
---
config:
  theme: base
  look: neo
  fontFamily: Inter, -apple-system, Segoe UI, Roboto, Helvetica, Arial, sans-serif
  flowchart:
    curve: linear
    nodeSpacing: 40
    rankSpacing: 64
    padding: 18
    wrappingWidth: 280
    htmlLabels: true
  elk:
    preset: modelOrder
  themeVariables:
    fontSize: 15px
    lineColor: "#64748B"
    primaryTextColor: "#0F172A"
    clusterBorder: "#0072B2"
    edgeLabelBackground: "#FFFFFF"
  themeCSS: >-
    p{margin:0}
    .node[data-look] rect,.node[data-look] path,.node[data-look] polygon,.node[data-look] .outer-path{filter:drop-shadow(0 1px 2px rgba(15,23,42,.10)) drop-shadow(0 6px 14px rgba(15,23,42,.10))}
    .node rect{rx:10px;ry:10px}
    .cluster rect{rx:16px;ry:16px}
    .node .label div{min-width:150px}
    .node.decision .label div{min-width:0}
    .cluster[data-look] rect{filter:none}
    .nodeLabel{line-height:1.35}
    .nodeLabel b{font-weight:600;font-size:15px;letter-spacing:-0.01em}
    .nodeLabel span{font-size:12.5px;font-weight:400;color:#334155}
    .cluster-label span.nodeLabel{display:inline-block;background:#FFFFFF;color:#0B2A3F;border:1.5px solid #0072B2;border-radius:999px;padding:2px 12px;font-size:11.5px;font-weight:700;letter-spacing:.09em;text-transform:uppercase}
    .flowchart-link{stroke-width:1.75px}
    .labelBkg{background:transparent!important}
    span.edgeLabel{display:inline-block;background:#FFFFFF!important;color:#1E293B;border:1px solid #94A3B8;border-radius:999px;padding:2px 10px;font-size:12px;font-weight:500}
    span.edgeLabel p{background:transparent!important}
    .label-icon{width:20px;height:20px;vertical-align:-4px;margin-right:6px}
    .ingest .label-icon{color:#0E8A7D}
    .xform .label-icon{color:#7B4FB0}
    .load .label-icon{color:#0072B2}
    .bus .label-icon{color:#A8517F}
    .store .label-icon{color:#00785A}
    .ui .label-icon{color:#D9480F}
    .ext .label-icon{color:#64748B}
---
flowchart TB
  accTitle: L2 Services -- merrow
  accDescr: Publisher downloads become icon packs. A diagram file and the config layers go to the writer, which emits Mermaid in a profile's look. Render draws it to SVG in a browser page, and lint measures it.
  publishers("<b>Icon publishers</b>")
  refs("<b>Reference repos</b>")
  authors("<b>People and agents</b>")
  docs("<b>Docs pages</b>")
  subgraph merrow["merrow"]
    direction LR
    sources("<b>Sources</b><br/><span>fetch and pin</span>")
    packs("<b>Icon packs</b><br/><span>converters</span>")
    config("<b>Config cascade</b><br/><span>objects and profiles</span>")
    writer("<b>Writer</b><br/><span>graph to Mermaid</span>")
    render("<b>Render</b><br/><span>SVG in a browser page</span>")
    lint("<b>Lint</b><br/><span>the standard's checks</span>")
  end
  sources --> packs
  packs --> writer
  config --> writer
  writer --> render
  render --> lint
  publishers -->|"downloads"| merrow
  refs -->|"layers"| merrow
  authors -->|"diagram files"| merrow
  merrow -->|"SVG"| docs
  class publishers,refs,authors,sources,packs,config,writer,render,lint,docs part
  classDef ingest fill:#FFFFFF,stroke:#0E8A7D,stroke-width:3px,color:#0F172A
  classDef xform fill:#FFFFFF,stroke:#7B4FB0,stroke-width:3px,color:#0F172A
  classDef load fill:#FFFFFF,stroke:#0072B2,stroke-width:3px,color:#0F172A
  classDef bus fill:#FFFFFF,stroke:#A8517F,stroke-width:3px,color:#0F172A
  classDef store fill:#FFFFFF,stroke:#00785A,stroke-width:3px,color:#0F172A
  classDef ui fill:#FFFFFF,stroke:#D9480F,stroke-width:3px,color:#0F172A
  classDef ext fill:#F4F6F8,stroke:#94A3B8,stroke-width:1.5px,stroke-dasharray:5 4,color:#0F172A
  classDef decision fill:#FFFFFF,stroke:#9A6700,stroke-width:3px,color:#0F172A
  classDef error fill:#FFFFFF,stroke:#C2410C,stroke-width:3px,color:#0F172A
  classDef control fill:#FFFFFF,stroke:#334155,stroke-width:3px,color:#0F172A
  classDef part fill:#FFFFFF,stroke:#94A3B8,stroke-width:1.5px,color:#0F172A
  style merrow fill:none,stroke:#0072B2,stroke-width:1.5px,stroke-dasharray:6 4
```

*Figure 1. L2 Services -- merrow.* Up: [L1 Context -- merrow](#everything-a-company-owns-comes-in-from-outside).

## Components

Each box in Figure 1, where its code lives and what it decides.

| Part | Code | What it decides |
|---|---|---|
| Sources | `src/merrow/sources/`, `sources.yaml`, `sources.lock.yaml` | Which publisher download, pinned by version and checksum, and when a release is out |
| Icon packs | `src/merrow/convert/`, `naming.py` | Each publisher file's icon key and title. The artwork is never changed |
| Config cascade | `config.py`, `profile.py`, `destination.py`, `objects.py` | merrow's defaults, then each reference repo, then `settings.yaml` and `MERROW_*` |
| Writer | `write.py`, `compose.py`, `spec.py`, `patterns.py` | Node labels, classes, groups, rows, stacked boundaries and long chains in stages |
| Render | `render.py`, `post.py`, `bundle.py`, `browser.py` | Mermaid drawn by playwright in light and dark, then group icons placed |
| Lint | `lint/diagram_check.py` | The standard's source checks, then size, crossings and skip arrows on the render |

## Everything a company owns comes in from outside

Authors and agents write diagram files. merrow draws them with publisher icons and the objects and profiles from reference repos, and writes Mermaid and SVG for the docs.

```mermaid
---
config:
  theme: base
  look: neo
  fontFamily: Inter, -apple-system, Segoe UI, Roboto, Helvetica, Arial, sans-serif
  flowchart:
    curve: linear
    nodeSpacing: 40
    rankSpacing: 64
    padding: 18
    wrappingWidth: 280
    htmlLabels: true
  elk:
    preset: modelOrder
  themeVariables:
    fontSize: 15px
    lineColor: "#64748B"
    primaryTextColor: "#0F172A"
    clusterBorder: "#0072B2"
    edgeLabelBackground: "#FFFFFF"
  themeCSS: >-
    p{margin:0}
    .node[data-look] rect,.node[data-look] path,.node[data-look] polygon,.node[data-look] .outer-path{filter:drop-shadow(0 1px 2px rgba(15,23,42,.10)) drop-shadow(0 6px 14px rgba(15,23,42,.10))}
    .node rect{rx:10px;ry:10px}
    .cluster rect{rx:16px;ry:16px}
    .node .label div{min-width:150px}
    .node.decision .label div{min-width:0}
    .cluster[data-look] rect{filter:none}
    .nodeLabel{line-height:1.35}
    .nodeLabel b{font-weight:600;font-size:15px;letter-spacing:-0.01em}
    .nodeLabel span{font-size:12.5px;font-weight:400;color:#334155}
    .cluster-label span.nodeLabel{display:inline-block;background:#FFFFFF;color:#0B2A3F;border:1.5px solid #0072B2;border-radius:999px;padding:2px 12px;font-size:11.5px;font-weight:700;letter-spacing:.09em;text-transform:uppercase}
    .flowchart-link{stroke-width:1.75px}
    .labelBkg{background:transparent!important}
    span.edgeLabel{display:inline-block;background:#FFFFFF!important;color:#1E293B;border:1px solid #94A3B8;border-radius:999px;padding:2px 10px;font-size:12px;font-weight:500}
    span.edgeLabel p{background:transparent!important}
    .label-icon{width:20px;height:20px;vertical-align:-4px;margin-right:6px}
    .ingest .label-icon{color:#0E8A7D}
    .xform .label-icon{color:#7B4FB0}
    .load .label-icon{color:#0072B2}
    .bus .label-icon{color:#A8517F}
    .store .label-icon{color:#00785A}
    .ui .label-icon{color:#D9480F}
    .ext .label-icon{color:#64748B}
---
flowchart LR
  accTitle: L1 Context -- merrow
  accDescr: People and agents hand merrow diagram files. merrow draws them with icon downloads from publishers and objects and profiles from reference repos, and writes Mermaid and SVG for the docs.
  authors("<b>People and agents</b>")
  refs("<b>Reference repos</b><br/><span>objects and profiles</span>")
  publishers("<b>Icon publishers</b><br/><span>AWS, Kubernetes and more</span>")
  merrow("<b>merrow</b>")
  docs("<b>Docs pages</b><br/><span>Mermaid and SVG</span>")
  authors -->|"diagram files"| merrow
  refs -->|"config layers"| merrow
  publishers -->|"downloads"| merrow
  merrow -->|"diagrams"| docs
  class authors,refs,publishers,merrow,docs part
  classDef ingest fill:#FFFFFF,stroke:#0E8A7D,stroke-width:3px,color:#0F172A
  classDef xform fill:#FFFFFF,stroke:#7B4FB0,stroke-width:3px,color:#0F172A
  classDef load fill:#FFFFFF,stroke:#0072B2,stroke-width:3px,color:#0F172A
  classDef bus fill:#FFFFFF,stroke:#A8517F,stroke-width:3px,color:#0F172A
  classDef store fill:#FFFFFF,stroke:#00785A,stroke-width:3px,color:#0F172A
  classDef ui fill:#FFFFFF,stroke:#D9480F,stroke-width:3px,color:#0F172A
  classDef ext fill:#F4F6F8,stroke:#94A3B8,stroke-width:1.5px,stroke-dasharray:5 4,color:#0F172A
  classDef decision fill:#FFFFFF,stroke:#9A6700,stroke-width:3px,color:#0F172A
  classDef error fill:#FFFFFF,stroke:#C2410C,stroke-width:3px,color:#0F172A
  classDef control fill:#FFFFFF,stroke:#334155,stroke-width:3px,color:#0F172A
  classDef part fill:#FFFFFF,stroke:#94A3B8,stroke-width:1.5px,color:#0F172A
```

*Figure 2. L1 Context -- merrow.* Up: top of merrow. Down: Figure 1, L2 Services, above.

## A profile is the whole look, and a reference repo can extend one

A profile is a set of DTCG token files plus templates in `profiles.yaml`. `house` is merrow's neutral look. `aws` draws AWS icons at their artwork size with the group styles from AWS's deck. A reference repo adds a token file to restyle a profile, or defines a profile with `extends:` and names just what changes.

## A destination is where the diagram is published

A destination in `destinations.yaml` holds what depends on the page: the column, the width and height limits, and the themes rendered to SVG. `page` is a docs page and the default, and `slide` is a deck. The profile and the destination are set separately, so `aws` lints for a page or a slide with no second profile. A reference repo defines a destination with `extends:`, such as a docs site with a 692 px column.

## Objects are drawn the same everywhere

An object is a thing with a label, a class or an icon, defined once. Every titled icon in a pack that `generated_objects` lists becomes an object by itself, such as `aws.amazon-ec2` from the AWS pack or `k8s.sts` from the Kubernetes one. merrow ships one pack, `starter`: 34 generic Carbon icons drawn as `icon.server` and the like with nothing built, and a built pack of the same name wins over it. A title comes from a `names` rule, or from the source's `titles` map where file names are abbreviations. A reference repo adds its objects, and an entry it writes wins over a generated one. A diagram file can carry its own `objects:` block for things only it draws, and those win for that file alone.

## What merrow won't do

It won't redistribute a publisher's icons: packs are built into a cache outside every repo. It won't draw a group that crosses another, because Mermaid can't. A multi-zone deployment draws one zone labelled with its count.
