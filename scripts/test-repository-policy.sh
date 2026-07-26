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

test_dco() {
  validator=$script_dir/check-dco.sh
  fixture_repo=

  fixture_git() {
    git -C "$fixture_repo" \
      -c core.hooksPath=/dev/null \
      -c commit.gpgsign=false \
      -c core.autocrlf=false \
      -c core.eol=lf \
      "$@"
  }

  new_fixture() {
    fixture_repo=$tmp_dir/$1
    mkdir -p "$fixture_repo"
    fixture_git init --quiet --template="$tmp_dir/empty-template"
    fixture_git config user.name 'Fixture User'
    fixture_git config user.email 'fixture@example.com'
  }

  commit_fixture() {
    message_file=$1
    content=$2
    printf '%s\n' "$content" >"$fixture_repo/tracked.txt"
    fixture_git add tracked.txt
    fixture_git commit --quiet --cleanup=verbatim -F "$message_file"
  }

  run_validator() {
    (
      cd "$fixture_repo"
      "$validator" "$@"
    )
  }

  new_fixture signed-root
  signed_message=$tmp_dir/signed-root-message
  printf '%s\n\n%s\n' \
    'Signed root commit' \
    'Signed-off-by: Fixture User <fixture@example.com>' \
    >"$signed_message"
  commit_fixture "$signed_message" signed-root
  fixture_git rev-parse --verify 'HEAD^{commit}' >/dev/null
  run_validator --all HEAD ||
    fail 'signed root commit with final trailer was rejected'

  new_fixture unsigned-commit
  unsigned_message=$tmp_dir/unsigned-commit-message
  printf '%s\n' 'Unsigned commit' >"$unsigned_message"
  commit_fixture "$unsigned_message" unsigned
  unsigned_sha=$(fixture_git log -1 --format=%H)
  unsigned_output=$tmp_dir/unsigned-commit.out
  capture_failure "$unsigned_output" run_validator --all HEAD ||
    fail 'unsigned commit was accepted'
  rg -q "$unsigned_sha" "$unsigned_output" ||
    fail 'unsigned commit diagnostic omitted the commit SHA'
  rg -q 'missing Signed-off-by trailer' "$unsigned_output" ||
    fail 'unsigned commit did not report missing Signed-off-by trailer'

  new_fixture signed-range
  range_message=$tmp_dir/signed-range-message
  printf '%s\n\n%s\n' \
    'Signed range commit' \
    'Signed-off-by: Fixture User <fixture@example.com>' \
    >"$range_message"
  commit_fixture "$range_message" range-base
  range_base=$(fixture_git rev-parse HEAD)
  commit_fixture "$range_message" range-first
  commit_fixture "$range_message" range-second
  range_head=$(fixture_git rev-parse HEAD)
  run_validator --range "$range_base" "$range_head" ||
    fail 'two signed commits in BASE..HEAD were rejected'

  invalid_base_output=$tmp_dir/invalid-base.out
  capture_failure "$invalid_base_output" \
    run_validator --range not-a-commit "$range_head" ||
    fail 'invalid base revision was accepted'
  rg -q 'invalid commit revision' "$invalid_base_output" ||
    fail 'invalid base revision did not report invalid commit revision'

  invalid_head_output=$tmp_dir/invalid-head.out
  capture_failure "$invalid_head_output" \
    run_validator --range "$range_base" not-a-commit ||
    fail 'invalid head revision was accepted'
  rg -q 'invalid commit revision' "$invalid_head_output" ||
    fail 'invalid head revision did not report invalid commit revision'

  empty_range_output=$tmp_dir/empty-range.out
  capture_failure "$empty_range_output" \
    run_validator --range "$range_head" "$range_head" ||
    fail 'BASE == HEAD did not report DCO range contains no commits'
  rg -q 'DCO range contains no commits' "$empty_range_output" ||
    fail 'BASE == HEAD did not report DCO range contains no commits'

  new_fixture signoff-in-subject
  subject_signoff_message=$tmp_dir/subject-signoff-message
  printf '%s\n' \
    'Signed-off-by: Fixture User <fixture@example.com>' \
    >"$subject_signoff_message"
  commit_fixture "$subject_signoff_message" subject-signoff
  subject_signoff_sha=$(fixture_git rev-parse HEAD)
  subject_signoff_output=$tmp_dir/subject-signoff.out
  capture_failure "$subject_signoff_output" run_validator --all HEAD ||
    fail 'Signed-off-by in subject did not report missing Signed-off-by trailer'
  rg -q "$subject_signoff_sha" "$subject_signoff_output" ||
    fail 'Signed-off-by in subject diagnostic omitted the commit SHA'
  rg -q 'missing Signed-off-by trailer' "$subject_signoff_output" ||
    fail 'Signed-off-by in subject did not report missing Signed-off-by trailer'

  new_fixture lowercase-signoff-key
  lowercase_signoff_message=$tmp_dir/lowercase-signoff-message
  printf '%s\n\n%s\n' \
    'Lowercase sign-off key' \
    'signed-off-by: Fixture User <fixture@example.com>' \
    >"$lowercase_signoff_message"
  commit_fixture "$lowercase_signoff_message" lowercase-signoff
  lowercase_signoff_sha=$(fixture_git rev-parse HEAD)
  lowercase_signoff_output=$tmp_dir/lowercase-signoff.out
  capture_failure "$lowercase_signoff_output" run_validator --all HEAD ||
    fail 'lowercase sign-off key did not report missing Signed-off-by trailer'
  rg -q "$lowercase_signoff_sha" "$lowercase_signoff_output" ||
    fail 'lowercase sign-off key diagnostic omitted the commit SHA'
  rg -q 'missing Signed-off-by trailer' "$lowercase_signoff_output" ||
    fail 'lowercase sign-off key did not report missing Signed-off-by trailer'

  new_fixture miscased-signoff-key
  miscased_signoff_message=$tmp_dir/miscased-signoff-message
  printf '%s\n\n%s\n' \
    'Miscased sign-off key' \
    'Signed-Off-By: Fixture User <fixture@example.com>' \
    >"$miscased_signoff_message"
  commit_fixture "$miscased_signoff_message" miscased-signoff
  miscased_signoff_sha=$(fixture_git log -1 --format=%H)
  miscased_signoff_output=$tmp_dir/miscased-signoff.out
  capture_failure "$miscased_signoff_output" run_validator --all HEAD ||
    fail 'miscased sign-off key did not report missing Signed-off-by trailer'
  rg -q "$miscased_signoff_sha" "$miscased_signoff_output" ||
    fail 'miscased sign-off key diagnostic omitted the commit SHA'
  rg -q 'missing Signed-off-by trailer' "$miscased_signoff_output" ||
    fail 'miscased sign-off key did not report missing Signed-off-by trailer'

  new_fixture exact-and-nonexact-signoff-keys
  exact_and_nonexact_message=$tmp_dir/exact-and-nonexact-message
  printf '%s\n\n%s\n%s\n%s\n' \
    'Exact and nonexact sign-off keys' \
    'Signed-off-by: Fixture User <fixture@example.com>' \
    'signed-off-by:' \
    'Signed-Off-By: <malformed@example.com>' \
    >"$exact_and_nonexact_message"
  commit_fixture "$exact_and_nonexact_message" exact-and-nonexact
  run_validator --all HEAD ||
    fail 'nonexact sign-off keys affected a valid exact Signed-off-by trailer'

  new_fixture signoff-before-body
  signoff_before_body_message=$tmp_dir/signoff-before-body-message
  printf '%s\n\n%s\n\n%s\n\n%s\n' \
    'Sign-off before a later paragraph' \
    'Initial body paragraph.' \
    'Signed-off-by: Fixture User <fixture@example.com>' \
    'Later body paragraph.' \
    >"$signoff_before_body_message"
  commit_fixture "$signoff_before_body_message" signoff-before-body
  signoff_before_body_sha=$(fixture_git log -1 --format=%H)
  signoff_before_body_output=$tmp_dir/signoff-before-body.out
  capture_failure "$signoff_before_body_output" run_validator --all HEAD ||
    fail 'sign-off followed by body did not report missing Signed-off-by trailer'
  rg -q "$signoff_before_body_sha" "$signoff_before_body_output" ||
    fail 'sign-off followed by body diagnostic omitted the commit SHA'
  rg -q 'missing Signed-off-by trailer' "$signoff_before_body_output" ||
    fail 'sign-off followed by body did not report missing Signed-off-by trailer'

  new_fixture malformed-signoff
  malformed_signoff_message=$tmp_dir/malformed-signoff-message
  printf '%s\n\n%s\n' \
    'Malformed sign-off' \
    'Signed-off-by:   <a@b.example>' \
    >"$malformed_signoff_message"
  commit_fixture "$malformed_signoff_message" malformed-signoff
  malformed_signoff_sha=$(fixture_git rev-parse HEAD)
  malformed_signoff_output=$tmp_dir/malformed-signoff.out
  capture_failure "$malformed_signoff_output" run_validator --all HEAD ||
    fail 'empty-name sign-off did not report invalid Signed-off-by trailer'
  rg -q "$malformed_signoff_sha" "$malformed_signoff_output" ||
    fail 'empty-name sign-off diagnostic omitted the commit SHA'
  rg -q 'invalid Signed-off-by trailer' "$malformed_signoff_output" ||
    fail 'empty-name sign-off did not report invalid Signed-off-by trailer'

  new_fixture empty-signoff
  empty_signoff_message=$tmp_dir/empty-signoff-message
  printf '%s\n\n%s\n' \
    'Empty exact sign-off' \
    'Signed-off-by:' \
    >"$empty_signoff_message"
  commit_fixture "$empty_signoff_message" empty-signoff
  empty_signoff_sha=$(fixture_git rev-parse HEAD)
  empty_signoff_output=$tmp_dir/empty-signoff.out
  capture_failure "$empty_signoff_output" run_validator --all HEAD ||
    fail 'empty exact sign-off was accepted'
  rg -q "$empty_signoff_sha" "$empty_signoff_output" ||
    fail 'empty exact sign-off diagnostic omitted the commit SHA'
  rg -q 'invalid Signed-off-by trailer' "$empty_signoff_output" ||
    fail 'empty exact sign-off did not report invalid Signed-off-by trailer'

  new_fixture signoff-without-at
  no_at_message=$tmp_dir/no-at-signoff-message
  printf '%s\n\n%s\n' \
    'Sign-off address without at sign' \
    'Signed-off-by: Fixture User <fixture.example.com>' \
    >"$no_at_message"
  commit_fixture "$no_at_message" no-at-signoff
  no_at_sha=$(fixture_git log -1 --format=%H)
  no_at_output=$tmp_dir/no-at-signoff.out
  capture_failure "$no_at_output" run_validator --all HEAD ||
    fail 'address without @ did not report invalid Signed-off-by trailer'
  rg -q "$no_at_sha" "$no_at_output" ||
    fail 'address without @ diagnostic omitted the commit SHA'
  rg -q 'invalid Signed-off-by trailer' "$no_at_output" ||
    fail 'address without @ did not report invalid Signed-off-by trailer'

  new_fixture crlf-signoff
  crlf_message=$tmp_dir/crlf-signoff-message
  printf '%s\r\n\r\n%s\r\n' \
    'CRLF final trailer' \
    'Signed-off-by: Fixture User <fixture@example.com>' \
    >"$crlf_message"
  commit_fixture "$crlf_message" crlf-signoff
  stored_crlf_message=$tmp_dir/stored-crlf-message
  fixture_git show -s --format=%B HEAD >"$stored_crlf_message"
  cr_count=$(
    LC_ALL=C tr -cd '\015' <"$stored_crlf_message" |
      wc -c |
      tr -d '[:space:]'
  )
  [ "$cr_count" -gt 0 ] ||
    fail 'CRLF fixture commit message did not retain CR bytes'
  run_validator --all HEAD ||
    fail 'CRLF final Signed-off-by trailer was rejected'

  new_fixture two-valid-signoffs
  two_valid_message=$tmp_dir/two-valid-signoffs-message
  printf '%s\n\n%s\n%s\n' \
    'Two valid sign-offs' \
    'Signed-off-by: Fixture User <fixture@example.com>' \
    'Signed-off-by: Second Fixture <second@example.com>' \
    >"$two_valid_message"
  commit_fixture "$two_valid_message" two-valid-signoffs
  run_validator --all HEAD ||
    fail 'two valid Signed-off-by trailers were rejected'

  new_fixture mixed-signoffs
  mixed_signoffs_message=$tmp_dir/mixed-signoffs-message
  printf '%s\n\n%s\n%s\n' \
    'Valid and malformed sign-offs' \
    'Signed-off-by: Fixture User <fixture@example.com>' \
    'Signed-off-by: <malformed@example.com>' \
    >"$mixed_signoffs_message"
  commit_fixture "$mixed_signoffs_message" mixed-signoffs
  mixed_signoffs_sha=$(fixture_git rev-parse HEAD)
  mixed_signoffs_output=$tmp_dir/mixed-signoffs.out
  capture_failure "$mixed_signoffs_output" run_validator --all HEAD ||
    fail 'valid plus malformed sign-off did not report invalid Signed-off-by trailer'
  rg -q "$mixed_signoffs_sha" "$mixed_signoffs_output" ||
    fail 'mixed sign-off diagnostic omitted the commit SHA'
  rg -q 'invalid Signed-off-by trailer' "$mixed_signoffs_output" ||
    fail 'valid plus malformed sign-off did not report invalid Signed-off-by trailer'

  new_fixture trailing-empty-signoff
  trailing_empty_message=$tmp_dir/trailing-empty-signoff-message
  printf '%s\n\n%s\n%s\n' \
    'Valid then empty exact sign-off' \
    'Signed-off-by: Fixture User <fixture@example.com>' \
    'Signed-off-by:' \
    >"$trailing_empty_message"
  commit_fixture "$trailing_empty_message" trailing-empty-signoff
  trailing_empty_sha=$(fixture_git rev-parse HEAD)
  trailing_empty_output=$tmp_dir/trailing-empty-signoff.out
  capture_failure "$trailing_empty_output" run_validator --all HEAD ||
    fail 'trailing empty exact sign-off did not report invalid Signed-off-by trailer'
  rg -q "$trailing_empty_sha" "$trailing_empty_output" ||
    fail 'trailing empty exact sign-off diagnostic omitted the commit SHA'
  rg -q 'invalid Signed-off-by trailer' "$trailing_empty_output" ||
    fail 'trailing empty exact sign-off did not report invalid Signed-off-by trailer'

  new_fixture unsigned-squash
  squash_signed_message=$tmp_dir/squash-signed-message
  printf '%s\n\n%s\n' \
    'Signed source commit' \
    'Signed-off-by: Fixture User <fixture@example.com>' \
    >"$squash_signed_message"
  commit_fixture "$squash_signed_message" squash-base
  squash_base=$(fixture_git rev-parse HEAD)
  commit_fixture "$squash_signed_message" squash-first
  commit_fixture "$squash_signed_message" squash-second
  squash_tree=$(fixture_git rev-parse 'HEAD^{tree}')
  squash_sha=$(
    printf '%s\n' 'Synthetic unsigned squash commit' |
      fixture_git commit-tree "$squash_tree" -p "$squash_base"
  )
  squash_output=$tmp_dir/unsigned-squash.out
  capture_failure "$squash_output" \
    run_validator --range "$squash_base" "$squash_sha" ||
    fail 'synthetic unsigned squash did not report missing Signed-off-by trailer'
  rg -q "$squash_sha" "$squash_output" ||
    fail 'synthetic unsigned squash diagnostic omitted the commit SHA'
  rg -q 'missing Signed-off-by trailer' "$squash_output" ||
    fail 'synthetic unsigned squash did not report missing Signed-off-by trailer'

  new_fixture two-unsigned
  two_unsigned_base_message=$tmp_dir/two-unsigned-base-message
  printf '%s\n\n%s\n' \
    'Signed base for unsigned range' \
    'Signed-off-by: Fixture User <fixture@example.com>' \
    >"$two_unsigned_base_message"
  commit_fixture "$two_unsigned_base_message" two-unsigned-base
  two_unsigned_base=$(fixture_git rev-parse HEAD)
  first_unsigned_message=$tmp_dir/first-unsigned-message
  printf '%s\n' 'First unsigned commit' >"$first_unsigned_message"
  commit_fixture "$first_unsigned_message" first-unsigned
  first_unsigned_sha=$(fixture_git rev-parse HEAD)
  second_unsigned_message=$tmp_dir/second-unsigned-message
  printf '%s\n' 'Second unsigned commit' >"$second_unsigned_message"
  commit_fixture "$second_unsigned_message" second-unsigned
  second_unsigned_sha=$(fixture_git log -1 --format=%H)
  two_unsigned_output=$tmp_dir/two-unsigned.out
  capture_failure "$two_unsigned_output" \
    run_validator --range "$two_unsigned_base" "$second_unsigned_sha" ||
    fail 'two unsigned commits did not report both commit SHAs'
  rg -q "$first_unsigned_sha" "$two_unsigned_output" ||
    fail 'two unsigned commit diagnostic omitted the first SHA'
  rg -q "$second_unsigned_sha" "$two_unsigned_output" ||
    fail 'two unsigned commit diagnostic omitted the second SHA'

  new_fixture control-character-subject
  control_subject_message=$tmp_dir/control-subject-message
  printf 'Control\tcharacter\r subject\n' >"$control_subject_message"
  commit_fixture "$control_subject_message" control-subject
  control_subject_sha=$(fixture_git rev-parse HEAD)
  stored_control_subject=$tmp_dir/stored-control-subject
  fixture_git log -1 --format=%s >"$stored_control_subject"
  tab_count=$(
    LC_ALL=C tr -cd '\011' <"$stored_control_subject" |
      wc -c |
      tr -d '[:space:]'
  )
  [ "$tab_count" -gt 0 ] ||
    fail 'control-character fixture subject did not retain a tab byte'
  subject_cr_count=$(
    LC_ALL=C tr -cd '\015' <"$stored_control_subject" |
      wc -c |
      tr -d '[:space:]'
  )
  [ "$subject_cr_count" -gt 0 ] ||
    fail 'control-character fixture subject did not retain a CR byte'
  control_subject_output=$tmp_dir/control-subject.out
  capture_failure "$control_subject_output" run_validator --all HEAD ||
    fail 'control-character subject did not report missing Signed-off-by trailer'
  rg -q "$control_subject_sha" "$control_subject_output" ||
    fail 'control-character subject diagnostic omitted the commit SHA'
  rg -q 'missing Signed-off-by trailer' "$control_subject_output" ||
    fail 'control-character subject did not report missing Signed-off-by trailer'
  sanitized_control_output=$tmp_dir/control-subject-sanitized.out
  LC_ALL=C tr -d '\000-\011\013-\037\177' \
    <"$control_subject_output" >"$sanitized_control_output"
  cmp -s "$control_subject_output" "$sanitized_control_output" ||
    fail 'control-character subject diagnostic contains control characters'

  printf 'policy fixtures (dco): ok\n'
}

case ${1:-} in
  tools)
    test_tools
    ;;
  dco)
    test_dco
    ;;
  *)
    printf 'usage: %s {tools|dco}\n' "$0" >&2
    exit 2
    ;;
esac
