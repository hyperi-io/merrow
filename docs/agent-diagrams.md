<!-- Project: HyperI AI -->

# Diagrams -- the /docs procedure

Every RULE about diagrams is `standards/universal/diagrams.md`: the ten rules, the levels L0 to L4, layout and lines, the role palette, the page wrapper, the templates and the rules for generators. Its short form is section 19 of `standards/rules/universal.md`. Read one of them before drawing or judging a diagram. This file is how `/docs` runs the gate.

## The gate

Nobody writing Mermaid can see the layout from the source, and LLM-drafted Mermaid gets both syntax and layout wrong. So every page `/docs` touched goes through the checker:

```bash
uv run ~/.local/share/hyperi-ai/tools/diagram_check.py <page.md>... --png .hyperi-ai/tmp/diagrams
```

- One verdict line a diagram: `ok` or `FAIL`, the rendered size, and the node and arrow counts. Findings sit under it, each naming its rule.
- Fix every finding on a diagram this run wrote or touched, and run it again. Layout findings are fixed with the repair ladder in the standard, never with `linkStyle` or config.
- Open the light and the dark screenshot of each diagram written. The checker cannot see contrast, lines that run on top of each other, or a node that is not in the code. It measures lines in flowcharts alone, so a sequence, state, ER or class diagram is judged from its screenshot.
- Terminal output with table borders (`+----+`) goes in a `console` fence. In a `text` or untagged fence it is reported as a text-box diagram.
- No Chrome on the host: run it with `--no-render`, which is the source pass alone, and say "not rendered" in the report. Never claim the render pass ran.
- A diagram on the page that this run did not touch is reported, not fixed, unless the run is `--diagrams`.

## Convergence -- `/docs --diagrams`

Converge a repo's existing diagrams to the standard as they are touched. `--diagrams` is that pass across a whole repo, one page at a time, checker run after each.

| Found | Becomes |
|---|---|
| `graph`, `TD`, a long top-down chain | `flowchart LR`, or stage subgraphs with `direction LR` |
| A text-box diagram in a `text` fence | Mermaid |
| `style` lines, made-up `classDef` names and colours | The standard's class lines, by role |
| No `accTitle`, `accDescr`, intro sentence or caption | The page wrapper, with the level in the title |
| More than 12 nodes, or two levels in one diagram | A parent and its child diagrams, linked `Up` and `Down` |
| `block-beta`, `C4Context`, `gantt` | A flowchart, or a table |

The nodes and arrows come from the code and the existing diagram, never from imagination. A redraw that drops or adds an arrow is a `DOC-FACT-1` finding.

## The gate ids

| Id | Fails when |
|---|---|
| `DOC-DIAG-1` | The checker prints `FAIL` for a diagram this run wrote or touched |
| `DOC-DIAG-4` | A diagram a human would squint at in its screenshot -- see `standards/universal/diagrams.md`, "Review checklist" |
| `DOC-FACT-1` | A node or arrow that is not in the code -- diagrams come from analysis, never imagination |
