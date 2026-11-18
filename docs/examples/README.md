# Worked examples

Each folder holds a diagram file, the Mermaid merrow writes from it, and light and dark SVGs. `make examples` regenerates them all. The AWS ones need `merrow pack build aws-icons aws-groups` first, the Kubernetes one `merrow pack build kubernetes-icons`.

| Example | Profile | What it shows |
|---|---|---|
| [pipeline/](pipeline/) | house | The README's quick start: three boxes and two arrows |
| [aws-web-app/](aws-web-app/) | aws | A classic web app on AWS, two Availability Zones drawn as one zone x2 |
| [aws-commerce/](aws-commerce/) | aws | An ecommerce deployment built mostly from the generated AWS objects |
| [kubernetes/](kubernetes/) | k8s | Kubernetes icons through a profile a reference repo defines with `extends: house` |
| [c4-big-bank/](c4-big-bank/) | house | A C4 system context and its services view, the second stacked around its boundary |

The `reference/` folders are small reference repos. Point `MERROW_REFERENCES` at one to draw its example.
