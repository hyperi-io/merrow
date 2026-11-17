# Diagram standard research

Why [`style/diagrams.md`](../style/diagrams.md) says what it says: the sources, the decisions, the test evidence and what is still unverified. Nobody needs this page to follow the standard.

## Problem

- LLM-written docs drift from Mermaid to text-box diagrams. One product's internals page drew its architecture with box-drawing characters in a `text` fence.
- When an LLM does write Mermaid, the structure is right and the presentation is poor: tall `graph TD` chains that waste the page width, no colour or arbitrary colour, lines that cross and run through boxes, and one diagram that tries to show everything.
- The earlier standard set a node cap, a five-colour brand palette and a shape list. It gave no way to split a system across diagrams, no layout method, and no check an author could run.

## Sources and what we took

| Source | What it says | What we took |
|---|---|---|
| [C4 model, diagrams](https://c4model.com/diagrams) | Four zoom levels: context, containers, components, code. Context and container diagrams are enough for most teams | The levels L1 to L4, and "expand only what the docs explain" |
| [C4 model, notation](https://c4model.com/diagrams/notation) | Every diagram has a title stating type and scope, and a key | Title format, the caption as the key, one level per diagram |
| [C4 review checklist](https://c4model.com/diagrams/checklist) | Yes/no questions on title, scope, element naming and relationships | The review checklist |
| Data flow diagram levelling (Yourdon and DeMarco, Gane and Sarson), [summary](https://www.w3computing.com/systemsanalysis/developing-data-flow-diagrams) | A child diagram cannot have inputs or outputs its parent process lacks ("balancing") | The balance rule |
| IDEF0, FIPS PUB 183, [summary](https://support.unicomsi.com/manuals/systemarchitect/11482/Architecting_and_designing/IDEF.22.21.html) | A child diagram has 3 to 6 boxes, and fewer than 3 is not decomposed | The fan-out rule, at 3 to 7 |
| ISO 5807:1985 | Standard flowchart symbols | The five node outlines. The subroutine symbol marks a process described elsewhere |
| Moody, "The 'Physics' of Notations", IEEE TSE 35(6), 2009 | One symbol per concept, symbols easy to tell apart, text with graphics, complexity managed explicitly | Outline and colour rules, the node limit, the levels |
| Purchase, ["Which aesthetic has the greatest effect on human understanding?"](https://eprints.gla.ac.uk/35804), 1997 | Edge crossings harm comprehension most. Bends and symmetry matter less | R4: zero crossings ranks above every other line rule |
| Purchase, "Metrics for Graph Drawing Aesthetics", JVLC 13, 2002 | Crossings, bends, symmetry, orthogonality, consistent flow direction | No back arrows, one flow direction |
| Cowan 2001, and Jones, "The 7 plus or minus 2 Urban Legend" | Working memory holds about 4 chunks, and chunking is what helps | Subgraphs as chunks, 4 subgraphs, 4 colour classes |
| Mayer and Fiorella, Cambridge Handbook of Multimedia Learning, 2014 | Coherence: extraneous material cuts learning (23 of 23 experiments). Spatial contiguity is the strongest effect (22 of 22) | Colour encodes a role or is absent. The diagram sits beside its prose |
| [WCAG 2.2 SC 1.4.1](https://w3.org/WAI/WCAG22/Understanding/use-of-color.html) | Colour must not be the only way information is conveyed | "Colour never carries meaning alone" |
| WCAG 2.2 SC 1.4.3 and 1.4.11 | 4.5:1 for text, 3:1 for graphical objects | The palette thresholds |
| Okabe and Ito, Colour Universal Design | Eight hues that stay distinct under common colour-vision deficiencies | The palette's hues. Borders darkened and fills tinted, because raw orange (2.25) and sky blue (2.31) fail 3:1 on white |
| [Mermaid, flowchart](https://mermaid.js.org/syntax/flowchart.html) | Subgraph direction limitation, link length, invisible links, `classDef`, reserved words | Layout patterns, the invisible link in the repair ladder, syntax traps |
| [Mermaid, theming](https://mermaid.js.org/config/theming.html) | The `base` theme alone is customisable, and v12 changed defaults | Nodes styled with `classDef`, never themes |
| [Mermaid, accessibility](https://mermaid.js.org/config/accessibility.html) | `accTitle` and `accDescr` become the SVG `<title>` and `<desc>` | R7 |
| [GitLab docs style guide, images and diagrams](https://docs.gitlab.com/development/documentation/styleguide/images_and_diagrams/) | A diagram needs an introductory sentence and must be accessible | The page wrapper |
| [Kubernetes diagram guide](https://kubernetes.io/docs/contribute/style/diagram-guide/) | Mermaid inline in Markdown, a caption under every diagram, `classDef` for styling | The page wrapper, and prior art for Mermaid alone |
| [Docusaurus, diagrams](https://docusaurus.io/docs/markdown-features/diagrams) | Light and dark Mermaid themes are set in site config | "Actions for a docs site owner" |

## Decisions

| Decision | Why |
|---|---|
| Mermaid alone | Text in the repo, diffable, renders to scalable SVG on GitHub and every docs generator we use |
| `flowchart LR` by default | Docs columns are wide and short. An 11-step `TD` chain rendered 168 x 944 px, and the same steps staged rendered 744 x 465 px |
| 5 columns, 1250 px natural width | Mermaid scales a wide diagram down to the column. Past about 1250 px, 16 px text drops under 11 px in an 860 px column |
| 12 nodes | Published Mermaid style guides cap at 15 to 20. Lower leaves room for a child diagram's neighbours |
| Five diagram types | Fewer types, fewer ways to be inconsistent. Wire formats and schedules read better as tables. `classDiagram` stays for trait and interface hierarchies, which Rust and TypeScript docs draw |
| Five outlines, bracket syntax | Bracket syntax works in every Mermaid release. The `@{ shape }` syntax needs 11.3.0 or later |
| External systems are rectangles with a dashed border | The dash carries the meaning without colour, and one outline fewer has to be learned |
| Dotted arrows mean async, optional or failure | One non-main style covers the three cases a reader needs told apart from the main path, and the caption says which |
| Colour by role, class lines copied byte for byte | A byte-identical line is checked by string comparison, and no colour decision is left to the author |
| A diagram copies the class lines it uses | The check is the same as for a whole block, and a diagram costs fewer tokens |
| Nodes hold fill, border and text colour | A node reads the same on a white or a dark page. Arrows and titles are left to the site theme, which switches by itself |
| No colour in sequence diagrams | A pale `box` fill under the dark theme's light text is unreadable |
| No per-diagram config | Theme and layout belong to the site. Per-diagram overrides are how diagrams drift apart |
| No `click` | Links live in the caption, where a link checker reads them |
| Level names Context, Services, Components, Detail | C4's levels, with "container" renamed to "service" so nobody reads it as a Docker container |
| L4 is the catch-all | Every diagram then has a level and a parent, and no "standalone" category exists to argue about |
| Boundary arrows match the parent | From DFD balancing. Parent and child consistency becomes a mechanical check |
| Stacked boundary form attaches arrows to the boundary | Forced by Mermaid: a subgraph's `direction` is ignored once an inner node links outside |
| Column plan before code | The layout cannot be seen from the source. Planning columns and rows first is the cheapest way to avoid crossings |
| The proportion holds flowcharts and state diagrams | A two-relationship ER diagram renders 147 x 470, taller than wide by its nature. Sequence, ER and class diagrams are held by the width and height limits alone |
| No longer links in the repair ladder | `a ---> b` is ignored by Mermaid 12.3.0 and makes a skip arrow on 11.17.2 |
| A queue or topic is `async`, a table or database is `store` | Both are cylinders. Naming each thing in one class stops two authors colouring a topic two ways |
| No shared pairs | Two nodes in one column that both link to the same two nodes in the next form a cycle between two columns, which cannot be drawn without a crossing |
| Intro sentence reads "This diagram shows" | The rule is GitLab's. The wording avoids "the following" |
| The standard, this page and the agent summary are three files | The standard is instructions alone, so an agent loads it without the reasoning |

## Test evidence

### Template sizes

Natural SVG size in px, measured by the checker in Chrome 157 in an 860 px column. Light and dark are identical.

| Template | Mermaid 12.3.0 | Mermaid 11.17.2 |
|---|---|---|
| L1 Context | 834 x 261 | 1033 x 169 |
| L2 Services, straight boundary | 1178 x 341 | 853 x 301 |
| L3 Components, stacked boundary | 756 x 523 | 732 x 437 |
| L4 stacked stages | 744 x 465 | 812 x 488 |
| L4 decision flow | 958 x 278 | 662 x 244 |
| L4 side by side | 632 x 187 | 948 x 169 |
| L4 sequence | 700 x 534 | 700 x 486 |
| L4 state | 925 x 136 | 645 x 146 |

All eight pass the checker's source and render passes on both releases.

### Behaviours confirmed by rendering

| Finding | Detail |
|---|---|
| Mermaid 12 lays out wider than 11 | The L2 template: 1178 px against 853 px from one source |
| Mermaid 12 routes lines at right angles | 11.17.2 draws curves. The same nine-arrow diagram reports 9 crossings on 12.3.0 and 7 crossings plus 2 lines through a box on 11.17.2 |
| A subgraph's `direction` is ignored when an inner node links outside | `flowchart TB` with an LR subgraph and inner cross-links rendered 344 x 731 (v12), a vertical strip. Linking the subgraph gave 744 x 459 |
| A six-column LR child diagram is too wide | Four inner steps and two neighbours: 1265 px in v12 |
| A coloured `box` in a sequence diagram fails in dark mode | Light theme text on a pale fill. An uncoloured `box` is fine |
| `click ... href` renders a link under `securityLevel: strict` | The anchor is present in the SVG in both versions |
| A labelled arrow is one column longer than a plain one | A source with one plain and one labelled arrow to two free boxes puts the labelled box a column further out (552 x 152), and the checker reports a skip arrow. Where both boxes feed one sink they share a column (639 x 152) |
| A longer link (`a ---> b`) is no repair | On 12.3.0 the node stays in its column. On 11.17.2 it moves, and the arrow jumps the box between |
| `maid` 0.0.29 rejects `accTitle` and `accDescr` in a flowchart | It reports `FL-LINK-MISSING` on the line, so it cannot check a diagram written to R7 |

The first two rows and the last three were measured with the checker. The other four come from renders made while the rules were drafted and were not re-run.

### Palette contrast

WCAG contrast ratios. Thresholds are 4.5:1 for text and 3:1 for graphics. The canvases are white, GitHub dark `#0D1117` and the docs site dark `#1B1B1D`.

| Class | Text on fill | Border on fill | Border on white | Border on `#0D1117` | Border on `#1B1B1D` |
|---|---|---|---|---|---|
| `default` | 17.06 | 4.55 | 4.76 | 3.98 | 3.61 |
| `core` | 12.19 | 4.26 | 5.19 | 3.65 | 3.32 |
| `store` | 11.93 | 4.72 | 5.48 | 3.46 | 3.14 |
| `async` | 13.07 | 4.21 | 5.06 | 3.74 | 3.40 |
| `decision` | 12.22 | 4.33 | 4.87 | 3.89 | 3.53 |
| `error` | 11.84 | 4.21 | 5.18 | 3.65 | 3.32 |
| `ext` | 12.85 | 4.23 | 4.83 | 3.91 | 3.56 |

A typical brand set fails here: a light blue passes on dark and fails on white, and a navy does the reverse. So `core` keeps the Okabe-Ito blue, and a brand colour goes in a reference repo with one value per theme.

### The checker

`merrow diagram lint` was run on diagrams built to break one rule each, on both Mermaid releases.

| Diagram | Expect | Mermaid 12.3.0 | Mermaid 11.17.2 |
|---|---|---|---|
| Two sources into the same two targets | 1 crossing | 1 crossing | 1 crossing |
| One source into three steps into one sink | 0 crossings, though arrows share a box | 0 | 0 |
| Three sources into the same three targets | 9 crossings as straight lines, and too many arrows | 9 crossings, 9 arrows on 6 nodes | 7 crossings, 2 lines through a box, 9 arrows on 6 nodes |
| A four-step chain with one skip arrow and two back arrows | The skip arrow and both back arrows | Found | Found |
| A skip arrow inside a left-to-right stage of a top-down chart | The skip arrow | Found | Found |
| `graph TD` with an init directive, `style`, `click`, a thick and a double-headed arrow, a circle and a made-up class | Each fault named | 11 source findings | Not run |

Five diagrams from those product docs were then redrawn to the standard. The checker failed three of the redraws on the first try, two for width and one for proportion, and all six resulting diagrams pass. That run found two gaps in the standard, which it now covers: three decision diamonds in a row leave no room for a start node, and an arrow touching the `core` box is labelled.

It was first run, read-only, over nine pages of one product's docs holding 29 diagrams. Every diagram failed, which is expected of pages written before the standard. The verdicts on its routing page (871 x 1234, no crossings, three skip arrows, six arrows into one box) were compared with the screenshot and match. It found one text-box diagram and one diagram that no longer parses on Mermaid 12.3.0.

Across that product's four repos' `docs/` trees: 165 Markdown files, 62 with diagrams, 36 top-down flowcharts, 69 left-to-right, 18 of other types, and none with `accTitle` or `accDescr`.

## Not verified

| Item | Status |
|---|---|
| Source order controls row order | Common practice for Mermaid's layered layouts. Shuffling declaration order and counting crossings was not done |
| The order of the repair ladder | The invisible link is a documented Mermaid feature. The order of the steps is judgement |
| The screenshots' themes | `neutral` and `dark`. GitHub's own theme was not tested |
| Which arrow is named as against the flow | The checker reads the layout. When two feedback arrows push the start node to the right, a forward arrow can be the one it names |
| Arrow limits: nodes plus 2, and 5 on one node | Our thresholds, from no source |
| The 860 px content column | Assumed. Measure the docs site's column and adjust the 1250 px limit |
| Which Mermaid release the docs site and GitHub run | Unknown. The checker pins 12.3.0 and takes another bundle with `--mermaid` |
| Rendering on GitHub | Not tested |
| The full eight-line class block in `stateDiagram-v2` | Not tested, so a state diagram copies the lines it uses |
| Lines that run on top of each other | The checker does not report them. Right-angle routing in Mermaid 12 makes them more common |
| Lines in sequence, state, ER and class diagrams | The checker measures their size alone. Its line checks read flowchart arrows |
| A crossing that falls exactly on a sampled point | An earlier build missed one of the nine crossings above for this reason. No diagram was built to hit the case on purpose |
| The checker's skip-arrow test on diagrams with nested subgraphs | Run on flat diagrams and the product pages. No nested case was built to break it |

## Actions for a docs site owner

- Pin the Mermaid release. Layout and line routing changed between 11 and 12.
- Set the theme pair once in the site config. The templates were tested with `neutral` for light and `dark` for dark.
- Set `layout` and `look` in the site's Mermaid options, so an upgrade does not restyle every diagram.
- Run the checker's source pass in CI on changed pages. The render pass needs Chrome.

## Rejected options

| Option | Why not |
|---|---|
| Brand colours as the diagram palette | A brand hue rarely passes 3:1 on both a light and a dark canvas. A company that wants its own sets them in its reference repo, per theme |
| A custom `base` theme with `themeVariables` | They apply to one theme, so one set of values has to serve light and dark. Node classes avoid the problem |
| Raw Okabe-Ito hues as fills | Too saturated for large fills, and several fail 3:1 on white |
| Mermaid `C4Context` diagrams | Experimental in Mermaid for years, with little layout control. Flowcharts drawn to C4's rules render better |
| `architecture-beta`, `block-beta` | Beta, so they change between Mermaid releases |
| ELK or dagre chosen per diagram | The layout engine is a site decision. A per-diagram choice makes the result depend on who wrote the diagram |
| DFD-style numeric IDs (1, 1.2, 1.2.3) | Numbers break when the structure changes. A title with level and scope is stable |
| A "standalone" diagram with no level | It becomes the default way out |
| `maid` as the parse check | It rejects the accessibility lines R7 needs, and it never renders |
| `mermaid-cli` as the renderer | It writes an SVG file and gives no geometry, so crossings would need a second SVG path parser |
| `mermaids-comb` for the crossing check | It counts crossings and can reorder a diagram to remove them, but it has one author, one release and three weeks of history |
| Mermaid's `validateLayout` | A test helper inside the Mermaid repo for authors of right-angle layouts. It is not a public API |
