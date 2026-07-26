#!/bin/sh
set -eu

usage() {
  printf 'usage: %s {--all REVISION|--range BASE HEAD}\n' "$0" >&2
  exit 2
}

case ${1:-} in
  --all)
    [ "$#" -eq 2 ] || usage
    revision=$2
    if ! git rev-parse --verify "$revision^{commit}" >/dev/null 2>&1; then
      printf 'invalid commit revision: %s\n' "$revision" >&2
      exit 2
    fi
    revision_spec=$revision
    ;;
  --range)
    [ "$#" -eq 3 ] || usage
    base=$2
    head=$3
    for revision in "$base" "$head"; do
      if ! git rev-parse --verify "$revision^{commit}" >/dev/null 2>&1; then
        printf 'invalid commit revision: %s\n' "$revision" >&2
        exit 2
      fi
    done
    revision_spec=$base..$head
    ;;
  *)
    usage
    ;;
esac

commits=$(git rev-list "$revision_spec")
[ -n "$commits" ] || {
  printf 'DCO range contains no commits\n' >&2
  exit 1
}
failed=0
parsed_trailers_file=$(
  mktemp "${TMPDIR:-/tmp}/engrammesh-dco-trailers.XXXXXX"
)
trap 'rm -f "$parsed_trailers_file"' EXIT HUP INT TERM

for commit in $commits; do
  git show -s --format=%B "$commit" |
    git interpret-trailers --parse >"$parsed_trailers_file"

  signed_off_count=0
  invalid_signed_off=0
  while IFS= read -r parsed_trailer || [ -n "$parsed_trailer" ]; do
    case $parsed_trailer in
      'Signed-off-by: '*)
        signed_off_count=$((signed_off_count + 1))
        signed_off=${parsed_trailer#Signed-off-by:}
        signed_off=$(
          printf '%s\n' "$signed_off" |
            sed 's/^[[:space:]]*//; s/[[:space:]]*$//'
        )
        if ! printf '%s\n' "$signed_off" |
          LC_ALL=C grep -Eq \
            '^[^[:space:]<>][^<>]*[[:space:]]+<[^[:space:]<>@]+@[^[:space:]<>@]+>$'; then
          invalid_signed_off=1
        fi
        ;;
    esac
  done <"$parsed_trailers_file"

  if [ "$signed_off_count" -eq 0 ]; then
    subject=$(
      git show -s --format=%s "$commit" |
        LC_ALL=C tr -d '\000-\011\013-\037\177'
    )
    printf '%s (%s): missing Signed-off-by trailer\n' \
      "$commit" "$subject" >&2
    failed=1
    continue
  fi

  if [ "$invalid_signed_off" -ne 0 ]; then
    subject=$(
      git show -s --format=%s "$commit" |
        LC_ALL=C tr -d '\000-\011\013-\037\177'
    )
    printf '%s (%s): invalid Signed-off-by trailer\n' \
      "$commit" "$subject" >&2
    failed=1
  fi
done

exit "$failed"
