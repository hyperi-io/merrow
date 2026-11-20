#!/usr/bin/env bash
# Install merrow from this checkout on Linux or macOS: uv if missing, the
# merrow CLI, the pinned Mermaid bundle and the browser it renders in.
set -euo pipefail

# The uv fetched when the host has none. Each hash is the release's .sha256,
# checked against its GitHub attestation. Bump the version and all four together.
UV_VERSION="0.13.7"
TMP_DIR=""

die() {
    echo "merrow install: ${1}" >&2
    exit 1
}

cleanup() {
    [[ -z "${TMP_DIR}" ]] || rm -rf "${TMP_DIR}"
}

uv_target() {
    local arch
    arch="$(uname -m)"
    case "${arch}" in
        arm64) arch="aarch64" ;;
    esac
    case "$(uname -s)" in
        Linux) echo "${arch}-unknown-linux-gnu" ;;
        *) echo "${arch}-apple-darwin" ;;
    esac
}

uv_sha256() {
    case "${1}" in
        x86_64-unknown-linux-gnu) echo "c5221ff41b7892bfc223543883600125f6a47fe845093e0f5bdff4f359196d83" ;;
        aarch64-unknown-linux-gnu) echo "71279f8d3c67241e807b9d8db872d1bf541579fb9f08b7d1eb1682196d1e57dc" ;;
        x86_64-apple-darwin) echo "20c47e4c1f630b8abaff8c291fa9b9aa300fef92c4fbff95adf198b55287cda7" ;;
        aarch64-apple-darwin) echo "81b811b57e4624df7ed3aac148e0359100d9962f3d9dce00aec533dc2e086731" ;;
        *) die "no uv build for ${1}: install uv yourself, see https://docs.astral.sh/uv/" ;;
    esac
}

fetch() {
    if command -v curl >/dev/null 2>&1; then
        curl -fsSL -o "${2}" "${1}"
    elif command -v wget >/dev/null 2>&1; then
        wget -q -O "${2}" "${1}"
    else
        die "needs curl or wget to fetch uv"
    fi
}

sha256_of() {
    if command -v sha256sum >/dev/null 2>&1; then
        sha256sum "${1}" | cut -d ' ' -f 1
    else
        shasum -a 256 "${1}" | cut -d ' ' -f 1
    fi
}

# Put the pinned uv in the bin dir uv's own installer uses, or stop on a hash mismatch.
install_uv() {
    local bin="${1}" target want
    target="$(uv_target)"
    want="$(uv_sha256 "${target}")"
    TMP_DIR="$(mktemp -d)"
    fetch "https://github.com/astral-sh/uv/releases/download/${UV_VERSION}/uv-${target}.tar.gz" "${TMP_DIR}/uv.tar.gz"
    [[ "$(sha256_of "${TMP_DIR}/uv.tar.gz")" == "${want}" ]] ||
        die "uv ${UV_VERSION} for ${target} failed its SHA256 check"
    tar -xzf "${TMP_DIR}/uv.tar.gz" -C "${TMP_DIR}"
    mkdir -p "${bin}"
    cp "${TMP_DIR}/uv-${target}/uv" "${TMP_DIR}/uv-${target}/uvx" "${bin}/"
}

main() {
    local os here bin merrow
    os="$(uname -s)"
    here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
    [[ "${os}" == "Linux" || "${os}" == "Darwin" ]] ||
        die "Linux and macOS only. Windows is best effort: see the README."
    [[ -f "${here}/.python-version" ]] || die "run this from a merrow checkout"
    trap cleanup EXIT
    if ! command -v uv >/dev/null 2>&1; then
        bin="${XDG_BIN_HOME:-${HOME}/.local/bin}"
        [[ -x "${bin}/uv" ]] || install_uv "${bin}"
        export PATH="${bin}:${PATH}"
    fi
    uv tool install --force --python "$(cat "${here}/.python-version")" "${here}[all]"
    merrow="$(uv tool dir --bin)/merrow"
    if [[ "${os}" == "Linux" ]] && command -v apt-get >/dev/null 2>&1; then
        # Playwright's bundled Node needs libatomic before it can install anything.
        if ! dpkg -s libatomic1 >/dev/null 2>&1; then
            sudo apt-get update && sudo apt-get install -y libatomic1
        fi
        "${merrow}" tools ensure --install-deps
    else
        "${merrow}" tools ensure
    fi
    command -v merrow >/dev/null 2>&1 || uv tool update-shell
}

if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    main "$@"
fi
