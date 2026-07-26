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

test_links() {
  validator=$script_dir/check-markdown-links.sh
  installer=$script_dir/install-policy-tools.sh

  [ -x "$validator" ] ||
    fail 'Markdown link validator is missing or not executable'

  link_tool_dir=$tmp_dir/link-policy-tools
  if ! lychee=$("$installer" install "$link_tool_dir" lychee); then
    fail 'could not install the approved Lychee release'
  fi
  [ "$lychee" = "$link_tool_dir/bin/lychee" ] ||
    fail 'Lychee installer returned an unexpected executable path'
  [ -x "$lychee" ] ||
    fail 'Lychee installer did not create an executable'

  run_link_validator() {
    run_link_repository=$1
    shift
    (
      cd "$run_link_repository"
      "$validator" "$@"
    )
  }

  run_link_validator_with_tmp() {
    run_link_repository=$1
    run_link_tmp=$2
    shift 2
    (
      cd "$run_link_repository"
      TMPDIR=$run_link_tmp "$validator" "$@"
    )
  }

  run_link_validator_with_tmp_c_locale() {
    run_link_repository=$1
    run_link_tmp=$2
    shift 2
    (
      cd "$run_link_repository"
      LC_ALL=C TMPDIR=$run_link_tmp "$validator" "$@"
    )
  }

  run_link_validator_with_path() {
    run_link_repository=$1
    run_link_path=$2
    run_link_real_git=$3
    run_link_move_to=$4
    shift 4
    (
      cd "$run_link_repository"
      PATH=$run_link_path \
        TASK4_REAL_GIT=$run_link_real_git \
        TASK4_MOVE_TO=$run_link_move_to \
        "$validator" "$@"
    )
  }

  run_link_validator_with_dump() {
    run_link_repository=$1
    run_link_dump_kind=$2
    run_link_dump_lychee=$3
    (
      cd "$run_link_repository"
      TASK4_DUMP_KIND=$run_link_dump_kind \
        "$validator" --revision HEAD --lychee "$run_link_dump_lychee"
    )
  }

  fixture_repo=$tmp_dir/link-fixture
  mkdir -p "$fixture_repo/docs"
  git -C "$fixture_repo" init --quiet --template="$tmp_dir/empty-template"
  git -C "$fixture_repo" config user.name 'Fixture User'
  git -C "$fixture_repo" config user.email 'fixture@example.com'
  printf '# Target\n' >"$fixture_repo/docs/target.md"
  printf '# Links\n\n[valid](target.md)\n' >"$fixture_repo/docs/guide.md"
  git -C "$fixture_repo" add docs/guide.md docs/target.md
  git -C "$fixture_repo" commit --quiet -m 'Valid inline link'

  (
    cd "$fixture_repo"
    "$validator" --revision HEAD --lychee "$lychee"
  ) || fail 'valid inline link was rejected'

  immutable_revision_repo=$tmp_dir/immutable-revision-fixture
  mkdir -p "$immutable_revision_repo/docs"
  git -C "$immutable_revision_repo" init --quiet \
    --template="$tmp_dir/empty-template"
  git -C "$immutable_revision_repo" config user.name 'Fixture User'
  git -C "$immutable_revision_repo" config user.email 'fixture@example.com'
  printf '# Target\n' >"$immutable_revision_repo/docs/target.md"
  printf '# Links\n\n[valid](target.md)\n' \
    >"$immutable_revision_repo/docs/guide.md"
  git -C "$immutable_revision_repo" add docs
  git -C "$immutable_revision_repo" commit --quiet -m 'Valid moving revision'
  immutable_revision_oid=$(
    git -C "$immutable_revision_repo" rev-parse HEAD
  )
  printf '# Links\n\n[missing](missing.md)\n' \
    >"$immutable_revision_repo/docs/guide.md"
  git -C "$immutable_revision_repo" add docs/guide.md
  git -C "$immutable_revision_repo" commit --quiet -m 'Moved revision'
  moved_revision_oid=$(git -C "$immutable_revision_repo" rev-parse HEAD)
  git -C "$immutable_revision_repo" branch moving "$immutable_revision_oid"

  git_wrapper_dir=$tmp_dir/git-wrapper
  mkdir -p "$git_wrapper_dir"
  real_git=$(command -v git)
  # shellcheck disable=SC2016
  printf '%s\n' \
    '#!/bin/sh' \
    'set -eu' \
    'if [ "$#" -eq 3 ] && [ "$1" = rev-parse ] &&' \
    '  [ "$2" = --verify ] && [ "$3" = "moving^{commit}" ]; then' \
    '  resolved=$("$TASK4_REAL_GIT" "$@")' \
    '  "$TASK4_REAL_GIT" update-ref refs/heads/moving "$TASK4_MOVE_TO"' \
    '  printf "%s\n" "$resolved"' \
    '  exit 0' \
    'fi' \
    'exec "$TASK4_REAL_GIT" "$@"' \
    >"$git_wrapper_dir/git"
  chmod +x "$git_wrapper_dir/git"

  run_link_validator_with_path "$immutable_revision_repo" \
    "$git_wrapper_dir:$PATH" "$real_git" "$moved_revision_oid" \
    --revision moving --lychee "$lychee" ||
    fail 'validator reused a mutable revision after resolving it'
  [ "$(git -C "$immutable_revision_repo" rev-parse moving)" = \
    "$moved_revision_oid" ] ||
    fail 'mutable revision fixture did not move during validation'

  invalid_revision_output=$tmp_dir/invalid-link-revision.out
  capture_failure "$invalid_revision_output" \
    run_link_validator "$fixture_repo" \
    --revision not-a-commit --lychee "$lychee" ||
    fail 'invalid link-check revision was accepted'
  rg -q 'invalid commit revision: not-a-commit' "$invalid_revision_output" ||
    fail 'invalid link-check revision did not report its value'

  relative_lychee_output=$tmp_dir/relative-lychee.out
  capture_failure "$relative_lychee_output" \
    run_link_validator "$fixture_repo" \
    --revision HEAD --lychee ./lychee ||
    fail 'relative Lychee executable path was accepted'
  rg -q 'Lychee path must be absolute' "$relative_lychee_output" ||
    fail 'relative Lychee path did not report the absolute-path requirement'

  nonexecutable_lychee=$tmp_dir/nonexecutable-lychee
  : >"$nonexecutable_lychee"
  nonexecutable_lychee_output=$tmp_dir/nonexecutable-lychee.out
  capture_failure "$nonexecutable_lychee_output" \
    run_link_validator "$fixture_repo" \
    --revision HEAD --lychee "$nonexecutable_lychee" ||
    fail 'nonexecutable absolute Lychee path was accepted'
  rg -q 'Lychee path is not executable:' "$nonexecutable_lychee_output" ||
    fail 'nonexecutable Lychee path did not report a clear diagnostic'

  dump_lychee=$tmp_dir/dump-lychee
  # shellcheck disable=SC2016
  printf '%s\n' \
    '#!/bin/sh' \
    'set -eu' \
    'root_dir=' \
    'dump=false' \
    'while [ "$#" -gt 0 ]; do' \
    '  case $1 in' \
    '    --root-dir)' \
    '      root_dir=$2' \
    '      shift 2' \
    '      ;;' \
    '    --dump)' \
    '      dump=true' \
    '      shift' \
    '      ;;' \
    '    *)' \
    '      shift' \
    '      ;;' \
    '  esac' \
    'done' \
    'if [ "$dump" = true ]; then' \
    '  case $TASK4_DUMP_KIND in' \
    '    invalid)' \
    '      printf "file://%s/docs/invalid%%ZZ.md\n" "$root_dir"' \
    '      ;;' \
    '    invalid_utf8)' \
    '      printf "file://%s/docs/invalid%%FF.md\n" "$root_dir"' \
    '      ;;' \
    '    nul)' \
    '      printf "file://%s/docs/nul%%00.md\n" "$root_dir"' \
    '      ;;' \
    '    authority)' \
    '      printf "file://example.com/path\n"' \
    '      ;;' \
    '  esac' \
    'fi' \
    >"$dump_lychee"
  chmod +x "$dump_lychee"

  invalid_file_url_output=$tmp_dir/invalid-file-url.out
  capture_failure "$invalid_file_url_output" \
    run_link_validator_with_dump "$fixture_repo" invalid "$dump_lychee" ||
    fail 'invalid serialized file URL was accepted'
  rg -q 'invalid file URL in Markdown:' "$invalid_file_url_output" ||
    fail 'invalid serialized file URL did not report a clear diagnostic'

  invalid_utf8_output=$tmp_dir/invalid-utf8-file-url.out
  capture_failure "$invalid_utf8_output" \
    run_link_validator_with_dump \
    "$fixture_repo" invalid_utf8 "$dump_lychee" ||
    fail 'non-UTF-8 file URL path was accepted'
  rg -q 'file URL path is not valid UTF-8:' "$invalid_utf8_output" ||
    fail 'non-UTF-8 file URL path did not report a clear diagnostic'

  nul_file_url_output=$tmp_dir/nul-file-url.out
  capture_failure "$nul_file_url_output" \
    run_link_validator_with_dump "$fixture_repo" nul "$dump_lychee" ||
    fail 'NUL-encoded file URL was accepted'
  rg -q 'file URL contains a NUL byte:' "$nul_file_url_output" ||
    fail 'NUL-encoded file URL did not report a clear diagnostic'

  authority_file_url_output=$tmp_dir/authority-file-url.out
  capture_failure "$authority_file_url_output" \
    run_link_validator_with_dump "$fixture_repo" authority "$dump_lychee" ||
    fail 'remote-authority file URL was accepted'
  rg -q 'file URL authority is not allowed:' "$authority_file_url_output" ||
    fail 'remote-authority file URL did not report a clear diagnostic'

  inside_snapshot_output=$tmp_dir/inside-snapshot.out
  capture_failure "$inside_snapshot_output" \
    run_link_validator_with_tmp "$fixture_repo" "$fixture_repo" \
    --revision HEAD --lychee "$lychee" ||
    fail 'snapshot directory inside the repository was accepted'
  rg -q 'snapshot directory must be outside the repository' \
    "$inside_snapshot_output" ||
    fail 'inside-repository snapshot did not report a clear diagnostic'
  if find "$fixture_repo" -maxdepth 1 -type d \
    -name 'engrammesh-links.*' -print | rg -q .; then
    fail 'rejected inside-repository snapshot was not cleaned up'
  fi

  printf '\n[missing](missing.md)\n' >>"$fixture_repo/docs/guide.md"
  git -C "$fixture_repo" add docs/guide.md
  git -C "$fixture_repo" commit --quiet -m 'Missing link target'
  missing_output=$tmp_dir/missing-link.out
  capture_failure "$missing_output" \
    run_link_validator "$fixture_repo" \
    --revision HEAD --lychee "$lychee" ||
    fail 'missing tracked target was accepted'
  rg -q 'File not found[.] Check if file exists and path is correct' \
    "$missing_output" ||
    fail 'missing tracked target did not report the Lychee missing-file diagnostic'

  untracked_repo=$tmp_dir/untracked-target-fixture
  mkdir -p "$untracked_repo/docs"
  git -C "$untracked_repo" init --quiet --template="$tmp_dir/empty-template"
  git -C "$untracked_repo" config user.name 'Fixture User'
  git -C "$untracked_repo" config user.email 'fixture@example.com'
  printf '# Links\n\n[untracked](untracked-target.md)\n' \
    >"$untracked_repo/docs/guide.md"
  printf '# Untracked target\n' >"$untracked_repo/docs/untracked-target.md"
  git -C "$untracked_repo" add docs/guide.md
  git -C "$untracked_repo" commit --quiet -m 'Untracked link target'
  git -C "$untracked_repo" status --short --untracked-files=all |
    rg -q 'docs/untracked-target[.]md' ||
    fail 'untracked link target fixture was accidentally tracked'
  untracked_output=$tmp_dir/untracked-target.out
  capture_failure "$untracked_output" \
    run_link_validator "$untracked_repo" \
    --revision HEAD --lychee "$lychee" ||
    fail 'existing but untracked link target was accepted'
  rg -q 'File not found[.] Check if file exists and path is correct' \
    "$untracked_output" ||
    fail 'untracked link target did not report the missing-file diagnostic'

  ignored_repo=$tmp_dir/ignored-target-fixture
  mkdir -p "$ignored_repo/docs"
  git -C "$ignored_repo" init --quiet --template="$tmp_dir/empty-template"
  git -C "$ignored_repo" config user.name 'Fixture User'
  git -C "$ignored_repo" config user.email 'fixture@example.com'
  printf 'docs/ignored-target.md\n' >"$ignored_repo/.gitignore"
  printf '# Links\n\n[ignored](ignored-target.md)\n' \
    >"$ignored_repo/docs/guide.md"
  printf '# Ignored target\n' >"$ignored_repo/docs/ignored-target.md"
  git -C "$ignored_repo" add .gitignore docs/guide.md
  git -C "$ignored_repo" commit --quiet -m 'Ignored link target'
  git -C "$ignored_repo" check-ignore -q docs/ignored-target.md ||
    fail 'ignored link target fixture was not ignored'
  ignored_output=$tmp_dir/ignored-target.out
  capture_failure "$ignored_output" \
    run_link_validator "$ignored_repo" \
    --revision HEAD --lychee "$lychee" ||
    fail 'existing but ignored link target was accepted'
  rg -q 'File not found[.] Check if file exists and path is correct' \
    "$ignored_output" ||
    fail 'ignored link target did not report the missing-file diagnostic'

  encoded_prefix_tmp_dir=$tmp_dir/snapshot\ space\ %\ ü
  mkdir -p "$encoded_prefix_tmp_dir"
  encoded_prefix_repo=$tmp_dir/encoded-prefix-fixture
  mkdir -p "$encoded_prefix_repo/docs"
  git -C "$encoded_prefix_repo" init --quiet \
    --template="$tmp_dir/empty-template"
  git -C "$encoded_prefix_repo" config user.name 'Fixture User'
  git -C "$encoded_prefix_repo" config user.email 'fixture@example.com'
  printf '# Encoded prefix target\n' \
    >"$encoded_prefix_repo/docs/space % ü.md"
  printf '# Links\n\n[target](space%%20%%25%%20%%C3%%BC.md)\n' \
    >"$encoded_prefix_repo/docs/guide.md"
  git -C "$encoded_prefix_repo" add docs
  git -C "$encoded_prefix_repo" commit --quiet \
    -m 'Encoded snapshot prefix characters'
  run_link_validator_with_tmp_c_locale \
    "$encoded_prefix_repo" "$encoded_prefix_tmp_dir" \
    --revision HEAD --lychee "$lychee" ||
    fail 'valid non-ASCII snapshot prefix was rejected under LC_ALL=C'

  escape_tmp_dir=$tmp_dir/escape-snapshots
  mkdir -p "$escape_tmp_dir"
  printf '# Outside snapshot\n' >"$escape_tmp_dir/outside.md"

  plain_escape_repo=$tmp_dir/plain-escape-fixture
  mkdir -p "$plain_escape_repo/docs"
  git -C "$plain_escape_repo" init --quiet --template="$tmp_dir/empty-template"
  git -C "$plain_escape_repo" config user.name 'Fixture User'
  git -C "$plain_escape_repo" config user.email 'fixture@example.com'
  printf '# Links\n\n[escape](../../outside.md)\n' \
    >"$plain_escape_repo/docs/guide.md"
  git -C "$plain_escape_repo" add docs/guide.md
  git -C "$plain_escape_repo" commit --quiet -m 'Parent-directory escape'
  plain_escape_output=$tmp_dir/plain-escape.out
  capture_failure "$plain_escape_output" \
    run_link_validator_with_tmp "$plain_escape_repo" "$escape_tmp_dir" \
    --revision HEAD --lychee "$lychee" ||
    fail '../ link target escape was accepted'
  rg -q 'link target escapes snapshot: .*outside[.]md' \
    "$plain_escape_output" ||
    fail '../ link target escape did not report the escaped target'

  encoded_escape_repo=$tmp_dir/encoded-escape-fixture
  mkdir -p "$encoded_escape_repo/docs"
  git -C "$encoded_escape_repo" init --quiet \
    --template="$tmp_dir/empty-template"
  git -C "$encoded_escape_repo" config user.name 'Fixture User'
  git -C "$encoded_escape_repo" config user.email 'fixture@example.com'
  printf '# Links\n\n[escape](%%2e%%2e/%%2e%%2e/outside.md)\n' \
    >"$encoded_escape_repo/docs/guide.md"
  git -C "$encoded_escape_repo" add docs/guide.md
  git -C "$encoded_escape_repo" commit --quiet \
    -m 'Percent-encoded parent-directory escape'
  encoded_escape_output=$tmp_dir/encoded-escape.out
  capture_failure "$encoded_escape_output" \
    run_link_validator_with_tmp "$encoded_escape_repo" "$escape_tmp_dir" \
    --revision HEAD --lychee "$lychee" ||
    fail 'percent-encoded link target escape was accepted'
  rg -q 'link target escapes snapshot: .*outside[.]md' \
    "$encoded_escape_output" ||
    fail 'percent-encoded escape did not report the escaped target'

  encoded_separator_repo=$tmp_dir/encoded-separator-fixture
  mkdir -p "$encoded_separator_repo/docs"
  git -C "$encoded_separator_repo" init --quiet \
    --template="$tmp_dir/empty-template"
  git -C "$encoded_separator_repo" config user.name 'Fixture User'
  git -C "$encoded_separator_repo" config user.email 'fixture@example.com'
  printf '# Links\n\n[escape](%%2e%%2e%%2f%%2e%%2e%%2foutside.md)\n' \
    >"$encoded_separator_repo/docs/guide.md"
  git -C "$encoded_separator_repo" add docs/guide.md
  git -C "$encoded_separator_repo" commit --quiet \
    -m 'Percent-encoded separator escape'
  encoded_separator_output=$tmp_dir/encoded-separator.out
  capture_failure "$encoded_separator_output" \
    run_link_validator_with_tmp "$encoded_separator_repo" "$escape_tmp_dir" \
    --revision HEAD --lychee "$lychee" ||
    fail 'percent-encoded separator escape was accepted'
  rg -q 'link target escapes snapshot: .*outside[.]md' \
    "$encoded_separator_output" ||
    fail 'percent-encoded separator escape did not report the escaped target'

  validate_link_fixture() {
    description=$1
    (
      cd "$fixture_repo"
      "$validator" --revision HEAD --lychee "$lychee"
    ) || fail "$description"
  }

  printf '# Links\n\n[inline](target.md)\n' \
    >"$fixture_repo/docs/guide.md"
  git -C "$fixture_repo" add docs/guide.md
  git -C "$fixture_repo" commit --quiet -m 'Restore valid inline link'

  printf '# Reference target\n' \
    >"$fixture_repo/docs/reference-target.md"
  printf '\n[reference][tracked target]\n\n%s\n' \
    '[tracked target]: reference-target.md' \
    >>"$fixture_repo/docs/guide.md"
  git -C "$fixture_repo" add docs
  git -C "$fixture_repo" commit --quiet -m 'Reference-style link'
  validate_link_fixture 'valid reference-style link was rejected'

  printf '# Root target\n' >"$fixture_repo/docs/root-target.md"
  printf '\n[root relative](/docs/root-target.md)\n' \
    >>"$fixture_repo/docs/guide.md"
  git -C "$fixture_repo" add docs
  git -C "$fixture_repo" commit --quiet -m 'Root-relative link'
  validate_link_fixture 'valid root-relative link was rejected'

  printf '# Query target\n' >"$fixture_repo/docs/query-target.md"
  printf '# Fragment target\n' >"$fixture_repo/docs/fragment-target.md"
  printf '\n[query](query-target.md?view=full)\n%s\n' \
    '[fragment](fragment-target.md#missing-anchor)' \
    >>"$fixture_repo/docs/guide.md"
  git -C "$fixture_repo" add docs
  git -C "$fixture_repo" commit --quiet -m 'Query and fragment links'
  validate_link_fixture 'valid query or unchecked fragment link was rejected'

  mkdir -p "$fixture_repo/docs/space dir"
  printf '# Space target\n' \
    >"$fixture_repo/docs/space dir/space target.md"
  printf '\n[space](<space dir/space target.md>)\n' \
    >>"$fixture_repo/docs/guide.md"
  git -C "$fixture_repo" add docs
  git -C "$fixture_repo" commit --quiet -m 'Angle-bracket path with spaces'
  validate_link_fixture 'valid angle-bracket path with spaces was rejected'

  printf '\n\\[escaped](missing-escaped-target.md)\n' \
    >>"$fixture_repo/docs/guide.md"
  git -C "$fixture_repo" add docs/guide.md
  git -C "$fixture_repo" commit --quiet -m 'Escaped link syntax'
  validate_link_fixture 'escaped link syntax was treated as a link'

  printf '%s\n' \
    '' \
    '````text' \
    '```' \
    '[fenced example](missing-fenced-target.md)' \
    '```' \
    '````' \
    '' \
    '~~~~text' \
    '~~~' \
    '[tilde example](missing-tilde-target.md)' \
    '~~~' \
    '~~~~' \
    >>"$fixture_repo/docs/guide.md"
  git -C "$fixture_repo" add docs/guide.md
  git -C "$fixture_repo" commit --quiet -m 'Variable-length code fences'
  validate_link_fixture 'link syntax in variable-length fences was checked'

  printf '%s\n' \
    '' \
    '`[multiline inline code' \
    'example](missing-inline-code-target.md)`' \
    >>"$fixture_repo/docs/guide.md"
  git -C "$fixture_repo" add docs/guide.md
  git -C "$fixture_repo" commit --quiet -m 'Multiline inline code'
  validate_link_fixture 'link syntax in multiline inline code was checked'

  printf '# Nested target\n' >"$fixture_repo/docs/nested(target).md"
  printf '# Encoded target\n' >"$fixture_repo/docs/encoded(target).md"
  printf '\n[nested](nested(target).md)\n[encoded](encoded%%28target%%29.md)\n' \
    >>"$fixture_repo/docs/guide.md"
  git -C "$fixture_repo" add docs
  git -C "$fixture_repo" commit --quiet -m 'Parentheses in link targets'
  validate_link_fixture 'valid nested or percent-encoded parentheses were rejected'

  printf '\n[protocol relative](//example.com/path)\n' \
    >>"$fixture_repo/docs/guide.md"
  git -C "$fixture_repo" add docs/guide.md
  git -C "$fixture_repo" commit --quiet -m 'Protocol-relative link'
  validate_link_fixture 'protocol-relative link was rejected in offline mode'
  protocol_relative_output=$tmp_dir/protocol-relative.out
  (
    cd "$fixture_repo"
    "$lychee" \
      --offline \
      --no-progress \
      --include-fragments=none \
      --root-dir "$fixture_repo" \
      './**/*.md'
  ) >"$protocol_relative_output"
  rg -q '1 Excluded' "$protocol_relative_output" ||
    fail 'protocol-relative link was not discovered as an offline exclusion'

  printf '# CRLF target\n' >"$fixture_repo/docs/crlf-target.md"
  printf '# CRLF\r\n\r\n[valid](crlf-target.md)\r\n' \
    >"$fixture_repo/docs/crlf.md"
  git -C "$fixture_repo" add docs
  git -C "$fixture_repo" commit --quiet -m 'CRLF Markdown source'
  stored_crlf_markdown=$tmp_dir/stored-crlf-markdown
  git -C "$fixture_repo" show HEAD:docs/crlf.md >"$stored_crlf_markdown"
  crlf_markdown_count=$(
    LC_ALL=C tr -cd '\015' <"$stored_crlf_markdown" |
      wc -c |
      tr -d '[:space:]'
  )
  [ "$crlf_markdown_count" -gt 0 ] ||
    fail 'CRLF Markdown fixture did not retain CR bytes'
  validate_link_fixture 'valid link in CRLF Markdown was rejected'

  mkdir -p "$fixture_repo/docs/tracked-directory"
  printf 'Tracked directory fixture.\n' \
    >"$fixture_repo/docs/tracked-directory/placeholder.txt"
  printf '\n[directory](tracked-directory/)\n' \
    >>"$fixture_repo/docs/guide.md"
  git -C "$fixture_repo" add docs
  git -C "$fixture_repo" commit --quiet -m 'Tracked directory target'
  validate_link_fixture 'valid tracked directory target was rejected'

  discovery_snapshot=$tmp_dir/link-discovery-snapshot
  mkdir -p "$discovery_snapshot"
  git -C "$fixture_repo" archive HEAD | tar -x -C "$discovery_snapshot"
  discovery_snapshot=$(
    CDPATH='' cd -- "$discovery_snapshot" && pwd -P
  )
  discovery_output=$tmp_dir/link-discovery.out
  (
    cd "$discovery_snapshot"
    "$lychee" \
      --offline \
      --no-progress \
      --include-fragments=none \
      --root-dir "$discovery_snapshot" \
      --dump \
      './**/*.md'
  ) >"$discovery_output"

  for discovered_link in \
    'docs/target.md' \
    'docs/reference-target.md' \
    'docs/root-target.md' \
    'docs/query-target.md?view=full' \
    'docs/fragment-target.md' \
    'docs/space%20dir/space%20target.md' \
    'docs/nested(target).md' \
    'docs/encoded%28target%29.md' \
    'docs/crlf-target.md' \
    'docs/tracked-directory'; do
    rg -Fq "$discovered_link" "$discovery_output" ||
      fail "Lychee dump omitted valid CommonMark target: $discovered_link"
  done
  for ignored_link in \
    'missing-escaped-target.md' \
    'missing-fenced-target.md' \
    'missing-tilde-target.md' \
    'missing-inline-code-target.md'; do
    if rg -Fq "$ignored_link" "$discovery_output"; then
      fail "Lychee dump discovered ignored code syntax: $ignored_link"
    fi
  done

  no_markdown_repo=$tmp_dir/no-markdown-fixture
  mkdir -p "$no_markdown_repo"
  git -C "$no_markdown_repo" init --quiet --template="$tmp_dir/empty-template"
  git -C "$no_markdown_repo" config user.name 'Fixture User'
  git -C "$no_markdown_repo" config user.email 'fixture@example.com'
  printf 'No Markdown here.\n' >"$no_markdown_repo/tracked.txt"
  git -C "$no_markdown_repo" add tracked.txt
  git -C "$no_markdown_repo" commit --quiet -m 'No Markdown files'
  no_markdown_output=$tmp_dir/no-markdown.out
  capture_failure "$no_markdown_output" \
    run_link_validator "$no_markdown_repo" \
    --revision HEAD --lychee "$lychee" ||
    fail 'revision without tracked Markdown was accepted'
  rg -q 'no tracked Markdown files' "$no_markdown_output" ||
    fail 'revision without tracked Markdown did not report a clear diagnostic'

  relative_symlink_repo=$tmp_dir/relative-symlink-fixture
  mkdir -p "$relative_symlink_repo/docs"
  git -C "$relative_symlink_repo" init --quiet \
    --template="$tmp_dir/empty-template"
  git -C "$relative_symlink_repo" config user.name 'Fixture User'
  git -C "$relative_symlink_repo" config user.email 'fixture@example.com'
  printf '# Links\n' >"$relative_symlink_repo/docs/guide.md"
  ln -s guide.md "$relative_symlink_repo/docs/relative-link.md"
  git -C "$relative_symlink_repo" add docs/guide.md docs/relative-link.md
  git -C "$relative_symlink_repo" commit --quiet -m 'Relative tracked symlink'
  relative_symlink_output=$tmp_dir/relative-symlink.out
  capture_failure "$relative_symlink_output" \
    run_link_validator "$relative_symlink_repo" \
    --revision HEAD --lychee "$lychee" ||
    fail 'relative tracked symlink was accepted'
  rg -q 'tracked symbolic link is not allowed: docs/relative-link[.]md' \
    "$relative_symlink_output" ||
    fail 'relative tracked symlink diagnostic omitted its path'

  absolute_symlink_repo=$tmp_dir/absolute-symlink-fixture
  mkdir -p "$absolute_symlink_repo/docs"
  git -C "$absolute_symlink_repo" init --quiet \
    --template="$tmp_dir/empty-template"
  git -C "$absolute_symlink_repo" config user.name 'Fixture User'
  git -C "$absolute_symlink_repo" config user.email 'fixture@example.com'
  printf '# Links\n' >"$absolute_symlink_repo/docs/guide.md"
  ln -s "$absolute_symlink_repo/docs/guide.md" \
    "$absolute_symlink_repo/docs/absolute-link.md"
  git -C "$absolute_symlink_repo" add docs/guide.md docs/absolute-link.md
  git -C "$absolute_symlink_repo" commit --quiet -m 'Absolute tracked symlink'
  absolute_symlink_output=$tmp_dir/absolute-symlink.out
  capture_failure "$absolute_symlink_output" \
    run_link_validator "$absolute_symlink_repo" \
    --revision HEAD --lychee "$lychee" ||
    fail 'absolute tracked symlink was accepted'
  rg -q 'tracked symbolic link is not allowed: docs/absolute-link[.]md' \
    "$absolute_symlink_output" ||
    fail 'absolute tracked symlink diagnostic omitted its path'

  printf 'policy fixtures (links): ok\n'
}

case ${1:-} in
  tools)
    test_tools
    ;;
  dco)
    test_dco
    ;;
  links)
    test_links
    ;;
  *)
    printf 'usage: %s {tools|dco|links}\n' "$0" >&2
    exit 2
    ;;
esac
