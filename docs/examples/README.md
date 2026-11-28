# Worked examples

Each folder holds a diagram file, the Mermaid merrow writes from it, and light and dark SVGs. `make examples` regenerates them all. The AWS ones need `merrow pack build aws-icons aws-groups` first, the Kubernetes one `merrow pack build kubernetes-icons`, the Flink one `carbon-icons` and the OpenShift one `redhat-icons`.

| Example | Profile | What it shows |
|---|---|---|
| [pipeline/](pipeline/) | house | The README's quick start: three boxes and two arrows |
| [aws-web-app/](aws-web-app/) | aws | A classic web app on AWS in two diagrams, its edge and its tiers, two Availability Zones drawn as one zone x2. `web-app-slide` is the whole of it at deck size, rendered and linted with `--destination slide` |
| [aws-commerce/](aws-commerce/) | aws | An ecommerce deployment built mostly from the generated AWS objects, split into its edge and its application tier to fit a page |
| [kubernetes/](kubernetes/) | k8s | Kubernetes icons through a profile a reference repo defines with `extends: house` |
| [c4-big-bank/](c4-big-bank/) | house | A C4 system context and its services view, the second stacked around its boundary |
| [bpmn-order/](bpmn-order/) | house | A BPMN order process from Camunda's examples (Apache-2.0): a collapsed sub-process, a boundary path and its inside |
| [oidc-login/](oidc-login/) | house | The OAuth 2.0 authorization code flow with OpenID Connect's steps (RFC 6749 Section 4.1, OpenID Connect Core 1.0 Section 3.1.1), a sequence diagram on a Markdown page |
| [campus-network/](campus-network/) | house | The three-layer campus network model from Wikipedia's Hierarchical internetworking model, one group a layer |
| [flink-platform/](flink-platform/) | house | An Apache Flink cluster reading Kafka and writing Iceberg, from the Flink Architecture documentation on apache.org |
| [openshift-platform/](openshift-platform/) | house | OpenShift's control plane Operators and compute machines, from the OpenShift Container Platform documentation (Apache-2.0), with Red Hat icons |

The `reference/` folders are small reference repos. Point `MERROW_REFERENCES` at one to draw its example.
