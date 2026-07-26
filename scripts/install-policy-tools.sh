#!/bin/sh
set -eu

verify_sha256() {
  file=$1
  expected=$2

  if ! printf '%s\n' "$expected" | grep -Eq '^[0-9a-f]{64}$'; then
    printf 'invalid SHA-256 digest\n' >&2
    exit 1
  fi

  case $(uname -s) in
    Linux)
      actual=$(sha256sum "$file" | awk '{print $1}')
      ;;
    Darwin)
      actual=$(shasum -a 256 "$file" | awk '{print $1}')
      ;;
    *)
      printf 'unsupported policy-tool platform\n' >&2
      exit 1
      ;;
  esac

  if [ "$actual" != "$expected" ]; then
    printf 'SHA-256 mismatch\n' >&2
    exit 1
  fi
}

resolve() {
  tool=$1
  operating_system=$2
  architecture=$3

  case "$architecture" in
    x86_64 | amd64)
      normalized_architecture=x86_64
      ;;
    arm64 | aarch64)
      normalized_architecture=arm64
      ;;
    *)
      printf 'unsupported policy-tool platform\n' >&2
      exit 1
      ;;
  esac

  case "$tool:$operating_system:$normalized_architecture" in
    lychee:Linux:x86_64)
      asset_platform=x86_64-unknown-linux-gnu
      digest=1f4e0ef7f6554a6ed33dd7ac144fb2e1bbed98598e7af973042fc5cd43951c9a
      ;;
    lychee:Linux:arm64)
      asset_platform=aarch64-unknown-linux-gnu
      digest=91a7bd65685da41b90ccb9bc867a3d649a7818042dae04ff405e55a25bddee4c
      ;;
    lychee:Darwin:x86_64)
      asset_platform=x86_64-apple-darwin
      digest=887503a9cff667d322b8d0892b40bf49976eb9507af8483220a3706cdad55978
      ;;
    lychee:Darwin:arm64)
      asset_platform=aarch64-apple-darwin
      digest=c9d3740ea2d891854d37116c9fba840f37b6e7c89d330e7db84ac333631c4977
      ;;
    actionlint:Linux:x86_64)
      asset_platform=linux_amd64
      digest=8aca8db96f1b94770f1b0d72b6dddcb1ebb8123cb3712530b08cc387b349a3d8
      ;;
    actionlint:Linux:arm64)
      asset_platform=linux_arm64
      digest=325e971b6ba9bfa504672e29be93c24981eeb1c07576d730e9f7c8805afff0c6
      ;;
    actionlint:Darwin:x86_64)
      asset_platform=darwin_amd64
      digest=5b44c3bc2255115c9b69e30efc0fecdf498fdb63c5d58e17084fd5f16324c644
      ;;
    actionlint:Darwin:arm64)
      asset_platform=darwin_arm64
      digest=aba9ced2dee8d27fecca3dc7feb1a7f9a52caefa1eb46f3271ea66b6e0e6953f
      ;;
    *)
      printf 'unsupported policy-tool platform\n' >&2
      exit 1
      ;;
  esac

  case "$tool" in
    lychee)
      url=https://github.com/lycheeverse/lychee/releases/download/lychee-v0.24.2/lychee-$asset_platform.tar.gz
      ;;
    actionlint)
      url=https://github.com/rhysd/actionlint/releases/download/v1.7.12/actionlint_1.7.12_$asset_platform.tar.gz
      ;;
  esac

  printf '%s\n%s\n' "$url" "$digest"
}

install_tool() {
  directory=$1
  tool=$2
  download_directory=$directory/download
  bin_directory=$directory/bin
  archive=$download_directory/$tool.tar.gz
  extract_directory=$download_directory/extract-$tool

  resolution=$(resolve "$tool" "$(uname -s)" "$(uname -m)")
  url=$(printf '%s\n' "$resolution" | sed -n '1p')
  expected_digest=$(printf '%s\n' "$resolution" | sed -n '2p')
  archive_name=${url##*/}
  asset_name=${archive_name%.tar.gz}
  case "$tool" in
    lychee)
      archive_member=$asset_name/lychee
      ;;
    actionlint)
      archive_member=actionlint
      ;;
  esac

  mkdir -p "$download_directory" "$bin_directory" "$extract_directory"
  curl --disable --fail --location --silent --show-error \
    --output "$archive" "$url"
  verify_sha256 "$archive" "$expected_digest"
  tar -xzf "$archive" -C "$extract_directory" "$archive_member"
  mv "$extract_directory/$archive_member" "$bin_directory/$tool"
  rm -r "$extract_directory"
  rm -f "$archive"
  chmod +x "$bin_directory/$tool"
  printf '%s\n' "$bin_directory/$tool"
}

install_tools() {
  directory=$1
  selection=$2

  case "$selection" in
    all)
      install_tool "$directory" lychee
      install_tool "$directory" actionlint
      ;;
    lychee | actionlint)
      install_tool "$directory" "$selection"
      ;;
    *)
      printf 'unsupported policy tool selection: %s\n' "$selection" >&2
      exit 2
      ;;
  esac
}

case ${1:-} in
  install)
    if [ "$#" -ne 2 ] && [ "$#" -ne 3 ]; then
      exit 2
    fi
    install_tools "$2" "${3:-all}"
    ;;
  verify-sha256)
    [ "$#" -eq 3 ] || exit 2
    verify_sha256 "$2" "$3"
    ;;
  resolve)
    [ "$#" -eq 4 ] || exit 2
    resolve "$2" "$3" "$4"
    ;;
  *)
    printf 'usage: %s {verify-sha256 FILE EXPECTED_HEX|resolve TOOL OS ARCH|install DIRECTORY [all|lychee|actionlint]}\n' "$0" >&2
    exit 2
    ;;
esac
