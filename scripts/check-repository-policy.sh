#!/bin/sh
set -eu

script_dir=$(CDPATH='' cd -- "$(dirname -- "$0")" && pwd -P)
repository_root=$(CDPATH='' cd -- "$script_dir/.." && pwd -P)
temporary_tool_dir=

usage() {
  printf 'usage: %s {--all REVISION|--range BASE HEAD} --tree TREE\n' "$0" >&2
  exit 2
}

cleanup() {
  if [ -n "$temporary_tool_dir" ]; then
    chmod -R u+w "$temporary_tool_dir" 2>/dev/null || true
    rm -rf "$temporary_tool_dir"
  fi
}

require_absolute_executable() {
  tool_name=$1
  executable=$2
  case $executable in
    /*)
      ;;
    *)
      printf '%s path must be absolute\n' "$tool_name" >&2
      exit 1
      ;;
  esac
  if [ ! -x "$executable" ]; then
    printf '%s path is not executable: %s\n' "$tool_name" "$executable" >&2
    exit 1
  fi
}

case ${1:-} in
  --all)
    [ "$#" -eq 4 ] || usage
    dco_mode=--all
    dco_revision=$2
    [ "$3" = "--tree" ] || usage
    tree_revision=$4
    ;;
  --range)
    [ "$#" -eq 5 ] || usage
    dco_mode=--range
    dco_base=$2
    dco_head=$3
    [ "$4" = "--tree" ] || usage
    tree_revision=$5
    ;;
  *)
    usage
    ;;
esac

for suite in tools dco history links workflow external baseline orchestration yaml; do
  "$script_dir/test-repository-policy.sh" "$suite"
done

(
  cd "$repository_root"
  "$script_dir/check-repository-baseline.sh"
)

if [ "${LYCHEE_BIN+x}" = x ]; then
  lychee_bin=$LYCHEE_BIN
  require_absolute_executable Lychee "$lychee_bin"
fi
if [ "${ACTIONLINT_BIN+x}" = x ]; then
  actionlint_bin=$ACTIONLINT_BIN
  require_absolute_executable actionlint "$actionlint_bin"
fi

if [ "${LYCHEE_BIN+x}" != x ] || [ "${ACTIONLINT_BIN+x}" != x ]; then
  if [ "${GITHUB_ACTIONS:-}" = true ]; then
    case ${RUNNER_TEMP:-} in
      /*)
        tool_dir=$RUNNER_TEMP/policy-tools
        ;;
      *)
        printf 'RUNNER_TEMP must be absolute in GitHub Actions\n' >&2
        exit 1
        ;;
    esac
    if [ -e "$tool_dir" ]; then
      printf 'policy tool directory already exists: %s\n' "$tool_dir" >&2
      exit 1
    fi
  else
    tool_dir=$(mktemp -d "${TMPDIR:-/tmp}/engrammesh-policy-tools.XXXXXX")
    temporary_tool_dir=$tool_dir
    trap cleanup EXIT HUP INT TERM
  fi

  if [ "${LYCHEE_BIN+x}" != x ]; then
    "$script_dir/install-policy-tools.sh" \
      install "$tool_dir" lychee >/dev/null
    lychee_bin=$tool_dir/bin/lychee
  fi
  if [ "${ACTIONLINT_BIN+x}" != x ]; then
    "$script_dir/install-policy-tools.sh" \
      install "$tool_dir" actionlint >/dev/null
    actionlint_bin=$tool_dir/bin/actionlint
  fi
fi

require_absolute_executable Lychee "$lychee_bin"
require_absolute_executable actionlint "$actionlint_bin"

(
  cd "$repository_root"
  case $dco_mode in
    --all)
      "$script_dir/check-dco.sh" --all "$dco_revision"
      ;;
    --range)
      "$script_dir/check-dco.sh" \
        --range "$dco_base" "$dco_head"
      ;;
  esac
  "$script_dir/check-markdown-links.sh" \
    --revision "$tree_revision" --lychee "$lychee_bin"
  "$script_dir/check-community-yaml.rb" "$repository_root"
  ruby "$script_dir/check-workflow-policy.rb" \
    --root "$repository_root" \
    --actionlint "$actionlint_bin"
  "$script_dir/check-private-history.sh" "$tree_revision"
)

printf 'repository policy: ok\n'
