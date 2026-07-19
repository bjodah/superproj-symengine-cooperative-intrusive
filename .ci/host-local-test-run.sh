#!/bin/bash
set -euxo pipefail


main() {
    SCRIPT_PATH="$(realpath ${BASH_SOURCE[0]})"
    REPO_ROOT="$(dirname $SCRIPT_PATH)/.."
    if [[ ! -z $(git -C "$REPO_ROOT" status -s) ]]; then
        >&2 echo "WARNING: uncommitted changes in repo, make sure that you commit any changes you want to test."
    fi

    IMAGE=$(grep '\- &ci_image' $REPO_ROOT/.woodpecker.yaml | cut -d"'" -f2)

    declare -a args_podman_run=()
    args_podman_run+=(-e LITGEN_ROOT=$(awk -F 'LITGEN_ROOT:[[:space:]]*' '/LITGEN_ROOT:/ {print $2}' $REPO_ROOT/.woodpecker.yaml))

    if [[ -e $HOME/.ccache ]]; then
        args_podman_run+=("-v" "$HOME/.ccache:/root/.ccache")
    fi

    args_podman_run+=("-i")
    if [[ -t 1 ]]; then  # Only allocate a pseudo-TTY (-t) when actually attached to one.
        args_podman_run+=("-t")
    fi

    # CI_PODMAN_NETWORK=none runs the suite with no network access at all --
    # the CI lanes are meant to work offline (everything from PyPI/apt is baked
    # into the image by .ci/env/Containerfile; see AGENTS.md), and this is how
    # that property is verified.
    if [[ -n ${CI_PODMAN_NETWORK:-} ]]; then
        args_podman_run+=("--network=$SXX_PODMAN_NETWORK")
    fi

    podman run \
           --rm \
           --privileged \
           --cap-add=SYS_PTRACE \
           --device /dev/fuse \
           --cap-add SYS_ADMIN \
           --cap-add=SYS_PTRACE \
           --security-opt seccomp=unconfined `# needed for address sanitizer` \
           "${args_podman_run[@]}" \
           -v "$REPO_ROOT:$REPO_ROOT" \
           -w "$REPO_ROOT" \
           $IMAGE \
           bash -lc "env IN_CONTAINER=1 ${SCRIPT_PATH}"
}
inner_main() {
    export COMPILER_LAUNCHER=ccache
    export CI=1
    .ci/run-ci-steps.sh
}
{
    if [[ "${IN_CONTAINER:-0}" == 1 ]]; then
        inner_main "$@"
        exit $?
    else
        main "$@"
        exit $?
    fi
}
