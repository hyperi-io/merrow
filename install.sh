#!/usr/bin/env bash
# Install merrow from this checkout on Linux or macOS: uv if missing, the
# merrow CLI, the pinned Mermaid bundle and the browser it renders in.
set -euo pipefail

die() {
    echo "merrow install: ${1}" >&2
    exit 1
}

main() {
    local os here
    os="$(uname -s)"
    here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
    [[ "${os}" == "Linux" || "${os}" == "Darwin" ]] ||
        die "Linux and macOS only. Windows is best effort: see the README."
    [[ -f "${here}/.python-version" ]] || die "run this from a merrow checkout"
    if ! command -v uv >/dev/null 2>&1; then
        curl -LsSf https://astral.sh/uv/install.sh | sh
        export PATH="${XDG_BIN_HOME:-${HOME}/.local/bin}:${PATH}"
    fi
    uv tool install --force --python "$(cat "${here}/.python-version")" "${here}"
    local merrow
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

main "$@"
