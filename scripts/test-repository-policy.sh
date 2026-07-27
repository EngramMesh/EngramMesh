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
  grep -Fq 'invalid SHA-256 digest' "$invalid_digest_output" ||
    fail 'malformed digest did not report invalid SHA-256 digest'

  mismatch_output=$tmp_dir/checksum-mismatch.out
  capture_failure "$mismatch_output" \
    "$installer" verify-sha256 "$checksum_fixture" \
    0000000000000000000000000000000000000000000000000000000000000000 ||
    fail 'verify-sha256 accepted an incorrect digest'
  grep -Fq 'SHA-256 mismatch' "$mismatch_output" ||
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
  grep -Fq 'unsupported policy-tool platform' "$unsupported_output" ||
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
  "$install_dir/bin/lychee" --version | grep -Eq '0[.]24[.]2' ||
    fail 'installed lychee did not report version 0.24.2'
  "$install_dir/bin/actionlint" --version | grep -Eq '1[.]7[.]12' ||
    fail 'installed actionlint did not report version 1.7.12'
  if find "$install_dir/download" -type f -print | grep -q .; then
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
  grep -Fq "$unsigned_sha" "$unsigned_output" ||
    fail 'unsigned commit diagnostic omitted the commit SHA'
  grep -Fq 'missing Signed-off-by trailer' "$unsigned_output" ||
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
  grep -Fq 'invalid commit revision' "$invalid_base_output" ||
    fail 'invalid base revision did not report invalid commit revision'

  invalid_head_output=$tmp_dir/invalid-head.out
  capture_failure "$invalid_head_output" \
    run_validator --range "$range_base" not-a-commit ||
    fail 'invalid head revision was accepted'
  grep -Fq 'invalid commit revision' "$invalid_head_output" ||
    fail 'invalid head revision did not report invalid commit revision'

  empty_range_output=$tmp_dir/empty-range.out
  capture_failure "$empty_range_output" \
    run_validator --range "$range_head" "$range_head" ||
    fail 'BASE == HEAD did not report DCO range contains no commits'
  grep -Fq 'DCO range contains no commits' "$empty_range_output" ||
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
  grep -Fq "$subject_signoff_sha" "$subject_signoff_output" ||
    fail 'Signed-off-by in subject diagnostic omitted the commit SHA'
  grep -Fq 'missing Signed-off-by trailer' "$subject_signoff_output" ||
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
  grep -Fq "$lowercase_signoff_sha" "$lowercase_signoff_output" ||
    fail 'lowercase sign-off key diagnostic omitted the commit SHA'
  grep -Fq 'missing Signed-off-by trailer' "$lowercase_signoff_output" ||
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
  grep -Fq "$miscased_signoff_sha" "$miscased_signoff_output" ||
    fail 'miscased sign-off key diagnostic omitted the commit SHA'
  grep -Fq 'missing Signed-off-by trailer' "$miscased_signoff_output" ||
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
  grep -Fq "$signoff_before_body_sha" "$signoff_before_body_output" ||
    fail 'sign-off followed by body diagnostic omitted the commit SHA'
  grep -Fq 'missing Signed-off-by trailer' "$signoff_before_body_output" ||
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
  grep -Fq "$malformed_signoff_sha" "$malformed_signoff_output" ||
    fail 'empty-name sign-off diagnostic omitted the commit SHA'
  grep -Fq 'invalid Signed-off-by trailer' "$malformed_signoff_output" ||
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
  grep -Fq "$empty_signoff_sha" "$empty_signoff_output" ||
    fail 'empty exact sign-off diagnostic omitted the commit SHA'
  grep -Fq 'invalid Signed-off-by trailer' "$empty_signoff_output" ||
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
  grep -Fq "$no_at_sha" "$no_at_output" ||
    fail 'address without @ diagnostic omitted the commit SHA'
  grep -Fq 'invalid Signed-off-by trailer' "$no_at_output" ||
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
  grep -Fq "$mixed_signoffs_sha" "$mixed_signoffs_output" ||
    fail 'mixed sign-off diagnostic omitted the commit SHA'
  grep -Fq 'invalid Signed-off-by trailer' "$mixed_signoffs_output" ||
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
  grep -Fq "$trailing_empty_sha" "$trailing_empty_output" ||
    fail 'trailing empty exact sign-off diagnostic omitted the commit SHA'
  grep -Fq 'invalid Signed-off-by trailer' "$trailing_empty_output" ||
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
  grep -Fq "$squash_sha" "$squash_output" ||
    fail 'synthetic unsigned squash diagnostic omitted the commit SHA'
  grep -Fq 'missing Signed-off-by trailer' "$squash_output" ||
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
  grep -Fq "$first_unsigned_sha" "$two_unsigned_output" ||
    fail 'two unsigned commit diagnostic omitted the first SHA'
  grep -Fq "$second_unsigned_sha" "$two_unsigned_output" ||
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
  grep -Fq "$control_subject_sha" "$control_subject_output" ||
    fail 'control-character subject diagnostic omitted the commit SHA'
  grep -Fq 'missing Signed-off-by trailer' "$control_subject_output" ||
    fail 'control-character subject did not report missing Signed-off-by trailer'
  sanitized_control_output=$tmp_dir/control-subject-sanitized.out
  LC_ALL=C tr -d '\000-\011\013-\037\177' \
    <"$control_subject_output" >"$sanitized_control_output"
  cmp -s "$control_subject_output" "$sanitized_control_output" ||
    fail 'control-character subject diagnostic contains control characters'

  printf 'policy fixtures (dco): ok\n'
}

test_history() {
  validator=$script_dir/check-private-history.sh
  fixture_repo=

  fixture_git() {
    git -C "$fixture_repo" \
      -c core.hooksPath=/dev/null \
      -c commit.gpgsign=false \
      -c core.autocrlf=false \
      -c core.eol=lf \
      "$@"
  }

  new_history_fixture() {
    fixture_repo=$tmp_dir/history-$1
    mkdir -p "$fixture_repo"
    fixture_git init --quiet --template="$tmp_dir/empty-template"
    fixture_git config user.name 'Fixture User'
    fixture_git config user.email 'fixture@example.com'
  }

  commit_history_file() {
    path=$1
    content=$2
    mkdir -p "$fixture_repo/$(dirname -- "$path")"
    printf '%s\n' "$content" >"$fixture_repo/$path"
    fixture_git add "$path"
    fixture_git commit --quiet -m "Add $path"
  }

  run_history_validator() {
    (
      cd "$fixture_repo"
      "$validator" "$@"
    )
  }

  new_history_fixture clean
  commit_history_file README.md clean
  run_history_validator HEAD ||
    fail 'clean history was rejected'
  commit_history_file .superpowers-public/spec.md public
  commit_history_file docs/superpowers-public/notes.md public
  commit_history_file docs/plans-public/roadmap.md public
  commit_history_file .superpowers-public/秘密.md public
  public_newline_path='docs/superpowers-public/public
notes.md'
  commit_history_file "$public_newline_path" public
  run_history_validator HEAD ||
    fail 'lookalike path components were rejected'
  invalid_history_revision_output=$tmp_dir/invalid-history-revision.out
  capture_failure "$invalid_history_revision_output" \
    run_history_validator not-a-commit ||
    fail 'invalid history revision was accepted'
  grep -Fqx 'invalid commit revision: not-a-commit' \
    "$invalid_history_revision_output" ||
    fail 'invalid history revision did not report its revision'

  new_history_fixture immutable-revision
  commit_history_file README.md safe
  immutable_safe_sha=$(fixture_git rev-parse HEAD)
  commit_history_file .superpowers/private.md private
  immutable_private_sha=$(fixture_git rev-parse HEAD)
  fixture_git branch moving-ref "$immutable_safe_sha"
  immutable_real_git=$(command -v git)
  case $immutable_real_git in
    /*)
      ;;
    *)
      fail 'immutable history real Git path is not absolute'
      ;;
  esac
  [ -x "$immutable_real_git" ] ||
    fail 'immutable history real Git path is not executable'
  immutable_git_dir=$tmp_dir/immutable-git-bin
  immutable_wrapper_count=$tmp_dir/immutable-git-wrapper.count
  immutable_wrapper_guard=$tmp_dir/immutable-git-wrapper.guard
  mkdir -p "$immutable_git_dir"
  # shellcheck disable=SC2016 # Variables belong to the generated wrapper.
  printf '%s\n' \
    '#!/bin/sh' \
    'set -eu' \
    'printf "invoke\n" >>"$TASK6_WRAPPER_COUNT"' \
    'guard_failure() {' \
    '  printf "%s\n" "$1" >>"$TASK6_WRAPPER_GUARD"' \
    '  printf "%s\n" "$1" >&2' \
    '  exit 70' \
    '}' \
    'case $TASK6_REAL_GIT in' \
    '  /*) ;;' \
    '  *) guard_failure "immutable history Git wrapper recursion guard: real Git path is not absolute" ;;' \
    'esac' \
    '[ -x "$TASK6_REAL_GIT" ] ||' \
    '  guard_failure "immutable history Git wrapper recursion guard: real Git is not executable"' \
    '[ "$TASK6_REAL_GIT" != "$0" ] ||' \
    '  guard_failure "immutable history Git wrapper recursion guard: real Git resolves to wrapper"' \
    'if [ "${TASK6_GIT_WRAPPER_ACTIVE:-0}" = 1 ]; then' \
    '  guard_failure "immutable history Git wrapper recursion detected"' \
    'fi' \
    'TASK6_GIT_WRAPPER_ACTIVE=1' \
    'export TASK6_GIT_WRAPPER_ACTIVE' \
    'if [ "$1" = rev-parse ]; then' \
    '  resolved=$("$TASK6_REAL_GIT" "$@")' \
    '  "$TASK6_REAL_GIT" branch -f moving-ref "$TASK6_PRIVATE_SHA" >/dev/null' \
    '  printf "%s\n" "$resolved"' \
    '  exit 0' \
    'fi' \
    'exec "$TASK6_REAL_GIT" "$@"' \
    >"$immutable_git_dir/git"
  chmod +x "$immutable_git_dir/git"
  immutable_restricted_bin=$tmp_dir/immutable-restricted-bin
  mkdir -p "$immutable_restricted_bin"
  for immutable_utility in mktemp rm ruby uname; do
    immutable_utility_path=$(command -v "$immutable_utility")
    case $immutable_utility_path in
      /*)
        ;;
      *)
        fail "immutable history utility path is not absolute: $immutable_utility"
        ;;
    esac
    [ -x "$immutable_utility_path" ] ||
      fail "immutable history utility is not executable: $immutable_utility"
    ln -s "$immutable_utility_path" \
      "$immutable_restricted_bin/$immutable_utility"
  done
  immutable_dash=$(command -v dash)
  case $immutable_dash in
    /*)
      ;;
    *)
      fail 'dash path is not absolute'
      ;;
  esac
  [ -x "$immutable_dash" ] || fail 'dash is not executable'
  immutable_validator_output=$tmp_dir/immutable-validator.out
  if ! (
    cd "$fixture_repo"
    PATH="$immutable_git_dir:$immutable_restricted_bin" \
      TASK6_REAL_GIT=$immutable_real_git \
      TASK6_PRIVATE_SHA=$immutable_private_sha \
      TASK6_WRAPPER_COUNT=$immutable_wrapper_count \
      TASK6_WRAPPER_GUARD=$immutable_wrapper_guard \
      "$immutable_dash" "$validator" moving-ref
  ) >"$immutable_validator_output" 2>&1; then
    if [ -s "$immutable_wrapper_guard" ]; then
      cat "$immutable_wrapper_guard" >&2
    fi
    cat "$immutable_validator_output" >&2
    fail 'immutable history fixture failed under dash with restricted PATH'
  fi
  immutable_wrapper_invocations=$(
    wc -l <"$immutable_wrapper_count" | tr -d '[:space:]'
  )
  [ "$immutable_wrapper_invocations" -eq 3 ] ||
    fail "immutable history Git wrapper invocation count changed: $immutable_wrapper_invocations"
  [ "$(fixture_git rev-parse moving-ref)" = "$immutable_private_sha" ] ||
    fail 'immutable history fixture did not move its reference'

  audit_git_dir=$tmp_dir/audit-git-bin
  mkdir -p "$audit_git_dir"
  # shellcheck disable=SC2016 # Positional parameter belongs to the wrapper.
  printf '%s\n' \
    '#!/bin/sh' \
    'case $1 in' \
    '  rev-parse)' \
    '    printf "%s\n" 1111111111111111111111111111111111111111' \
    '    ;;' \
    '  rev-list)' \
    '    printf "%s\n" "aaaaaaaa ./.superpowers/object.md" "bbbbbbbb ./.superpowers/shared.md"' \
    '    ;;' \
    '  log)' \
    '    printf "%s\0" "./docs/plans/log.md" "./.superpowers/shared.md"' \
    '    ;;' \
    '  *) exit 2 ;;' \
    'esac' \
    >"$audit_git_dir/git"
  chmod +x "$audit_git_dir/git"
  run_synthetic_history_validator() {
    (
      cd "$fixture_repo"
      PATH="$audit_git_dir:$PATH" "$validator" HEAD
    )
  }
  synthetic_history_output=$tmp_dir/synthetic-history.out
  capture_failure "$synthetic_history_output" \
    run_synthetic_history_validator ||
    fail 'synthetic history paths were accepted'
  for synthetic_diagnostic in \
    'private history path: .superpowers/object.md' \
    'private history path: .superpowers/shared.md' \
    'private history path: docs/plans/log.md'; do
    grep -Fqx "$synthetic_diagnostic" "$synthetic_history_output" ||
      fail "synthetic history omitted: $synthetic_diagnostic"
    [ "$(grep -Fxc "$synthetic_diagnostic" "$synthetic_history_output")" -eq 1 ] ||
      fail "synthetic history repeated: $synthetic_diagnostic"
  done

  new_history_fixture quoted-private-paths
  unicode_private_path=.superpowers/秘密.md
  newline_private_path='docs/superpowers/line
break.md'
  commit_history_file "$unicode_private_path" private
  commit_history_file "$newline_private_path" private
  fixture_git rm --quiet "$unicode_private_path" "$newline_private_path"
  fixture_git commit --quiet -m 'Delete quoted private paths'
  quoted_private_output=$tmp_dir/quoted-private-paths.out
  capture_failure "$quoted_private_output" \
    run_history_validator HEAD ||
    fail 'C-quoted private history paths were accepted'
  for quoted_private_diagnostic in \
    'private history path: .superpowers/秘密.md' \
    'private history path: docs/superpowers/line\nbreak.md'; do
    grep -Fqx "$quoted_private_diagnostic" "$quoted_private_output" ||
      fail "quoted private history omitted: $quoted_private_diagnostic"
    [ "$(grep -Fxc "$quoted_private_diagnostic" "$quoted_private_output")" -eq 1 ] ||
      fail "quoted private history repeated: $quoted_private_diagnostic"
  done
  [ "$(wc -l <"$quoted_private_output" | tr -d '[:space:]')" -eq 2 ] ||
    fail 'quoted private history emitted a raw newline from a path'
  quoted_private_sanitized=$tmp_dir/quoted-private-paths-sanitized.out
  LC_ALL=C tr -d '\000-\011\013-\037\177' \
    <"$quoted_private_output" >"$quoted_private_sanitized"
  cmp -s "$quoted_private_output" "$quoted_private_sanitized" ||
    fail 'quoted private history diagnostic contains raw control characters'

  new_history_fixture injective-diagnostics
  invalid_path_byte=$(printf '\377')
  invalid_byte_path=".superpowers/raw-$invalid_path_byte.md"
  literal_escape_path='.superpowers/raw-\xFF.md'
  diagnostic_blob=$(printf '%s\n' private | fixture_git hash-object -w --stdin)
  {
    printf '100644 %s\t%s\0' "$diagnostic_blob" "$invalid_byte_path"
    printf '100644 %s\t%s\0' "$diagnostic_blob" "$literal_escape_path"
  } | fixture_git update-index -z --index-info
  fixture_git commit --quiet -m 'Add byte-distinct private paths'
  fixture_git read-tree --empty
  fixture_git commit --quiet -m 'Delete byte-distinct private paths'
  injective_diagnostics_output=$tmp_dir/injective-diagnostics.out
  capture_failure "$injective_diagnostics_output" \
    run_history_validator HEAD ||
    fail 'byte-distinct private history paths were accepted'
  for injective_diagnostic in \
    'private history path: .superpowers/raw-\xFF.md' \
    'private history path: .superpowers/raw-\\xFF.md'; do
    grep -Fqx "$injective_diagnostic" "$injective_diagnostics_output" ||
      fail "byte-distinct history omitted: $injective_diagnostic"
    [ "$(grep -Fxc "$injective_diagnostic" "$injective_diagnostics_output")" -eq 1 ] ||
      fail "byte-distinct history repeated: $injective_diagnostic"
  done
  [ "$(wc -l <"$injective_diagnostics_output" | tr -d '[:space:]')" -eq 2 ] ||
    fail 'byte-distinct private paths did not produce distinct diagnostics'
  injective_diagnostics_sanitized=$tmp_dir/injective-diagnostics-sanitized.out
  LC_ALL=C tr -d '\000-\011\013-\037\177' \
    <"$injective_diagnostics_output" >"$injective_diagnostics_sanitized"
  cmp -s "$injective_diagnostics_output" \
    "$injective_diagnostics_sanitized" ||
    fail 'byte-distinct history diagnostic contains raw control characters'

  new_history_fixture deleted-superpowers
  commit_history_file .superpowers/spec.md private
  fixture_git rm --quiet .superpowers/spec.md
  fixture_git commit --quiet -m 'Delete private specification'
  deleted_superpowers_output=$tmp_dir/deleted-superpowers.out
  capture_failure "$deleted_superpowers_output" \
    run_history_validator HEAD ||
    fail 'deleted .superpowers history was accepted'
  grep -Fqx 'private history path: .superpowers/spec.md' \
    "$deleted_superpowers_output" ||
    fail 'deleted .superpowers history did not report its path'
  [ "$(grep -Fxc 'private history path: .superpowers/spec.md' \
    "$deleted_superpowers_output")" -eq 1 ] ||
    fail 'deleted .superpowers history path was reported more than once'

  new_history_fixture deleted-docs-superpowers
  commit_history_file docs/superpowers/notes.md private
  fixture_git rm --quiet docs/superpowers/notes.md
  fixture_git commit --quiet -m 'Delete private notes'
  deleted_docs_superpowers_output=$tmp_dir/deleted-docs-superpowers.out
  capture_failure "$deleted_docs_superpowers_output" \
    run_history_validator HEAD ||
    fail 'deleted docs/superpowers history was accepted'
  grep -Fqx 'private history path: docs/superpowers/notes.md' \
    "$deleted_docs_superpowers_output" ||
    fail 'deleted docs/superpowers history did not report its path'

  new_history_fixture deleted-docs-plans
  commit_history_file docs/plans/roadmap.md private
  fixture_git rm --quiet docs/plans/roadmap.md
  fixture_git commit --quiet -m 'Delete private plan'
  deleted_docs_plans_output=$tmp_dir/deleted-docs-plans.out
  capture_failure "$deleted_docs_plans_output" \
    run_history_validator HEAD ||
    fail 'deleted docs/plans history was accepted'
  grep -Fqx 'private history path: docs/plans/roadmap.md' \
    "$deleted_docs_plans_output" ||
    fail 'deleted docs/plans history did not report its path'

  printf 'policy fixtures (history): ok\n'
}

test_workflow() {
  validator=$script_dir/check-workflow-policy.rb
  installer=$script_dir/install-policy-tools.sh
  workflow_root=$tmp_dir/workflow-fixture
  workflow_dir=$workflow_root/.github/workflows
  mkdir -p "$workflow_dir"
  git -C "$workflow_root" \
    -c core.hooksPath=/dev/null \
    -c commit.gpgsign=false \
    init --quiet --template="$tmp_dir/empty-template"

  workflow_tool_dir=$tmp_dir/workflow-policy-tools
  if ! actionlint=$("$installer" install "$workflow_tool_dir" actionlint); then
    fail 'could not install the approved actionlint release'
  fi
  [ "$actionlint" = "$workflow_tool_dir/bin/actionlint" ] ||
    fail 'actionlint installer returned an unexpected executable path'
  [ -x "$actionlint" ] ||
    fail 'actionlint installer did not create an executable'
  successful_actionlint_stub=$tmp_dir/successful-actionlint
  printf '%s\n' '#!/bin/sh' 'exit 0' >"$successful_actionlint_stub"
  chmod +x "$successful_actionlint_stub"

  reset_workflow_fixture() {
    # shellcheck disable=SC2016 # GitHub expressions must remain literal.
    printf '%s\n' \
      'name: Repository policy
on:
  pull_request:
  push:
permissions:
  contents: read
concurrency:
  group: required-policy-${{ github.ref }}
  cancel-in-progress: true
jobs:
  repository-policy:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa
      - run: |
          git cat-file -e "${HEAD_SHA}^{commit}"
          git cat-file -e "${TREE_SHA}^{commit}"
          git cat-file -e "${BASE_SHA}^{commit}"
          scripts/test-repository-policy.sh dco' \
      >"$workflow_dir/repository-policy.yml"
    # shellcheck disable=SC2016 # GitHub expressions must remain literal.
    printf '%s\n' \
      'name: External links
on:
  schedule:
    - cron: "17 3 * * 1"
permissions:
  contents: read
concurrency:
  group: external-links-${{ github.ref }}
  cancel-in-progress: true
jobs:
  external-links:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb
      - run: scripts/test-repository-policy.sh links' \
      >"$workflow_dir/external-links.yml"
  }

  run_workflow_validator() {
    "$validator" --root "$workflow_root" --actionlint "$actionlint"
  }

  assert_workflow_rejected() {
    fixture_name=$1
    expected_diagnostic=$2
    fixture_output=$tmp_dir/workflow-$fixture_name.out
    capture_failure "$fixture_output" run_workflow_validator ||
      fail "$fixture_name workflow fixture was accepted"
    grep -Fqx "$expected_diagnostic" "$fixture_output" ||
      fail "$fixture_name did not report: $expected_diagnostic"
  }

  assert_workflow_policy_rejected() {
    fixture_name=$1
    expected_diagnostic=$2
    fixture_output=$tmp_dir/workflow-$fixture_name.out
    capture_failure "$fixture_output" \
      "$validator" --root "$workflow_root" \
      --actionlint "$successful_actionlint_stub" ||
      fail "$fixture_name workflow fixture was accepted"
    grep -Fqx "$expected_diagnostic" "$fixture_output" ||
      fail "$fixture_name did not report: $expected_diagnostic"
  }

  add_token_environment() {
    token_expression=$1
    awk -v token_expression="$token_expression" '
      /^concurrency:$/ {
        print "env:"
        print "  GH_TOKEN: " token_expression
      }
      { print }
    ' "$workflow_dir/repository-policy.yml" \
      >"$tmp_dir/token-environment.yml"
    mv "$tmp_dir/token-environment.yml" \
      "$workflow_dir/repository-policy.yml"
  }

  add_shell_token_reference() {
    token_expression=$1
    awk -v token_expression="$token_expression" '
      /          scripts\/test-repository-policy[.]sh dco/ {
        print "          echo \"token=" token_expression "\""
        next
      }
      { print }
    ' "$workflow_dir/repository-policy.yml" \
      >"$tmp_dir/shell-token-reference.yml"
    mv "$tmp_dir/shell-token-reference.yml" \
      "$workflow_dir/repository-policy.yml"
  }

  assert_token_reference_rejected() {
    token_variant=$1
    token_expression=$2

    reset_workflow_fixture
    add_token_environment "$token_expression"
    assert_workflow_rejected "token-env-$token_variant" \
      '.github/workflows/repository-policy.yml: GitHub token must not be written to an environment variable'

    reset_workflow_fixture
    add_shell_token_reference "$token_expression"
    assert_workflow_rejected "token-run-$token_variant" \
      '.github/workflows/repository-policy.yml: GitHub token references are not allowed in shell run commands'
  }

  assert_token_reference_rejected_after_actionlint() {
    token_variant=$1
    token_expression=$2

    reset_workflow_fixture
    add_token_environment "$token_expression"
    assert_workflow_policy_rejected "token-env-$token_variant" \
      '.github/workflows/repository-policy.yml: GitHub token must not be written to an environment variable'

    reset_workflow_fixture
    add_shell_token_reference "$token_expression"
    assert_workflow_policy_rejected "token-run-$token_variant" \
      '.github/workflows/repository-policy.yml: GitHub token references are not allowed in shell run commands'
  }

  assert_double_quote_token_rejected_by_actionlint() {
    token_variant=$1
    token_expression=$2

    reset_workflow_fixture
    add_token_environment "$token_expression"
    token_actionlint_output=$tmp_dir/workflow-token-actionlint-env-$token_variant.out
    capture_failure "$token_actionlint_output" run_workflow_validator ||
      fail "token-env-$token_variant bypassed actionlint"
    grep -Eq '\[expression\]' "$token_actionlint_output" ||
      fail "token-env-$token_variant did not fail through actionlint"
    grep -Fq 'only single quotes are available' "$token_actionlint_output" ||
      fail "token-env-$token_variant actionlint diagnostic changed"

    reset_workflow_fixture
    add_shell_token_reference "$token_expression"
    token_actionlint_output=$tmp_dir/workflow-token-actionlint-run-$token_variant.out
    capture_failure "$token_actionlint_output" run_workflow_validator ||
      fail "token-run-$token_variant bypassed actionlint"
    grep -Eq '\[expression\]' "$token_actionlint_output" ||
      fail "token-run-$token_variant did not fail through actionlint"
    grep -Fq 'only single quotes are available' "$token_actionlint_output" ||
      fail "token-run-$token_variant actionlint diagnostic changed"
  }

  reset_workflow_fixture
  run_workflow_validator ||
    fail 'approved workflow fixture was rejected'

  for guard_name in head tree base; do
    case $guard_name in
      head)
        guard="git cat-file -e \"\${HEAD_SHA}^{commit}\""
        ;;
      tree)
        guard="git cat-file -e \"\${TREE_SHA}^{commit}\""
        ;;
      base)
        guard="git cat-file -e \"\${BASE_SHA}^{commit}\""
        ;;
    esac
    reset_workflow_fixture
    grep -Fv "$guard" \
      "$workflow_dir/repository-policy.yml" \
      >"$tmp_dir/missing-$guard_name-guard.yml"
    mv "$tmp_dir/missing-$guard_name-guard.yml" \
      "$workflow_dir/repository-policy.yml"
    assert_workflow_rejected "missing-$guard_name-guard" \
      ".github/workflows/repository-policy.yml: missing required guard: $guard"
  done

  reset_workflow_fixture
  sed \
    -e 's/${{ github.ref }}/${{ github.ref + }}/' \
    -e 's/contents: read/contents: write/' \
    "$workflow_dir/repository-policy.yml" \
    >"$tmp_dir/invalid-expression.yml"
  mv "$tmp_dir/invalid-expression.yml" \
    "$workflow_dir/repository-policy.yml"
  invalid_expression_output=$tmp_dir/workflow-invalid-expression.out
  capture_failure "$invalid_expression_output" run_workflow_validator ||
    fail 'invalid GitHub expression was accepted'
  grep -Eq '\[expression\]' "$invalid_expression_output" ||
    fail 'invalid GitHub expression did not fail through actionlint'

  reset_workflow_fixture
  cp "$workflow_dir/repository-policy.yml" \
    "$workflow_dir/a-duplicate-repository-policy.yml"
  sed \
    -e 's/group: required-policy-/group: escaped-policy-/' \
    -e 's/^  repository-policy:/  escaped-policy:/' \
    -e '/^on:$/a\
  schedule:\
    - cron: "7 1 * * *"' \
    "$workflow_dir/a-duplicate-repository-policy.yml" \
    >"$tmp_dir/a-duplicate-repository-policy.yml"
  mv "$tmp_dir/a-duplicate-repository-policy.yml" \
    "$workflow_dir/a-duplicate-repository-policy.yml"
  assert_workflow_rejected duplicate-role-first \
    'duplicate workflow name: Repository policy: .github/workflows/a-duplicate-repository-policy.yml, .github/workflows/repository-policy.yml'
  rm -f "$workflow_dir/a-duplicate-repository-policy.yml"

  reset_workflow_fixture
  cp "$workflow_dir/repository-policy.yml" \
    "$workflow_dir/z-duplicate-repository-policy.yml"
  sed \
    -e 's/group: required-policy-/group: escaped-policy-/' \
    -e 's/^  repository-policy:/  escaped-policy:/' \
    -e '/^on:$/a\
  schedule:\
    - cron: "7 1 * * *"' \
    "$workflow_dir/repository-policy.yml" \
    >"$tmp_dir/repository-policy-escaped.yml"
  mv "$tmp_dir/repository-policy-escaped.yml" \
    "$workflow_dir/repository-policy.yml"
  assert_workflow_rejected duplicate-role-last \
    'duplicate workflow name: Repository policy: .github/workflows/repository-policy.yml, .github/workflows/z-duplicate-repository-policy.yml'
  rm -f "$workflow_dir/z-duplicate-repository-policy.yml"

  reset_workflow_fixture
  sed 's/contents: read/contents: write/' \
    "$workflow_dir/repository-policy.yml" \
    >"$tmp_dir/write-permission.yml"
  mv "$tmp_dir/write-permission.yml" \
    "$workflow_dir/repository-policy.yml"
  assert_workflow_rejected write-permission \
    '.github/workflows/repository-policy.yml: top-level permissions must be exactly contents: read'

  reset_workflow_fixture
  sed 's#actions/checkout@aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa#actions/checkout@v4#' \
    "$workflow_dir/repository-policy.yml" \
    >"$tmp_dir/tagged-use.yml"
  mv "$tmp_dir/tagged-use.yml" \
    "$workflow_dir/repository-policy.yml"
  assert_workflow_rejected tagged-use \
    '.github/workflows/repository-policy.yml: unpinned uses: actions/checkout@v4'

  reset_workflow_fixture
  sed 's#actions/checkout@aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa#actions/checkout@abcdef0#' \
    "$workflow_dir/repository-policy.yml" \
    >"$tmp_dir/short-sha-use.yml"
  mv "$tmp_dir/short-sha-use.yml" \
    "$workflow_dir/repository-policy.yml"
  assert_workflow_rejected short-sha-use \
    '.github/workflows/repository-policy.yml: unpinned uses: actions/checkout@abcdef0'

  reset_workflow_fixture
  sed 's/name: Repository policy/name: Repository checks/' \
    "$workflow_dir/repository-policy.yml" \
    >"$tmp_dir/missing-workflow-name.yml"
  mv "$tmp_dir/missing-workflow-name.yml" \
    "$workflow_dir/repository-policy.yml"
  assert_workflow_rejected missing-workflow-name \
    'missing workflow name: Repository policy'

  reset_workflow_fixture
  sed 's/^  repository-policy:/  policy:/' \
    "$workflow_dir/repository-policy.yml" \
    >"$tmp_dir/missing-job-name.yml"
  mv "$tmp_dir/missing-job-name.yml" \
    "$workflow_dir/repository-policy.yml"
  assert_workflow_rejected missing-job-name \
    '.github/workflows/repository-policy.yml: missing job: repository-policy'

  reset_workflow_fixture
  sed '/    runs-on: ubuntu-latest/a\
    permissions:\
      contents: read' \
    "$workflow_dir/repository-policy.yml" \
    >"$tmp_dir/job-permissions.yml"
  mv "$tmp_dir/job-permissions.yml" \
    "$workflow_dir/repository-policy.yml"
  assert_workflow_rejected job-permissions \
    '.github/workflows/repository-policy.yml: job repository-policy must not define permissions'

  reset_workflow_fixture
  sed 's/group: required-policy-/group: repository-policy-/' \
    "$workflow_dir/repository-policy.yml" \
    >"$tmp_dir/required-concurrency.yml"
  mv "$tmp_dir/required-concurrency.yml" \
    "$workflow_dir/repository-policy.yml"
  assert_workflow_rejected required-concurrency \
    '.github/workflows/repository-policy.yml: concurrency group must start with required-policy-'

  reset_workflow_fixture
  sed 's/group: external-links-/group: links-/' \
    "$workflow_dir/external-links.yml" \
    >"$tmp_dir/external-concurrency.yml"
  mv "$tmp_dir/external-concurrency.yml" \
    "$workflow_dir/external-links.yml"
  assert_workflow_rejected external-concurrency \
    '.github/workflows/external-links.yml: concurrency group must start with external-links-'

  reset_workflow_fixture
  sed '/^on:$/a\
  schedule:\
    - cron: "11 2 * * *"' \
    "$workflow_dir/repository-policy.yml" \
    >"$tmp_dir/required-schedule.yml"
  mv "$tmp_dir/required-schedule.yml" \
    "$workflow_dir/repository-policy.yml"
  assert_workflow_rejected required-schedule \
    '.github/workflows/repository-policy.yml: Repository policy must not run on schedule'

  reset_workflow_fixture
  sed '/^on:$/a\
  pull_request:' \
    "$workflow_dir/external-links.yml" \
    >"$tmp_dir/external-pull-request.yml"
  mv "$tmp_dir/external-pull-request.yml" \
    "$workflow_dir/external-links.yml"
  assert_workflow_rejected external-pull-request \
    '.github/workflows/external-links.yml: External links must not run on pull_request'

  reset_workflow_fixture
  sed '/^on:$/a\
  push:' \
    "$workflow_dir/external-links.yml" \
    >"$tmp_dir/external-push.yml"
  mv "$tmp_dir/external-push.yml" \
    "$workflow_dir/external-links.yml"
  assert_workflow_rejected external-push \
    '.github/workflows/external-links.yml: External links must not run on push'

  reset_workflow_fixture
  sed '/^on:$/a\
  pull_request_target:' \
    "$workflow_dir/repository-policy.yml" \
    >"$tmp_dir/pull-request-target.yml"
  mv "$tmp_dir/pull-request-target.yml" \
    "$workflow_dir/repository-policy.yml"
  assert_workflow_rejected pull-request-target \
    '.github/workflows/repository-policy.yml: pull_request_target is not allowed'

  assert_token_reference_rejected exact-github \
    "\${{ github.token }}"
  assert_token_reference_rejected spaced-cased-github \
    "\${{ GitHub . Token }}"
  assert_token_reference_rejected single-bracket-github \
    "\${{ github [ 'token' ] }}"
  assert_double_quote_token_rejected_by_actionlint double-bracket-github \
    "\${{ github [ \"TOKEN\" ] }}"
  assert_token_reference_rejected_after_actionlint double-bracket-github \
    "\${{ github [ \"TOKEN\" ] }}"
  assert_token_reference_rejected exact-secrets \
    "\${{ secrets.GITHUB_TOKEN }}"
  assert_token_reference_rejected spaced-cased-secrets \
    "\${{ Secrets . GitHub_Token }}"
  assert_token_reference_rejected single-bracket-secrets \
    "\${{ secrets [ 'GITHUB_TOKEN' ] }}"
  assert_double_quote_token_rejected_by_actionlint double-bracket-secrets \
    "\${{ secrets [ \"github_token\" ] }}"
  assert_token_reference_rejected_after_actionlint double-bracket-secrets \
    "\${{ secrets [ \"github_token\" ] }}"
  assert_token_reference_rejected wrapped-github \
    "\${{ format('{0}', github.token) }}"
  assert_token_reference_rejected wrapped-secrets \
    "\${{ format('{0}', secrets['GITHUB_TOKEN']) }}"
  assert_token_reference_rejected delimiter-in-string \
    "\${{ format('}}{0}', github.token) }}"
  assert_token_reference_rejected doubled-quote-string \
    "\${{ format('it''s }} {0}', secrets.GITHUB_TOKEN) }}"
  assert_token_reference_rejected computed-github-index \
    "\${{ github[format('{0}', 'token')] }}"
  assert_token_reference_rejected computed-secrets-index \
    "\${{ secrets[format('{0}_{1}', 'GITHUB', 'TOKEN')] }}"

  reset_workflow_fixture
  add_token_environment "\${{ github['sha'] }}"
  run_workflow_validator ||
    fail 'static non-token environment index was rejected'

  reset_workflow_fixture
  add_shell_token_reference "\${{ secrets['NOT_GITHUB_TOKEN'] }}"
  run_workflow_validator ||
    fail 'static non-token shell index was rejected'

  reset_workflow_fixture
  sed '/^concurrency:$/i\
env:\
  GH_TOKEN: ${{ github.token }}' \
    "$workflow_dir/repository-policy.yml" \
    >"$tmp_dir/token-environment.yml"
  mv "$tmp_dir/token-environment.yml" \
    "$workflow_dir/repository-policy.yml"
  assert_workflow_rejected token-environment \
    '.github/workflows/repository-policy.yml: GitHub token must not be written to an environment variable'

  reset_workflow_fixture
  sed '/          scripts\/test-repository-policy.sh dco/c\
          curl --fail --location https://example.com/policy-tool --output "$RUNNER_TEMP/policy-tool"\
          chmod +x "$RUNNER_TEMP/policy-tool"\
          "$RUNNER_TEMP/policy-tool" --token "${{ github.token }}"' \
    "$workflow_dir/repository-policy.yml" \
    >"$tmp_dir/downloaded-token.yml"
  mv "$tmp_dir/downloaded-token.yml" \
    "$workflow_dir/repository-policy.yml"
  assert_workflow_rejected downloaded-token \
    '.github/workflows/repository-policy.yml: GitHub token references are not allowed in shell run commands'

  printf 'policy fixtures (workflow): ok\n'
}

test_orchestration() {
  orchestrator=$script_dir/check-repository-policy.sh
  fixture_root=$tmp_dir/orchestration-baseline
  fixture_scripts=$fixture_root/scripts
  mkdir -p "$fixture_scripts"
  git -C "$fixture_root" \
    -c core.hooksPath=/dev/null \
    -c commit.gpgsign=false \
    init --quiet --template="$tmp_dir/empty-template"
  git -C "$fixture_root" config user.name 'Fixture User'
  git -C "$fixture_root" config user.email 'fixture@example.com'

  printf '%s\n' '# Baseline fixture' >"$fixture_root/README.md"
  git -C "$fixture_root" add README.md
  git -C "$fixture_root" commit --quiet \
    -m 'Baseline fixture' \
    -m 'Signed-off-by: Fixture User <fixture@example.com>'

  # shellcheck disable=SC2016 # Stub source expands in the fixture process.
  printf '%s\n' \
    '#!/bin/sh' \
    'set -eu' \
    'exit 0' \
    >"$fixture_scripts/test-repository-policy.sh"
  # shellcheck disable=SC2016 # Stub source expands in the fixture process.
  printf '%s\n' \
    '#!/bin/sh' \
    'set -eu' \
    'printf "baseline fixture failure\n" >&2' \
    'exit 1' \
    >"$fixture_scripts/check-repository-baseline.sh"
  for fixture_script in \
    check-dco.sh \
    check-markdown-links.sh \
    check-community-yaml.rb \
    check-workflow-policy.rb \
    check-private-history.sh
  do
    printf '%s\n' \
      '#!/bin/sh' \
      'set -eu' \
      'exit 0' \
      >"$fixture_scripts/$fixture_script"
  done
  chmod +x "$fixture_scripts"/*

  lychee_stub=$tmp_dir/orchestration-lychee
  actionlint_stub=$tmp_dir/orchestration-actionlint
  printf '%s\n' '#!/bin/sh' 'exit 0' >"$lychee_stub"
  printf '%s\n' '#!/bin/sh' 'exit 0' >"$actionlint_stub"
  chmod +x "$lychee_stub" "$actionlint_stub"

  fixture_output=$tmp_dir/orchestration-baseline.out
  if [ -f "$orchestrator" ]; then
    cp "$orchestrator" "$fixture_scripts/check-repository-policy.sh"
    chmod +x "$fixture_scripts/check-repository-policy.sh"
  fi
  run_baseline_fixture() {
    (
      cd "$fixture_root"
      LYCHEE_BIN=$lychee_stub ACTIONLINT_BIN=$actionlint_stub \
        "$fixture_scripts/check-repository-policy.sh" \
        --all HEAD --tree HEAD
    )
  }
  capture_failure "$fixture_output" run_baseline_fixture ||
    fail 'deliberately failing baseline fixture was accepted'
  grep -Fqx 'baseline fixture failure' "$fixture_output" ||
    fail 'orchestrator did not reach the deliberately failing baseline'

  valid_root=$tmp_dir/orchestration-valid
  valid_scripts=$valid_root/scripts
  orchestration_log=$tmp_dir/orchestration-valid.log
  mkdir -p "$valid_scripts"
  valid_root=$(CDPATH='' cd -- "$valid_root" && pwd -P)
  valid_scripts=$valid_root/scripts
  cp "$orchestrator" "$valid_scripts/check-repository-policy.sh"
  chmod +x "$valid_scripts/check-repository-policy.sh"

  # shellcheck disable=SC2016 # Stub source expands in the fixture process.
  printf '%s\n' \
    '#!/bin/sh' \
    'set -eu' \
    '[ "$#" -eq 1 ]' \
    'printf "fixture:%s\n" "$1" >>"$ORCHESTRATION_LOG"' \
    >"$valid_scripts/test-repository-policy.sh"
  # shellcheck disable=SC2016 # Stub source expands in the fixture process.
  printf '%s\n' \
    '#!/bin/sh' \
    'set -eu' \
    '[ "$#" -eq 0 ]' \
    'printf "baseline\n" >>"$ORCHESTRATION_LOG"' \
    >"$valid_scripts/check-repository-baseline.sh"
  # shellcheck disable=SC2016 # Stub source expands in the fixture process.
  printf '%s\n' \
    '#!/bin/sh' \
    'set -eu' \
    'printf "dco:%s\n" "$*" >>"$ORCHESTRATION_LOG"' \
    >"$valid_scripts/check-dco.sh"
  # shellcheck disable=SC2016 # Stub source expands in the fixture process.
  printf '%s\n' \
    '#!/bin/sh' \
    'set -eu' \
    'printf "links:%s\n" "$*" >>"$ORCHESTRATION_LOG"' \
    >"$valid_scripts/check-markdown-links.sh"
  # shellcheck disable=SC2016 # Stub source expands in the fixture process.
  printf '%s\n' \
    '#!/bin/sh' \
    'set -eu' \
    'printf "yaml:%s\n" "$*" >>"$ORCHESTRATION_LOG"' \
    >"$valid_scripts/check-community-yaml.rb"
  printf '%s\n' \
    '#!/usr/bin/env ruby' \
    'File.open(ENV.fetch("ORCHESTRATION_LOG"), "a") do |output|' \
    '  output.puts("workflow:#{ARGV.join(" ")}")' \
    'end' \
    >"$valid_scripts/check-workflow-policy.rb"
  # shellcheck disable=SC2016 # Stub source expands in the fixture process.
  printf '%s\n' \
    '#!/bin/sh' \
    'set -eu' \
    'printf "history:%s\n" "$*" >>"$ORCHESTRATION_LOG"' \
    >"$valid_scripts/check-private-history.sh"
  # shellcheck disable=SC2016 # Stub source expands in the fixture process.
  printf '%s\n' \
    '#!/bin/sh' \
    'set -eu' \
    '[ "$#" -eq 3 ]' \
    '[ "$1" = install ]' \
    'mkdir -p "$2/bin"' \
    'printf "%s\n" "#!/bin/sh" "exit 0" >"$2/bin/$3"' \
    'chmod +x "$2/bin/$3"' \
    'printf "install:%s:%s\n" "$2" "$3" >>"$INSTALL_LOG"' \
    'printf "%s/bin/%s\n" "$2" "$3"' \
    >"$valid_scripts/install-policy-tools.sh"
  chmod +x "$valid_scripts"/*

  run_valid_fixture() {
    (
      cd "$valid_root"
      ORCHESTRATION_LOG=$orchestration_log \
        LYCHEE_BIN=$lychee_stub \
        ACTIONLINT_BIN=$actionlint_stub \
        "$valid_scripts/check-repository-policy.sh" "$@"
    )
  }

  : >"$orchestration_log"
  all_output=$tmp_dir/orchestration-valid-all.out
  run_valid_fixture --all ALL_HEAD --tree ALL_TREE >"$all_output" 2>&1 ||
    fail 'valid --all orchestration fixture was rejected'
  grep -Fqx 'repository policy: ok' "$all_output" ||
    fail 'valid --all orchestration did not report repository policy: ok'
  printf '%s\n' \
    'fixture:tools' \
    'fixture:dco' \
    'fixture:history' \
    'fixture:links' \
    'fixture:workflow' \
    'fixture:external' \
    'fixture:baseline' \
    'fixture:orchestration' \
    'fixture:yaml' \
    'baseline' \
    'dco:--all ALL_HEAD' \
    "links:--revision ALL_TREE --lychee $lychee_stub" \
    "yaml:$valid_root" \
    "workflow:--root $valid_root --actionlint $actionlint_stub" \
    'history:ALL_TREE' \
    >"$tmp_dir/orchestration-valid-all.expected"
  if ! cmp -s \
    "$tmp_dir/orchestration-valid-all.expected" "$orchestration_log"; then
    diff -u \
      "$tmp_dir/orchestration-valid-all.expected" \
      "$orchestration_log" >&2 || true
    fail 'valid --all orchestration checks or arguments were out of order'
  fi

  : >"$orchestration_log"
  range_output=$tmp_dir/orchestration-valid-range.out
  run_valid_fixture \
    --range RANGE_BASE RANGE_HEAD --tree RANGE_TREE \
    >"$range_output" 2>&1 ||
    fail 'valid --range orchestration fixture was rejected'
  grep -Fqx 'repository policy: ok' "$range_output" ||
    fail 'valid --range orchestration did not report repository policy: ok'
  printf '%s\n' \
    'fixture:tools' \
    'fixture:dco' \
    'fixture:history' \
    'fixture:links' \
    'fixture:workflow' \
    'fixture:external' \
    'fixture:baseline' \
    'fixture:orchestration' \
    'fixture:yaml' \
    'baseline' \
    'dco:--range RANGE_BASE RANGE_HEAD' \
    "links:--revision RANGE_TREE --lychee $lychee_stub" \
    "yaml:$valid_root" \
    "workflow:--root $valid_root --actionlint $actionlint_stub" \
    'history:RANGE_TREE' \
    >"$tmp_dir/orchestration-valid-range.expected"
  if ! cmp -s \
    "$tmp_dir/orchestration-valid-range.expected" "$orchestration_log"; then
    diff -u \
      "$tmp_dir/orchestration-valid-range.expected" \
      "$orchestration_log" >&2 || true
    fail 'valid --range orchestration checks or arguments were out of order'
  fi

  local_tool_parent=$tmp_dir/orchestration-local-tools
  local_install_log=$tmp_dir/orchestration-local-install.log
  mkdir -p "$local_tool_parent"
  : >"$orchestration_log"
  : >"$local_install_log"
  (
    cd "$valid_root"
    unset LYCHEE_BIN ACTIONLINT_BIN GITHUB_ACTIONS RUNNER_TEMP
    TMPDIR=$local_tool_parent \
      INSTALL_LOG=$local_install_log \
      ORCHESTRATION_LOG=$orchestration_log \
      "$valid_scripts/check-repository-policy.sh" \
      --all LOCAL_HEAD --tree LOCAL_TREE
  ) >"$tmp_dir/orchestration-local-tools.out" 2>&1 ||
    fail 'local orchestration tool installation was rejected'
  local_tool_dir=$(
    sed -n 's/^install:\(.*\):lychee$/\1/p' "$local_install_log"
  )
  case $local_tool_dir in
    "$local_tool_parent"/engrammesh-policy-tools.*)
      ;;
    *)
      fail 'local orchestration did not use a fresh mktemp tool directory'
      ;;
  esac
  [ ! -e "$local_tool_dir" ] ||
    fail 'local orchestration retained its temporary tool directory'
  printf '%s\n' \
    "install:$local_tool_dir:lychee" \
    "install:$local_tool_dir:actionlint" \
    >"$tmp_dir/orchestration-local-install.expected"
  cmp -s \
    "$tmp_dir/orchestration-local-install.expected" \
    "$local_install_log" ||
    fail 'local orchestration tool installation order changed'

  runner_temp=$tmp_dir/orchestration-runner
  runner_install_log=$tmp_dir/orchestration-runner-install.log
  mkdir -p "$runner_temp"
  : >"$orchestration_log"
  : >"$runner_install_log"
  (
    cd "$valid_root"
    unset LYCHEE_BIN ACTIONLINT_BIN
    GITHUB_ACTIONS=true \
      RUNNER_TEMP=$runner_temp \
      INSTALL_LOG=$runner_install_log \
      ORCHESTRATION_LOG=$orchestration_log \
      "$valid_scripts/check-repository-policy.sh" \
      --all RUNNER_HEAD --tree RUNNER_TREE
  ) >"$tmp_dir/orchestration-runner-tools.out" 2>&1 ||
    fail 'Actions orchestration tool installation was rejected'
  printf '%s\n' \
    "install:$runner_temp/policy-tools:lychee" \
    "install:$runner_temp/policy-tools:actionlint" \
    >"$tmp_dir/orchestration-runner-install.expected"
  cmp -s \
    "$tmp_dir/orchestration-runner-install.expected" \
    "$runner_install_log" ||
    fail 'Actions orchestration did not use RUNNER_TEMP/policy-tools'
  [ -x "$runner_temp/policy-tools/bin/lychee" ] ||
    fail 'Actions orchestration did not install Lychee'
  [ -x "$runner_temp/policy-tools/bin/actionlint" ] ||
    fail 'Actions orchestration did not install actionlint'

  printf 'policy fixtures (orchestration): ok\n'
}

test_external_workflow() {
  workflow_path=$repository_root/.github/workflows/external-links.yml
  [ -s "$workflow_path" ] ||
    fail 'external-links workflow is missing or empty'

  ruby - "$workflow_path" <<'RUBY'
require "yaml"

path = ARGV.fetch(0)
workflow = YAML.safe_load(
  File.read(path),
  permitted_classes: [],
  permitted_symbols: [],
  aliases: false
)

events = workflow.fetch("on")
unless events.keys.sort == %w[schedule workflow_dispatch] &&
       events.fetch("schedule") == [{ "cron" => "17 3 * * 1" }] &&
       events.fetch("workflow_dispatch").nil?
  abort "external-links workflow events are not weekly/manual only"
end

unless workflow["permissions"] == { "contents" => "read" }
  abort "external-links workflow permissions changed"
end
unless workflow["concurrency"] == {
  "group" => "external-links-${{ github.ref }}",
  "cancel-in-progress" => true
}
  abort "external-links workflow concurrency changed"
end

job = workflow.fetch("jobs").fetch("external-links")
unless job["name"] == "external-links" && job["runs-on"] == "ubuntu-24.04"
  abort "external-links job identity changed"
end
steps = job.fetch("steps")
checkout = steps.find { |step| step["name"] == "Check out repository" }
unless checkout &&
       checkout["uses"] ==
         "actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1" &&
       checkout["with"] == { "persist-credentials" => false }
  abort "external-links checkout security settings changed"
end

install = steps.find { |step| step["name"] == "Install checksum-pinned Lychee" }
expected_install = [
  "set -euo pipefail",
  './scripts/install-policy-tools.sh install "$RUNNER_TEMP/policy-tools" lychee'
]
unless install &&
       install["shell"] == "bash" &&
       install.fetch("run").lines.map(&:rstrip) == expected_install
  abort "external-links pinned installer invocation changed"
end

check = steps.find { |step| step["name"] == "Check external links" }
loopback =
  "(?i)^https?://(?:localhost|(?:[^./:]+\\.)*localhost|" \
  "127(?:\\.[0-9]{1,3}){3}|\\[::1\\])" \
  "(?::[0-9]+)?(?:/|$)"
examples =
  "(?i)^https?://(?:[^./:]+\\.)*" \
  "(?:example\\.com|example\\.org|example\\.net)" \
  "(?::[0-9]+)?(?:/|$)"
reserved =
  "(?i)^https?://(?:[^./:]+\\.)*" \
  "(?:example|invalid|localhost|test)" \
  "(?::[0-9]+)?(?:/|$)"
advisory =
  "^https://github\\.com/EngramMesh/EngramMesh/security/advisories/new$"
expected_check = [
  "set -euo pipefail",
  '"$RUNNER_TEMP/policy-tools/bin/lychee" \\',
  "  --no-progress \\",
  "  --max-retries 2 \\",
  "  --timeout 20 \\",
  "  --exclude '#{loopback}' \\",
  "  --exclude '#{examples}' \\",
  "  --exclude '#{reserved}' \\",
  "  --exclude '#{advisory}' \\",
  "  './**/*.md'"
]
unless check &&
       check["shell"] == "bash" &&
       check.fetch("run").lines.map(&:rstrip) == expected_check
  abort "external-links Lychee arguments changed"
end

exclusions = [loopback, examples, reserved, advisory].map { |pattern| Regexp.new(pattern) }
excluded_urls = [
  "http://localhost/",
  "HTTP://LOCALHOST:8080/path",
  "https://service.LocalHost:9443/",
  "http://127.0.0.1/",
  "https://127.255.255.255:65535/path",
  "http://[::1]/",
  "https://[::1]:8443/path",
  "https://example.com/",
  "http://docs.EXAMPLE.org:8080/path",
  "https://a.b.example.net/",
  "https://example/",
  "http://service.invalid:3000/path",
  "https://LOCALHOST/",
  "http://subdomain.test:80/",
  "https://github.com/EngramMesh/EngramMesh/security/advisories/new"
]
excluded_urls.each do |url|
  abort "external-links exclusions missed #{url}" unless exclusions.any? { |pattern| pattern.match?(url) }
end
if exclusions.any? { |pattern| pattern.match?("https://www.openai.com/") }
  abort "external-links exclusions matched a normal public domain"
end
RUBY

  printf 'policy fixtures (external workflow): ok\n'
}

test_baseline() {
  validator=$script_dir/check-repository-baseline.sh
  baseline_root=$tmp_dir/baseline-fixture
  mkdir -p "$baseline_root"
  git -C "$repository_root" archive HEAD | tar -x -C "$baseline_root"
  mkdir -p "$baseline_root/.github/workflows"

  policy_files='
scripts/install-policy-tools.sh
scripts/check-dco.sh
scripts/check-markdown-links.sh
scripts/check-community-yaml.rb
scripts/check-private-history.sh
scripts/check-workflow-policy.rb
scripts/test-repository-policy.sh
scripts/check-repository-policy.sh
.github/workflows/repository-policy.yml
.github/workflows/external-links.yml
'
  policy_executables='
scripts/install-policy-tools.sh
scripts/check-dco.sh
scripts/check-markdown-links.sh
scripts/check-community-yaml.rb
scripts/check-private-history.sh
scripts/check-workflow-policy.rb
scripts/test-repository-policy.sh
scripts/check-repository-policy.sh
'

  for path in $policy_files; do
    cp "$repository_root/$path" "$baseline_root/$path"
  done
  printf '\n%s\n%s\n' \
    'Maintainers integrate pull requests with Rebase and Merge so each validated' \
    'DCO trailer remains in the main history. Squash Merge and Merge Commit are not used.' \
    >>"$baseline_root/CONTRIBUTING.md"
  cp "$validator" "$baseline_root/scripts/check-repository-baseline.sh"
  chmod +x "$baseline_root/scripts"/*

  git -C "$baseline_root" \
    -c core.hooksPath=/dev/null \
    -c commit.gpgsign=false \
    init --quiet --template="$tmp_dir/empty-template"
  git -C "$baseline_root" add .

  run_baseline_validator() {
    (
      cd "$baseline_root"
      ./scripts/check-repository-baseline.sh
    )
  }

  run_baseline_validator ||
    fail 'complete repository baseline fixture was rejected'

  awk '{ printf "%s\r\n", $0 }' "$baseline_root/CONTRIBUTING.md" \
    >"$tmp_dir/contributing-crlf.md"
  mv "$tmp_dir/contributing-crlf.md" "$baseline_root/CONTRIBUTING.md"
  run_baseline_validator ||
    fail 'CRLF repository baseline fixture was rejected'
  tr -d '\r' <"$baseline_root/CONTRIBUTING.md" \
    >"$tmp_dir/contributing-lf.md"
  mv "$tmp_dir/contributing-lf.md" "$baseline_root/CONTRIBUTING.md"

  for path in $policy_files; do
    rm -f "$baseline_root/$path"
    missing_output=$tmp_dir/baseline-missing-$(printf '%s' "$path" | tr / _).out
    capture_failure "$missing_output" run_baseline_validator ||
      fail "baseline accepted missing policy file: $path"
    grep -Fqx "missing or empty: $path" "$missing_output" ||
      fail "missing policy file did not report its path: $path"
    cp "$repository_root/$path" "$baseline_root/$path"
  done

  for path in $policy_executables; do
    chmod -x "$baseline_root/$path"
    mode_output=$tmp_dir/baseline-mode-$(printf '%s' "$path" | tr / _).out
    capture_failure "$mode_output" run_baseline_validator ||
      fail "baseline accepted non-executable policy script: $path"
    grep -Fqx "not executable: $path" "$mode_output" ||
      fail "non-executable policy script did not report its path: $path"
    chmod +x "$baseline_root/$path"
  done

  assert_ripgrep_command_rejected() {
    fixture_name=$1
    fixture_command=$2
    printf '%s\n' "$fixture_command" \
      >>"$baseline_root/scripts/check-dco.sh"
    ripgrep_output=$tmp_dir/baseline-ripgrep-$fixture_name.out
    capture_failure "$ripgrep_output" run_baseline_validator ||
      fail "baseline accepted ripgrep command spelling: $fixture_name"
    grep -Fqx \
      'public policy files must not invoke ripgrep' \
      "$ripgrep_output" ||
      fail "public ripgrep dependency diagnostic changed: $fixture_name"
    cp "$repository_root/scripts/check-dco.sh" \
      "$baseline_root/scripts/check-dco.sh"
    chmod +x "$baseline_root/scripts/check-dco.sh"
  }

  direct_ripgrep_command=r'g -q forbidden-runtime-dependency README.md'
  single_quote_ripgrep_command="r''g -q forbidden-runtime-dependency README.md"
  double_quote_ripgrep_command='r""g -q forbidden-runtime-dependency README.md'
  separator_ripgrep_command=':; r""g -q forbidden-runtime-dependency README.md'
  prefixed_ripgrep_command="if POLICY_MODE=test command r''g -q forbidden-runtime-dependency README.md"
  assert_ripgrep_command_rejected direct "$direct_ripgrep_command"
  assert_ripgrep_command_rejected \
    adjacent-single-quotes "$single_quote_ripgrep_command"
  assert_ripgrep_command_rejected \
    adjacent-double-quotes "$double_quote_ripgrep_command"
  assert_ripgrep_command_rejected \
    after-separator "$separator_ripgrep_command"
  assert_ripgrep_command_rejected \
    keyword-assignment-command-prefix "$prefixed_ripgrep_command"

  {
    printf '%s%s\n' '# r' 'g is harmless fixture prose'
    printf '%s%s\n' "echo 'r" "g is prose'"
    printf '%s%s\n' "fixture_data='r" "g'"
    printf '%s%s\n' "printf '%s\n' 'r" "g is data'"
  } >>"$baseline_root/scripts/check-dco.sh"
  run_baseline_validator ||
    fail 'baseline rejected harmless ripgrep comments, prose, or data'
  cp "$repository_root/scripts/check-dco.sh" \
    "$baseline_root/scripts/check-dco.sh"
  chmod +x "$baseline_root/scripts/check-dco.sh"

  awk '
    $0 == "Maintainers integrate pull requests with Rebase and Merge so each validated" {
      getline
      next
    }
    { print }
  ' "$baseline_root/CONTRIBUTING.md" \
    >"$tmp_dir/contributing-without-integration-guidance.md"
  mv "$tmp_dir/contributing-without-integration-guidance.md" \
    "$baseline_root/CONTRIBUTING.md"
  guidance_output=$tmp_dir/baseline-missing-integration-guidance.out
  capture_failure "$guidance_output" run_baseline_validator ||
    fail 'baseline accepted missing rebase-only DCO integration guidance'
  grep -Fqx \
    'CONTRIBUTING.md does not require rebase-only DCO integration' \
    "$guidance_output" ||
    fail 'missing rebase-only DCO integration guidance diagnostic changed'

  printf 'policy fixtures (baseline): ok\n'
}

test_yaml() {
  validator=$script_dir/check-community-yaml.rb

  [ -x "$validator" ] ||
    fail 'community YAML validator is missing or not executable'

  psych_compatibility_shim=$tmp_dir/psych-one-positional-parse.rb
  printf '%s\n' \
    'require "yaml"' \
    'module Psych' \
    '  class << self' \
    '    alias_method :repository_policy_original_parse, :parse' \
    '    def parse(yaml, **keywords)' \
    '      repository_policy_original_parse(yaml, **keywords)' \
    '    end' \
    '  end' \
    'end' \
    >"$psych_compatibility_shim"
  psych_compatibility_output=$tmp_dir/psych-one-positional-parse.out
  if ! ruby -r "$psych_compatibility_shim" \
    "$validator" "$repository_root" \
    >"$psych_compatibility_output" 2>&1; then
    if grep -Fq 'wrong number of arguments' \
      "$psych_compatibility_output"; then
      fail 'community YAML validator passed a second positional argument to Psych.parse'
    fi
    cat "$psych_compatibility_output" >&2
    fail 'community YAML validator failed under one-argument Psych.parse compatibility shim'
  fi

  "$validator" "$repository_root" ||
    fail 'repository community YAML files were rejected'

  fixture_root=$tmp_dir/yaml-fixture
  mkdir -p "$fixture_root/.github/ISSUE_TEMPLATE"
  printf '%s\n' \
    'name: Minimal form' \
    'description: A valid minimal issue form.' \
    'body:' \
    '  - type: input' \
    '    id: summary' \
    '    attributes:' \
    '      label: Summary' \
    >"$tmp_dir/valid-form.yml"
  printf '%s\n' \
    'blank_issues_enabled: false' \
    'contact_links:' \
    '  - name: Report a security vulnerability' \
    '    url: https://github.com/EngramMesh/EngramMesh/security/advisories/new' \
    '    about: Use private vulnerability reporting.' \
    >"$tmp_dir/valid-config.yml"

  reset_yaml_fixture() {
    cp "$tmp_dir/valid-form.yml" \
      "$fixture_root/.github/ISSUE_TEMPLATE/bug.yml"
    cp "$tmp_dir/valid-form.yml" \
      "$fixture_root/.github/ISSUE_TEMPLATE/feature.yml"
    cp "$tmp_dir/valid-config.yml" \
      "$fixture_root/.github/ISSUE_TEMPLATE/config.yml"
  }

  assert_yaml_rejected() {
    fixture_name=$1
    expected_diagnostic=$2
    fixture_output=$tmp_dir/yaml-$fixture_name.out
    validator_status=0
    "$validator" "$fixture_root" >"$fixture_output" 2>&1 ||
      validator_status=$?
    grep -Fqx "$expected_diagnostic" "$fixture_output" ||
      fail "$fixture_name did not report: $expected_diagnostic"
    [ "$validator_status" -ne 0 ] ||
      fail "$fixture_name was accepted"
  }

  reset_yaml_fixture
  "$validator" "$fixture_root" ||
    fail 'valid minimal community YAML fixture was rejected'

  : >"$fixture_root/.github/ISSUE_TEMPLATE/bug.yml"
  assert_yaml_rejected empty-root \
    '.github/ISSUE_TEMPLATE/bug.yml: root must be a mapping'

  reset_yaml_fixture
  printf '%s\n' 'scalar root' \
    >"$fixture_root/.github/ISSUE_TEMPLATE/bug.yml"
  assert_yaml_rejected scalar-root \
    '.github/ISSUE_TEMPLATE/bug.yml: root must be a mapping'

  assert_bad_form() {
    bad_form_name=$1
    bad_form_diagnostic=$2
    bad_form_content=$3
    reset_yaml_fixture
    printf '%s\n' "$bad_form_content" \
      >"$fixture_root/.github/ISSUE_TEMPLATE/bug.yml"
    assert_yaml_rejected "$bad_form_name" "$bad_form_diagnostic"
  }

  assert_bad_config() {
    bad_config_name=$1
    bad_config_diagnostic=$2
    bad_config_content=$3
    reset_yaml_fixture
    printf '%s\n' "$bad_config_content" \
      >"$fixture_root/.github/ISSUE_TEMPLATE/config.yml"
    assert_yaml_rejected "$bad_config_name" "$bad_config_diagnostic"
  }

  assert_bad_form alias \
    '.github/ISSUE_TEMPLATE/bug.yml: YAML aliases are not allowed' \
    'name: &form_name Aliased form
description: Invalid alias fixture.
title: *form_name
body:
  - type: input
    id: summary
    attributes:
      label: Summary'
  assert_bad_form unsafe-class \
    '.github/ISSUE_TEMPLATE/bug.yml: invalid YAML' \
    'name: !ruby/object:Object {}
description: Unsafe class fixture.
body:
  - type: input
    id: summary
    attributes:
      label: Summary'
  assert_bad_form malformed-yaml \
    '.github/ISSUE_TEMPLATE/bug.yml: invalid YAML' \
    'name: [unterminated
description: Invalid YAML fixture.'

  assert_bad_form false-root \
    '.github/ISSUE_TEMPLATE/bug.yml: root must be a mapping' \
    'false'
  assert_bad_form number-root \
    '.github/ISSUE_TEMPLATE/bug.yml: root must be a mapping' \
    '42'
  assert_bad_form sequence-root \
    '.github/ISSUE_TEMPLATE/bug.yml: root must be a mapping' \
    '- not
- a
- mapping'

  assert_bad_form missing-name \
    '.github/ISSUE_TEMPLATE/bug.yml: name must be a non-empty string' \
    'description: Missing name fixture.
body:
  - type: input
    id: summary
    attributes:
      label: Summary'
  assert_bad_form non-string-name \
    '.github/ISSUE_TEMPLATE/bug.yml: name must be a non-empty string' \
    'name: 7
description: Invalid name fixture.
body:
  - type: input
    id: summary
    attributes:
      label: Summary'
  assert_bad_form missing-description \
    '.github/ISSUE_TEMPLATE/bug.yml: description must be a non-empty string' \
    'name: Missing description
body:
  - type: input
    id: summary
    attributes:
      label: Summary'
  assert_bad_form non-string-description \
    '.github/ISSUE_TEMPLATE/bug.yml: description must be a non-empty string' \
    'name: Invalid description
description: false
body:
  - type: input
    id: summary
    attributes:
      label: Summary'

  assert_bad_form empty-body \
    '.github/ISSUE_TEMPLATE/bug.yml: body must be a non-empty sequence' \
    'name: Empty body
description: Invalid empty body fixture.
body: []'
  assert_bad_form markdown-only \
    '.github/ISSUE_TEMPLATE/bug.yml: body must contain at least one non-Markdown item' \
    'name: Markdown only
description: Invalid Markdown-only fixture.
body:
  - type: markdown
    attributes:
      value: Read this.'
  assert_bad_form unsupported-type \
    '.github/ISSUE_TEMPLATE/bug.yml: body[0].type is unsupported: mystery' \
    'name: Unsupported type
description: Invalid body type fixture.
body:
  - type: mystery
    id: summary
    attributes:
      label: Summary'

  assert_bad_form missing-id \
    '.github/ISSUE_TEMPLATE/bug.yml: body[0].id must match [a-zA-Z][a-zA-Z0-9_-]*' \
    'name: Missing ID
description: Invalid missing ID fixture.
body:
  - type: input
    attributes:
      label: Summary'
  assert_bad_form invalid-id \
    '.github/ISSUE_TEMPLATE/bug.yml: body[0].id must match [a-zA-Z][a-zA-Z0-9_-]*' \
    'name: Invalid ID
description: Invalid ID fixture.
body:
  - type: input
    id: 9-invalid
    attributes:
      label: Summary'
  assert_bad_form duplicate-id \
    '.github/ISSUE_TEMPLATE/bug.yml: body[1].id duplicates body[0].id: summary' \
    'name: Duplicate ID
description: Invalid duplicate ID fixture.
body:
  - type: input
    id: summary
    attributes:
      label: Summary
  - type: textarea
    id: summary
    attributes:
      label: Details'
  assert_bad_form markdown-duplicate-id \
    '.github/ISSUE_TEMPLATE/bug.yml: body[1].id duplicates body[0].id: summary' \
    'name: Markdown duplicate ID
description: Markdown and input duplicate ID fixture.
body:
  - type: markdown
    id: summary
    attributes:
      value: Read this.
  - type: input
    id: summary
    attributes:
      label: Summary'

  assert_bad_form missing-attributes \
    '.github/ISSUE_TEMPLATE/bug.yml: body[0].attributes must be a mapping' \
    'name: Missing attributes
description: Invalid missing attributes fixture.
body:
  - type: input
    id: summary'
  assert_bad_form markdown-empty-value \
    '.github/ISSUE_TEMPLATE/bug.yml: body[0].attributes.value must be a non-empty string' \
    'name: Empty Markdown
description: Invalid Markdown value fixture.
body:
  - type: markdown
    attributes:
      value: ""
  - type: input
    id: summary
    attributes:
      label: Summary'

  assert_bad_form input-empty-label \
    '.github/ISSUE_TEMPLATE/bug.yml: body[0].attributes.label must be a non-empty string' \
    'name: Empty input label
description: Invalid input label fixture.
body:
  - type: input
    id: summary
    attributes:
      label: ""'
  assert_bad_form textarea-missing-label \
    '.github/ISSUE_TEMPLATE/bug.yml: body[0].attributes.label must be a non-empty string' \
    'name: Missing textarea label
description: Invalid textarea label fixture.
body:
  - type: textarea
    id: summary
    attributes:
      description: Details'
  assert_bad_form dropdown-non-string-label \
    '.github/ISSUE_TEMPLATE/bug.yml: body[0].attributes.label must be a non-empty string' \
    'name: Invalid dropdown label
description: Invalid dropdown label fixture.
body:
  - type: dropdown
    id: choice
    attributes:
      label: false
      options:
        - One'

  assert_bad_form dropdown-empty-options \
    '.github/ISSUE_TEMPLATE/bug.yml: body[0].attributes.options must be a non-empty sequence' \
    'name: Empty dropdown options
description: Invalid dropdown options fixture.
body:
  - type: dropdown
    id: choice
    attributes:
      label: Choice
      options: []'
  assert_bad_form dropdown-empty-option \
    '.github/ISSUE_TEMPLATE/bug.yml: body[0].attributes.options[0] must be a non-empty string' \
    'name: Empty dropdown option
description: Invalid dropdown option fixture.
body:
  - type: dropdown
    id: choice
    attributes:
      label: Choice
      options:
        - ""'
  assert_bad_form dropdown-duplicate-option \
    '.github/ISSUE_TEMPLATE/bug.yml: body[0].attributes.options[1] duplicates options[0]: One' \
    'name: Duplicate dropdown option
description: Invalid duplicate option fixture.
body:
  - type: dropdown
    id: choice
    attributes:
      label: Choice
      options:
        - One
        - One'
  assert_bad_form dropdown-mapping-option \
    '.github/ISSUE_TEMPLATE/bug.yml: body[0].attributes.options[0] must be a non-empty string' \
    'name: Mapping dropdown option
description: Invalid mapping option fixture.
body:
  - type: dropdown
    id: choice
    attributes:
      label: Choice
      options:
        - label: One'
  assert_bad_form dropdown-non-boolean-multiple \
    '.github/ISSUE_TEMPLATE/bug.yml: body[0].attributes.multiple must be Boolean' \
    'name: Invalid dropdown multiple
description: Invalid dropdown multiple fixture.
body:
  - type: dropdown
    id: choice
    attributes:
      label: Choice
      options:
        - One
      multiple: "false"'

  reset_yaml_fixture
  printf '%s\n' \
    'name: Zero default' \
    'description: Valid zero dropdown default fixture.' \
    'body:' \
    '  - type: dropdown' \
    '    id: choice' \
    '    attributes:' \
    '      label: Choice' \
    '      options:' \
    '        - One' \
    '      default: 0' \
    >"$fixture_root/.github/ISSUE_TEMPLATE/bug.yml"
  "$validator" "$fixture_root" ||
    fail 'valid dropdown default zero was rejected'

  assert_bad_form dropdown-boolean-default \
    '.github/ISSUE_TEMPLATE/bug.yml: body[0].attributes.default must be a zero-based option index' \
    'name: Boolean dropdown default
description: Invalid Boolean dropdown default fixture.
body:
  - type: dropdown
    id: choice
    attributes:
      label: Choice
      options:
        - One
      default: false'
  assert_bad_form dropdown-negative-default \
    '.github/ISSUE_TEMPLATE/bug.yml: body[0].attributes.default must be a zero-based option index' \
    'name: Negative dropdown default
description: Invalid negative dropdown default fixture.
body:
  - type: dropdown
    id: choice
    attributes:
      label: Choice
      options:
        - One
      default: -1'
  assert_bad_form dropdown-out-of-range-default \
    '.github/ISSUE_TEMPLATE/bug.yml: body[0].attributes.default must be a zero-based option index' \
    'name: Out of range dropdown default
description: Invalid out of range dropdown default fixture.
body:
  - type: dropdown
    id: choice
    attributes:
      label: Choice
      options:
        - One
      default: 1'
  assert_bad_form dropdown-none-default \
    '.github/ISSUE_TEMPLATE/bug.yml: body[0].attributes.default cannot be combined with a None or n/a option' \
    'name: None dropdown default
description: Invalid None option default fixture.
body:
  - type: dropdown
    id: choice
    attributes:
      label: Choice
      options:
        - One
        - nOnE
      default: 0'
  assert_bad_form dropdown-na-default \
    '.github/ISSUE_TEMPLATE/bug.yml: body[0].attributes.default cannot be combined with a None or n/a option' \
    'name: N/A dropdown default
description: Invalid n/a option default fixture.
body:
  - type: dropdown
    id: choice
    attributes:
      label: Choice
      options:
        - One
        - N/A
      default: 0'
  assert_bad_form dropdown-compound-default \
    '.github/ISSUE_TEMPLATE/bug.yml: body[0].attributes.default must be a zero-based option index' \
    'name: Compound dropdown default
description: Compound invalid dropdown default fixture.
body:
  - type: dropdown
    id: choice
    attributes:
      label: Choice
      options:
        - One
        - None
      default: -1'
  grep -Fqx \
    '.github/ISSUE_TEMPLATE/bug.yml: body[0].attributes.default cannot be combined with a None or n/a option' \
    "$tmp_dir/yaml-dropdown-compound-default.out" ||
    fail 'dropdown-compound-default did not preserve: default cannot be combined with a None or n/a option'

  assert_bad_form checkbox-invalid-label \
    '.github/ISSUE_TEMPLATE/bug.yml: body[0].attributes.options[0].label must be a non-empty string' \
    'name: Invalid checkbox label
description: Invalid checkbox option label fixture.
body:
  - type: checkboxes
    id: consent
    attributes:
      options:
        - label: ""'
  assert_bad_form checkbox-invalid-required \
    '.github/ISSUE_TEMPLATE/bug.yml: body[0].attributes.options[0].required must be Boolean' \
    'name: Invalid checkbox required
description: Invalid checkbox required fixture.
body:
  - type: checkboxes
    id: consent
    attributes:
      options:
        - label: I agree
          required: "yes"'

  assert_bad_form non-mapping-validations \
    '.github/ISSUE_TEMPLATE/bug.yml: body[0].validations must be a mapping' \
    'name: Invalid validations
description: Invalid validations fixture.
body:
  - type: input
    id: summary
    attributes:
      label: Summary
    validations:
      - required'
  assert_bad_form non-boolean-validation-required \
    '.github/ISSUE_TEMPLATE/bug.yml: body[0].validations.required must be Boolean' \
    'name: Invalid required validation
description: Invalid required validation fixture.
body:
  - type: input
    id: summary
    attributes:
      label: Summary
    validations:
      required: "true"'

  assert_bad_form unknown-root-key \
    '.github/ISSUE_TEMPLATE/bug.yml: unknown root key: mystery' \
    'name: Unknown root key
description: Invalid unknown root key fixture.
mystery: value
body:
  - type: input
    id: summary
    attributes:
      label: Summary'
  assert_bad_form unknown-body-key \
    '.github/ISSUE_TEMPLATE/bug.yml: body[0] has unknown key: mystery' \
    'name: Unknown body key
description: Invalid unknown body key fixture.
body:
  - type: input
    id: summary
    mystery: value
    attributes:
      label: Summary'
  assert_bad_form unknown-attribute-key \
    '.github/ISSUE_TEMPLATE/bug.yml: body[0].attributes has unknown key: mystery' \
    'name: Unknown attribute key
description: Invalid unknown attribute key fixture.
body:
  - type: input
    id: summary
    attributes:
      label: Summary
      mystery: value'
  assert_bad_form invalid-title-type \
    '.github/ISSUE_TEMPLATE/bug.yml: title must be a string' \
    'name: Invalid title
description: Invalid title fixture.
title: false
body:
  - type: input
    id: summary
    attributes:
      label: Summary'
  assert_bad_form invalid-labels-type \
    '.github/ISSUE_TEMPLATE/bug.yml: labels must be a sequence of non-empty strings' \
    'name: Invalid labels
description: Invalid labels fixture.
labels: bug
body:
  - type: input
    id: summary
    attributes:
      label: Summary'
  assert_bad_form invalid-assignees-type \
    '.github/ISSUE_TEMPLATE/bug.yml: assignees must be a sequence of non-empty strings' \
    'name: Invalid assignees
description: Invalid assignees fixture.
assignees:
  - false
body:
  - type: input
    id: summary
    attributes:
      label: Summary'

  assert_bad_form duplicate-root-key \
    '.github/ISSUE_TEMPLATE/bug.yml: duplicate mapping key at $.name' \
    'name: First name
name: Second name
description: Duplicate root key fixture.
body:
  - type: input
    id: summary
    attributes:
      label: Summary'
  assert_bad_form duplicate-nested-key \
    '.github/ISSUE_TEMPLATE/bug.yml: duplicate mapping key at $.body[0].attributes.label' \
    'name: Duplicate nested key
description: Duplicate nested key fixture.
body:
  - type: input
    id: summary
    attributes:
      label: First label
      label: Second label'
  assert_bad_form equivalent-scalar-key \
    '.github/ISSUE_TEMPLATE/bug.yml: duplicate mapping key at $.TRUE' \
    'true: first value
TRUE: second value
name: Equivalent scalar keys
description: Equivalent scalar key fixture.
body:
  - type: input
    id: summary
    attributes:
      label: Summary'
  reset_yaml_fixture
  printf '%s\n' \
    'true: Boolean key' \
    '!ruby/string true: Explicit string key' \
    'name: Distinct explicit string key' \
    'description: Boolean and explicit string key fixture.' \
    'body:' \
    '  - type: input' \
    '    id: summary' \
    '    attributes:' \
    '      label: Summary' \
    >"$fixture_root/.github/ISSUE_TEMPLATE/bug.yml"
  explicit_string_distinct_output=$tmp_dir/yaml-explicit-string-distinct.out
  explicit_string_distinct_status=0
  "$validator" "$fixture_root" \
    >"$explicit_string_distinct_output" 2>&1 ||
    explicit_string_distinct_status=$?
  [ "$explicit_string_distinct_status" -ne 0 ] ||
    fail 'Boolean and explicitly tagged string root keys bypassed the schema'
  grep -Fqx \
    '.github/ISSUE_TEMPLATE/bug.yml: unknown root key: true' \
    "$explicit_string_distinct_output" ||
    fail 'explicit string tag was not loaded distinctly from a Boolean key'
  explicit_string_unknown_count=$(
    grep -Fxc \
      '.github/ISSUE_TEMPLATE/bug.yml: unknown root key: true' \
      "$explicit_string_distinct_output"
  )
  [ "$explicit_string_unknown_count" -eq 2 ] ||
    fail 'Boolean and explicitly tagged string keys did not remain distinct'
  if grep -Fq 'duplicate mapping key' "$explicit_string_distinct_output"; then
    fail 'explicit string tag was conflated with a Boolean key'
  fi

  assert_bad_form equivalent-explicit-string-key \
    '.github/ISSUE_TEMPLATE/bug.yml: duplicate mapping key at $.true' \
    '!str true: First string value
!ruby/string true: Second string value
name: Equivalent explicit string keys
description: Equivalent explicit string key fixture.
body:
  - type: input
    id: summary
    attributes:
      label: Summary'
  assert_bad_form nested-equivalent-explicit-string-key \
    '.github/ISSUE_TEMPLATE/bug.yml: duplicate mapping key at $.body[0].attributes.mystery' \
    'name: Nested explicit string keys
description: Nested explicit string key fixture.
body:
  - type: input
    id: summary
    attributes:
      label: Summary
      !str mystery: First string value
      !ruby/string mystery: Second string value'
  assert_bad_form equivalent-integer-key \
    '.github/ISSUE_TEMPLATE/bug.yml: duplicate mapping key at $["1"]' \
    '01: first value
1: second value
name: Equivalent integer keys
description: Equivalent integer key fixture.
body:
  - type: input
    id: summary
    attributes:
      label: Summary'
  assert_bad_form nested-equivalent-key \
    '.github/ISSUE_TEMPLATE/bug.yml: duplicate mapping key at $.body[0].attributes.TRUE' \
    'name: Nested equivalent keys
description: Nested equivalent key fixture.
body:
  - type: input
    id: summary
    attributes:
      label: Summary
      true: first value
      TRUE: second value'
  assert_bad_form composite-mapping-key \
    '.github/ISSUE_TEMPLATE/bug.yml: unsupported non-scalar mapping key at $' \
    '? [name, description]
: unsupported key
name: Composite key
description: Composite mapping key fixture.
body:
  - type: input
    id: summary
    attributes:
      label: Summary'

  reset_yaml_fixture
  printf '%s\n' \
    'name: First name' \
    'name: !ruby/object:Object {}' \
    'description: AST gate fixture.' \
    'body:' \
    '  - type: input' \
    '    id: summary' \
    '    attributes:' \
    '      label: Summary' \
    >"$fixture_root/.github/ISSUE_TEMPLATE/bug.yml"
  ast_gate_output=$tmp_dir/yaml-ast-gate.out
  ast_gate_status=0
  "$validator" "$fixture_root" >"$ast_gate_output" 2>&1 ||
    ast_gate_status=$?
  [ "$ast_gate_status" -ne 0 ] ||
    fail 'AST duplicate-key gate fixture was accepted'
  grep -Fqx \
    '.github/ISSUE_TEMPLATE/bug.yml: duplicate mapping key at $.name' \
    "$ast_gate_output" ||
    fail 'AST duplicate-key gate did not report its duplicate'
  if grep -Fq '.github/ISSUE_TEMPLATE/bug.yml: invalid YAML' \
    "$ast_gate_output"; then
    fail 'AST duplicate-key errors did not gate safe loading'
  fi

  assert_bad_config blank-issues-enabled \
    '.github/ISSUE_TEMPLATE/config.yml: blank_issues_enabled must be false' \
    'blank_issues_enabled: true
contact_links:
  - name: Report a security vulnerability
    url: https://github.com/EngramMesh/EngramMesh/security/advisories/new
    about: Use private vulnerability reporting.'
  assert_bad_config malformed-contact-link \
    '.github/ISSUE_TEMPLATE/config.yml: contact_links[0].about must be a non-empty string' \
    'blank_issues_enabled: false
contact_links:
  - name: Report a security vulnerability
    url: https://github.com/EngramMesh/EngramMesh/security/advisories/new'
  assert_bad_config missing-advisory-url \
    '.github/ISSUE_TEMPLATE/config.yml: contact_links must include https://github.com/EngramMesh/EngramMesh/security/advisories/new' \
    'blank_issues_enabled: false
contact_links:
  - name: Ask a question
    url: https://github.com/EngramMesh/EngramMesh/discussions
    about: Ask the community.'

  reset_yaml_fixture
  printf '%s\n' \
    'name: Multiple errors' \
    'description: false' \
    'mystery: value' \
    'body: []' \
    >"$fixture_root/.github/ISSUE_TEMPLATE/bug.yml"
  multiple_errors_output=$tmp_dir/yaml-multiple-errors.out
  multiple_errors_status=0
  "$validator" "$fixture_root" >"$multiple_errors_output" 2>&1 ||
    multiple_errors_status=$?
  [ "$multiple_errors_status" -ne 0 ] ||
    fail 'multiple invalid YAML fields were accepted'
  for multiple_error in \
    '.github/ISSUE_TEMPLATE/bug.yml: unknown root key: mystery' \
    '.github/ISSUE_TEMPLATE/bug.yml: description must be a non-empty string' \
    '.github/ISSUE_TEMPLATE/bug.yml: body must be a non-empty sequence'; do
    grep -Fqx "$multiple_error" "$multiple_errors_output" ||
      fail "multiple-error fixture did not preserve: $multiple_error"
  done

  reset_yaml_fixture
  rm -f "$fixture_root/.github/ISSUE_TEMPLATE/config.yml"
  assert_yaml_rejected unreadable-file \
    '.github/ISSUE_TEMPLATE/config.yml: cannot read file'

  printf 'policy fixtures (yaml): ok\n'
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
  grep -Fq 'invalid commit revision: not-a-commit' "$invalid_revision_output" ||
    fail 'invalid link-check revision did not report its value'

  relative_lychee_output=$tmp_dir/relative-lychee.out
  capture_failure "$relative_lychee_output" \
    run_link_validator "$fixture_repo" \
    --revision HEAD --lychee ./lychee ||
    fail 'relative Lychee executable path was accepted'
  grep -Fq 'Lychee path must be absolute' "$relative_lychee_output" ||
    fail 'relative Lychee path did not report the absolute-path requirement'

  nonexecutable_lychee=$tmp_dir/nonexecutable-lychee
  : >"$nonexecutable_lychee"
  nonexecutable_lychee_output=$tmp_dir/nonexecutable-lychee.out
  capture_failure "$nonexecutable_lychee_output" \
    run_link_validator "$fixture_repo" \
    --revision HEAD --lychee "$nonexecutable_lychee" ||
    fail 'nonexecutable absolute Lychee path was accepted'
  grep -Fq 'Lychee path is not executable:' "$nonexecutable_lychee_output" ||
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
  grep -Fq 'invalid file URL in Markdown:' "$invalid_file_url_output" ||
    fail 'invalid serialized file URL did not report a clear diagnostic'

  invalid_utf8_output=$tmp_dir/invalid-utf8-file-url.out
  capture_failure "$invalid_utf8_output" \
    run_link_validator_with_dump \
    "$fixture_repo" invalid_utf8 "$dump_lychee" ||
    fail 'non-UTF-8 file URL path was accepted'
  grep -Fq 'file URL path is not valid UTF-8:' "$invalid_utf8_output" ||
    fail 'non-UTF-8 file URL path did not report a clear diagnostic'

  nul_file_url_output=$tmp_dir/nul-file-url.out
  capture_failure "$nul_file_url_output" \
    run_link_validator_with_dump "$fixture_repo" nul "$dump_lychee" ||
    fail 'NUL-encoded file URL was accepted'
  grep -Fq 'file URL contains a NUL byte:' "$nul_file_url_output" ||
    fail 'NUL-encoded file URL did not report a clear diagnostic'

  authority_file_url_output=$tmp_dir/authority-file-url.out
  capture_failure "$authority_file_url_output" \
    run_link_validator_with_dump "$fixture_repo" authority "$dump_lychee" ||
    fail 'remote-authority file URL was accepted'
  grep -Fq 'file URL authority is not allowed:' "$authority_file_url_output" ||
    fail 'remote-authority file URL did not report a clear diagnostic'

  inside_snapshot_output=$tmp_dir/inside-snapshot.out
  capture_failure "$inside_snapshot_output" \
    run_link_validator_with_tmp "$fixture_repo" "$fixture_repo" \
    --revision HEAD --lychee "$lychee" ||
    fail 'snapshot directory inside the repository was accepted'
  grep -Fq 'snapshot directory must be outside the repository' \
    "$inside_snapshot_output" ||
    fail 'inside-repository snapshot did not report a clear diagnostic'
  if find "$fixture_repo" -maxdepth 1 -type d \
    -name 'engrammesh-links.*' -print | grep -q .; then
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
  grep -Eq 'File not found[.] Check if file exists and path is correct' \
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
    grep -Eq 'docs/untracked-target[.]md' ||
    fail 'untracked link target fixture was accidentally tracked'
  untracked_output=$tmp_dir/untracked-target.out
  capture_failure "$untracked_output" \
    run_link_validator "$untracked_repo" \
    --revision HEAD --lychee "$lychee" ||
    fail 'existing but untracked link target was accepted'
  grep -Eq 'File not found[.] Check if file exists and path is correct' \
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
  grep -Eq 'File not found[.] Check if file exists and path is correct' \
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
  grep -Eq 'link target escapes snapshot: .*outside[.]md' \
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
  grep -Eq 'link target escapes snapshot: .*outside[.]md' \
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
  grep -Eq 'link target escapes snapshot: .*outside[.]md' \
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
  grep -Fq '1 Excluded' "$protocol_relative_output" ||
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
    grep -Fq "$discovered_link" "$discovery_output" ||
      fail "Lychee dump omitted valid CommonMark target: $discovered_link"
  done
  for ignored_link in \
    'missing-escaped-target.md' \
    'missing-fenced-target.md' \
    'missing-tilde-target.md' \
    'missing-inline-code-target.md'; do
    if grep -Fq "$ignored_link" "$discovery_output"; then
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
  grep -Fq 'no tracked Markdown files' "$no_markdown_output" ||
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
  grep -Eq 'tracked symbolic link is not allowed: docs/relative-link[.]md' \
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
  grep -Eq 'tracked symbolic link is not allowed: docs/absolute-link[.]md' \
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
  history)
    test_history
    ;;
  links)
    test_links
    ;;
  workflow)
    test_workflow
    ;;
  orchestration)
    test_orchestration
    ;;
  external)
    test_external_workflow
    ;;
  baseline)
    test_baseline
    ;;
  yaml)
    test_yaml
    ;;
  *)
    printf 'usage: %s {tools|dco|history|links|workflow|orchestration|external|baseline|yaml}\n' "$0" >&2
    exit 2
    ;;
esac
