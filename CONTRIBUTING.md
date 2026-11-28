# Contributing to merrow

Two audiences, two paths.

## External contributors - the short path

**You do NOT need to install `hyperi-ci` or activate any
repo-local git hooks.** Standard tooling is enough.

1. Fork the repository, clone your fork, create a topic branch.
2. Make your change. Run `uv run pytest -n 2`, `uv run ruff check` and `uv run ty check`. The render tests need playwright's headless shell, which `merrow tools ensure` installs. The maintainers' full gate is `hyperi-ci check`, which also runs semgrep and the docs checks.
3. Commit with whatever message format your workflow uses.
   Open a PR against `main`.

**What happens to your PR's CI checks:**

PRs from forks intentionally do not auto-trigger this repo's
full CI pipeline. You will see green checks because all jobs
are skipped, not because they ran and passed. A maintainer
will pull your PR locally to validate it against the full
pipeline. This avoids exposing internal CI credentials and
self-hosted runners to fork-originated workflows, which is the
standard GitHub-side security recommendation.

If a maintainer requests changes, push to the same branch on
your fork. They will re-validate.

## Maintainers - the strict path

Maintainers opt in to the project's stricter tooling:

```bash
# install the CLI
uv tool install hyperi-ci          # or: pipx install hyperi-ci

# activate the repo-local git hooks (commit-msg validation +
# pre-push enforcement of `hyperi-ci push` over bare `git push`)
git config core.hooksPath .githooks

# verify
hyperi-ci --version
hyperi-ci check                    # quality + test, pre-push gate
```

Maintainer workflow:

1. Land changes on `main` via PR or direct push (your call).
2. `hyperi-ci push` instead of `git push`. The pre-push hook
   enforces this. Bypass it with `HYPERCI_PUSH=1 git push` if you
   know what you are doing.
3. `hyperi-ci push --release` when you want to ship a release.
   It amends a `Release: true` trailer to HEAD. The CI pipeline
   picks that up, predicts the next version, stamps it, and
   publishes.

## What happens when you push commits to your fork

Nothing on this repo's side. Your fork has a separate GitHub
Actions context, and this repo's workflows are not triggered until
you open a PR. Your fork's CI (if you enabled it) runs in
your namespace.

## Commit message conventions

Maintainers follow Conventional Commits and the hooks enforce
it. External contributors do not need to follow this format --
the maintainer who merges your PR rewrites the merge commit
as needed.

## Security disclosures

Do NOT open a public issue or PR for security vulnerabilities.
See the repository's `SECURITY.md` (if present) or the
organisation's security contact for the disclosure process.

## Context

### What this is

merrow is a CLI that turns a diagram file or hand-written Mermaid into Mermaid in a profile's look, renders it to SVG and lints it. It is company-neutral: no company's objects, colours or names live here, and a test fails if one creeps in. Those belong in a reference repo, loaded as a config layer.

### Where things live

| Path | Holds |
|---|---|
| `src/merrow/cli.py` | Every command, `merrow <noun> <verb>` |
| `src/merrow/*.yaml` | The base config layer: defaults, sources, profiles, patterns, objects |
| `src/merrow/write.py`, `compose.py` | Graph to Mermaid: labels, classes, rows, stacked boundaries, stages |
| `src/merrow/render.py`, `bundle.py`, `browser.py` | Mermaid to SVG in a playwright page |
| `src/merrow/lint/diagram_check.py` | The standard's checks |
| `style/` | The diagram standard and templates lint holds diagrams to |
| `docs/diagrams/` | Sources for the diagrams in `docs/architecture.md` |

### Commands that test a change

`hyperi-ci check` runs the quality gates and the tests. `uv run pytest -n 2` alone misses ruff, ty, semgrep and the docs checks. Render tests launch playwright's headless shell, which `merrow tools ensure` installs. On Debian and Ubuntu it needs Chrome's system libraries: `merrow tools ensure --install-deps` asks sudo for them.

### What tends to bite

| Don't | Do | Why |
|---|---|---|
| Commit an icon pack, a publisher download or a render with publisher icons in a test fixture | Build packs into the cache, fake them in tests | Publisher terms bar redistribution |
| Name a company or product in merrow | Put it in a reference repo | `tests/test_neutral.py` fails the build |
| Hard-code a value | Add it to the YAML config | Every tunable goes through the cascade |
| Type `classDef` or `style` lines in a diagram | Use a profile and objects | Lint fails any styling inside a diagram |
| Lock a dependency right after its release with a warm uv cache | `uv lock --refresh` | uv serves the old index from its cache |

### Where this sits

merrow depends on scalo-py (config, logging, HTTP) and on hyperi-ci for its CI. Reference repos are read by merrow as config layers and depend on its profile and object formats. A product docs repo pins a release for its diagram generator, and hyperi-ai pins `merrow[all]`, so a change reaches them only through a release.
