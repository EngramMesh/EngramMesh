#!/bin/sh
set -eu

usage() {
  printf 'usage: %s --revision REV --lychee /absolute/path/to/lychee\n' "$0" >&2
  exit 2
}

[ "$#" -eq 4 ] || usage
[ "$1" = "--revision" ] || usage
revision=$2
[ "$3" = "--lychee" ] || usage
lychee=$4

case $lychee in
  /*)
    ;;
  *)
    printf 'Lychee path must be absolute\n' >&2
    exit 1
    ;;
esac
[ -x "$lychee" ] || {
  printf 'Lychee path is not executable: %s\n' "$lychee" >&2
  exit 1
}

if ! commit_oid=$(git rev-parse --verify "$revision^{commit}" 2>/dev/null); then
  printf 'invalid commit revision: %s\n' "$revision" >&2
  exit 1
fi

symlink_entry=$(
  git ls-tree -r "$commit_oid" |
    sed -n '/^120000 / {
      p
      q
    }'
)
if [ -n "$symlink_entry" ]; then
  symlink_path=$(printf '%s\n' "$symlink_entry" | cut -f2-)
  printf 'tracked symbolic link is not allowed: %s\n' "$symlink_path" >&2
  exit 1
fi

repository_root=$(
  repository_path=$(git rev-parse --show-toplevel)
  CDPATH='' cd -- "$repository_path" && pwd -P
)
snapshot=$(mktemp -d "${TMPDIR:-/tmp}/engrammesh-links.XXXXXX")
link_dump=$snapshot.links
trap 'chmod -R u+w "$snapshot" 2>/dev/null || true; rm -rf "$snapshot"; rm -f "$link_dump"' EXIT HUP INT TERM
snapshot=$(CDPATH='' cd -- "$snapshot" && pwd -P)
case $snapshot in
  "$repository_root"/*)
    printf 'snapshot directory must be outside the repository\n' >&2
    exit 1
    ;;
esac

git archive "$commit_oid" | tar -x -C "$snapshot"

if ! find "$snapshot" -type f -name '*.md' -print | grep -q .; then
  printf 'no tracked Markdown files in revision: %s\n' "$revision" >&2
  exit 1
fi

(
  cd "$snapshot"
  "$lychee" \
    --offline \
    --no-progress \
    --include-fragments=none \
    --root-dir "$snapshot" \
    --dump \
    './**/*.md'
) >"$link_dump"

ruby - "$snapshot" "$link_dump" <<'RUBY'
require "pathname"
require "uri"

snapshot = Pathname.new(ARGV.fetch(0).b).cleanpath.to_s.b

File.foreach(ARGV.fetch(1), chomp: true) do |link|
  next unless link.start_with?("file:")

  begin
    uri = URI.parse(link)
  rescue URI::InvalidURIError
    abort "invalid file URL in Markdown: #{link}"
  end

  local_authority =
    (uri.host.nil? || uri.host.empty?) &&
    uri.userinfo.nil? &&
    uri.port.nil?
  unless uri.scheme == "file" && local_authority
    abort "file URL authority is not allowed: #{link}"
  end

  decoded_path = URI::DEFAULT_PARSER.unescape(uri.path)
  if decoded_path.include?("\0")
    abort "file URL contains a NUL byte: #{link}"
  end
  unless decoded_path.valid_encoding?
    abort "file URL path is not valid UTF-8: #{link}"
  end
  unless decoded_path.start_with?("/")
    abort "file URL path is not absolute: #{link}"
  end

  target = Pathname.new(decoded_path.b).cleanpath.to_s.b
  next if target == snapshot || target.start_with?(snapshot + "/".b)

  abort "link target escapes snapshot: #{link}"
end
RUBY

(
  cd "$snapshot"
  "$lychee" \
    --offline \
    --no-progress \
    --include-fragments=none \
    --root-dir "$snapshot" \
    './**/*.md'
)
