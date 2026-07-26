#!/bin/sh
set -eu

script_dir=$(CDPATH='' cd -- "$(dirname -- "$0")" && pwd -P)
repository_root=$(CDPATH='' cd -- "$script_dir/.." && pwd -P)
tmp_dir=$(mktemp -d "${TMPDIR:-/tmp}/engrammesh-policy.XXXXXX")
case $tmp_dir in
  "$repository_root"/*)
    printf 'fixture directory must be outside the repository\n' >&2
    exit 1
    ;;
esac
trap 'chmod -R u+w "$tmp_dir" 2>/dev/null || true; rm -rf "$tmp_dir"' EXIT HUP INT TERM

export GIT_CONFIG_NOSYSTEM=1
export GIT_CONFIG_GLOBAL="$tmp_dir/empty-gitconfig"
mkdir -p "$tmp_dir/empty-template"
: >"$GIT_CONFIG_GLOBAL"

fail() {
  printf 'policy fixture failed: %s\n' "$1" >&2
  exit 1
}

capture_failure() {
  output_file=$1
  shift
  if "$@" >"$output_file" 2>&1; then
    return 1
  fi
}

assert_resolution() {
  installer=$1
  tool=$2
  operating_system=$3
  architecture=$4
  expected_url=$5
  expected_digest=$6

  if ! actual_resolution=$(
    "$installer" resolve "$tool" "$operating_system" "$architecture"
  ); then
    fail "resolver rejected approved $tool $operating_system $architecture platform"
  fi
  expected_resolution=$(printf '%s\n%s' "$expected_url" "$expected_digest")
  [ "$actual_resolution" = "$expected_resolution" ] ||
    fail "resolver returned unapproved $tool $operating_system $architecture release"
}

test_tools() {
  installer=$script_dir/install-policy-tools.sh
  checksum_fixture=$tmp_dir/checksum-fixture
  printf 'EngramMesh policy tool fixture\n' >"$checksum_fixture"
  expected_checksum=861119db05543c0c2aa8534a90d07c14761b6e2c22a1840d95fadf448bcd06af

  "$installer" verify-sha256 "$checksum_fixture" "$expected_checksum"

  invalid_digest_output=$tmp_dir/invalid-digest.out
  capture_failure "$invalid_digest_output" \
    "$installer" verify-sha256 "$checksum_fixture" not-a-sha256 ||
    fail 'verify-sha256 accepted a malformed digest'
  rg -q 'invalid SHA-256 digest' "$invalid_digest_output" ||
    fail 'malformed digest did not report invalid SHA-256 digest'

  mismatch_output=$tmp_dir/checksum-mismatch.out
  capture_failure "$mismatch_output" \
    "$installer" verify-sha256 "$checksum_fixture" \
    0000000000000000000000000000000000000000000000000000000000000000 ||
    fail 'verify-sha256 accepted an incorrect digest'
  rg -q 'SHA-256 mismatch' "$mismatch_output" ||
    fail 'digest mismatch did not report SHA-256 mismatch'

  assert_resolution "$installer" lychee Darwin arm64 \
    'https://github.com/lycheeverse/lychee/releases/download/lychee-v0.24.2/lychee-aarch64-apple-darwin.tar.gz' \
    'c9d3740ea2d891854d37116c9fba840f37b6e7c89d330e7db84ac333631c4977'
  assert_resolution "$installer" lychee Darwin aarch64 \
    'https://github.com/lycheeverse/lychee/releases/download/lychee-v0.24.2/lychee-aarch64-apple-darwin.tar.gz' \
    'c9d3740ea2d891854d37116c9fba840f37b6e7c89d330e7db84ac333631c4977'
  assert_resolution "$installer" lychee Darwin x86_64 \
    'https://github.com/lycheeverse/lychee/releases/download/lychee-v0.24.2/lychee-x86_64-apple-darwin.tar.gz' \
    '887503a9cff667d322b8d0892b40bf49976eb9507af8483220a3706cdad55978'
  assert_resolution "$installer" lychee Darwin amd64 \
    'https://github.com/lycheeverse/lychee/releases/download/lychee-v0.24.2/lychee-x86_64-apple-darwin.tar.gz' \
    '887503a9cff667d322b8d0892b40bf49976eb9507af8483220a3706cdad55978'
  assert_resolution "$installer" lychee Linux arm64 \
    'https://github.com/lycheeverse/lychee/releases/download/lychee-v0.24.2/lychee-aarch64-unknown-linux-gnu.tar.gz' \
    '91a7bd65685da41b90ccb9bc867a3d649a7818042dae04ff405e55a25bddee4c'
  assert_resolution "$installer" lychee Linux aarch64 \
    'https://github.com/lycheeverse/lychee/releases/download/lychee-v0.24.2/lychee-aarch64-unknown-linux-gnu.tar.gz' \
    '91a7bd65685da41b90ccb9bc867a3d649a7818042dae04ff405e55a25bddee4c'
  assert_resolution "$installer" lychee Linux x86_64 \
    'https://github.com/lycheeverse/lychee/releases/download/lychee-v0.24.2/lychee-x86_64-unknown-linux-gnu.tar.gz' \
    '1f4e0ef7f6554a6ed33dd7ac144fb2e1bbed98598e7af973042fc5cd43951c9a'
  assert_resolution "$installer" lychee Linux amd64 \
    'https://github.com/lycheeverse/lychee/releases/download/lychee-v0.24.2/lychee-x86_64-unknown-linux-gnu.tar.gz' \
    '1f4e0ef7f6554a6ed33dd7ac144fb2e1bbed98598e7af973042fc5cd43951c9a'
  assert_resolution "$installer" actionlint Darwin arm64 \
    'https://github.com/rhysd/actionlint/releases/download/v1.7.12/actionlint_1.7.12_darwin_arm64.tar.gz' \
    'aba9ced2dee8d27fecca3dc7feb1a7f9a52caefa1eb46f3271ea66b6e0e6953f'
  assert_resolution "$installer" actionlint Darwin aarch64 \
    'https://github.com/rhysd/actionlint/releases/download/v1.7.12/actionlint_1.7.12_darwin_arm64.tar.gz' \
    'aba9ced2dee8d27fecca3dc7feb1a7f9a52caefa1eb46f3271ea66b6e0e6953f'
  assert_resolution "$installer" actionlint Darwin x86_64 \
    'https://github.com/rhysd/actionlint/releases/download/v1.7.12/actionlint_1.7.12_darwin_amd64.tar.gz' \
    '5b44c3bc2255115c9b69e30efc0fecdf498fdb63c5d58e17084fd5f16324c644'
  assert_resolution "$installer" actionlint Darwin amd64 \
    'https://github.com/rhysd/actionlint/releases/download/v1.7.12/actionlint_1.7.12_darwin_amd64.tar.gz' \
    '5b44c3bc2255115c9b69e30efc0fecdf498fdb63c5d58e17084fd5f16324c644'
  assert_resolution "$installer" actionlint Linux arm64 \
    'https://github.com/rhysd/actionlint/releases/download/v1.7.12/actionlint_1.7.12_linux_arm64.tar.gz' \
    '325e971b6ba9bfa504672e29be93c24981eeb1c07576d730e9f7c8805afff0c6'
  assert_resolution "$installer" actionlint Linux aarch64 \
    'https://github.com/rhysd/actionlint/releases/download/v1.7.12/actionlint_1.7.12_linux_arm64.tar.gz' \
    '325e971b6ba9bfa504672e29be93c24981eeb1c07576d730e9f7c8805afff0c6'
  assert_resolution "$installer" actionlint Linux x86_64 \
    'https://github.com/rhysd/actionlint/releases/download/v1.7.12/actionlint_1.7.12_linux_amd64.tar.gz' \
    '8aca8db96f1b94770f1b0d72b6dddcb1ebb8123cb3712530b08cc387b349a3d8'
  assert_resolution "$installer" actionlint Linux amd64 \
    'https://github.com/rhysd/actionlint/releases/download/v1.7.12/actionlint_1.7.12_linux_amd64.tar.gz' \
    '8aca8db96f1b94770f1b0d72b6dddcb1ebb8123cb3712530b08cc387b349a3d8'

  unsupported_output=$tmp_dir/unsupported-platform.out
  capture_failure "$unsupported_output" \
    "$installer" resolve lychee Plan9 x86_64 ||
    fail 'resolver accepted an unsupported platform'
  rg -q 'unsupported policy-tool platform' "$unsupported_output" ||
    fail 'unsupported platform did not report unsupported policy-tool platform'

  install_dir=$tmp_dir/installed-policy-tools
  install_output=$tmp_dir/install.out
  install_error=$tmp_dir/install.err
  repository_paths_before=$tmp_dir/repository-paths-before
  repository_paths_after=$tmp_dir/repository-paths-after
  git_status_before=$tmp_dir/git-status-before
  git_status_after=$tmp_dir/git-status-after
  git_config_before=$tmp_dir/git-config-before
  git_config_after=$tmp_dir/git-config-after
  path_before=$PATH

  find "$repository_root" -mindepth 1 -print | LC_ALL=C sort \
    >"$repository_paths_before"
  git -C "$repository_root" status --porcelain=v1 --untracked-files=all \
    >"$git_status_before"
  git -C "$repository_root" config --list --show-origin >"$git_config_before"

  if ! "$installer" install "$install_dir" all \
    >"$install_output" 2>"$install_error"; then
    fail 'install command did not download and install the approved tools'
  fi

  [ "$PATH" = "$path_before" ] || fail 'install command modified PATH'
  find "$repository_root" -mindepth 1 -print | LC_ALL=C sort \
    >"$repository_paths_after"
  cmp -s "$repository_paths_before" "$repository_paths_after" ||
    fail 'install command created a path under the repository'
  git -C "$repository_root" status --porcelain=v1 --untracked-files=all \
    >"$git_status_after"
  cmp -s "$git_status_before" "$git_status_after" ||
    fail 'install command modified the working tree'
  git -C "$repository_root" config --list --show-origin >"$git_config_after"
  cmp -s "$git_config_before" "$git_config_after" ||
    fail 'install command modified Git configuration'

  expected_install_output=$(printf '%s\n%s' \
    "$install_dir/bin/lychee" "$install_dir/bin/actionlint")
  actual_install_output=$(cat "$install_output")
  [ "$actual_install_output" = "$expected_install_output" ] ||
    fail 'install command did not print the installed binary paths'
  [ -x "$install_dir/bin/lychee" ] ||
    fail 'install command did not create an executable lychee'
  [ -x "$install_dir/bin/actionlint" ] ||
    fail 'install command did not create an executable actionlint'
  "$install_dir/bin/lychee" --version | rg -q '0[.]24[.]2' ||
    fail 'installed lychee did not report version 0.24.2'
  "$install_dir/bin/actionlint" --version | rg -q '1[.]7[.]12' ||
    fail 'installed actionlint did not report version 1.7.12'
  if find "$install_dir/download" -type f -print | rg -q .; then
    fail 'install command retained a downloaded archive'
  fi

  printf 'policy fixtures (tools): ok\n'
}

case ${1:-} in
  tools)
    test_tools
    ;;
  *)
    printf 'usage: %s tools\n' "$0" >&2
    exit 2
    ;;
esac
