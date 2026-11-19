# Project:   merrow
# File:      Makefile
# Purpose:   CI targets wrapping hyperi-ci
#
# License:   Apache-2.0
# Copyright: (c) 2026 HYPERI PTY LIMITED

.PHONY: quality test build check starter examples

quality:
	hyperi-ci run quality

test:
	hyperi-ci run test

build:
	hyperi-ci run build

check:
	hyperi-ci check

# Rebuild the starter pack merrow ships, after a Carbon bump.
starter:
	env MERROW_PACKS_DIR=src/merrow/packs uv run merrow pack build starter-icons

# Regenerate every worked example's Mermaid and SVGs. The AWS cases need
# `merrow pack build aws-icons aws-groups` first, the Kubernetes one
# `merrow pack build kubernetes-icons`, the Flink one `carbon-icons` and the
# OpenShift one `redhat-icons`.
examples:
	uv run merrow graph render docs/examples/pipeline/pipeline.yaml --out docs/examples/pipeline
	uv run merrow graph render docs/examples/aws-web-app/web-app-edge.yaml docs/examples/aws-web-app/web-app-tiers.yaml --out docs/examples/aws-web-app
	uv run merrow graph render docs/examples/aws-commerce/commerce-edge.yaml docs/examples/aws-commerce/commerce-app.yaml --out docs/examples/aws-commerce
	env MERROW_REFERENCES='["docs/examples/kubernetes/reference"]' uv run merrow graph render --profile k8s docs/examples/kubernetes/components.yaml --out docs/examples/kubernetes
	env MERROW_REFERENCES='["docs/examples/c4-big-bank/reference"]' uv run merrow graph render docs/examples/c4-big-bank/context.yaml docs/examples/c4-big-bank/containers.yaml --out docs/examples/c4-big-bank
	uv run merrow graph render docs/examples/bpmn-order/order.yaml docs/examples/bpmn-order/create-invoice.yaml --out docs/examples/bpmn-order
	uv run merrow diagram apply docs/examples/oidc-login/login.md
	uv run merrow diagram render docs/examples/oidc-login/login.md --out docs/examples/oidc-login
	uv run merrow graph render docs/examples/campus-network/campus.yaml --out docs/examples/campus-network
	uv run merrow graph render docs/examples/flink-platform/flink.yaml --out docs/examples/flink-platform
	uv run merrow graph render docs/examples/openshift-platform/openshift.yaml --out docs/examples/openshift-platform
