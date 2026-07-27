#!/bin/sh
set -eu

if [ "$#" -ne 1 ]; then
  printf 'usage: %s REV\n' "$0" >&2
  exit 2
fi

requested_revision=$1
if ! revision=$(git rev-parse --verify "$requested_revision^{commit}" 2>/dev/null); then
  printf 'invalid commit revision: %s\n' "$requested_revision" >&2
  exit 1
fi

audit_dir=$(mktemp -d "${TMPDIR:-/tmp}/engrammesh-history.XXXXXX")
trap 'rm -rf "$audit_dir"' EXIT HUP INT TERM

git rev-list --objects "$revision" >"$audit_dir/objects"
git log -z --format= --name-only "$revision" >"$audit_dir/names"

ruby - "$audit_dir/objects" "$audit_dir/names" \
  "$audit_dir/offending-paths" <<'RUBY'
# frozen_string_literal: true

def decode_git_c_path(field)
  return field unless field.start_with?('"'.b)
  raise "unterminated Git path quote" unless field.end_with?('"'.b)

  input = field.byteslice(1, field.bytesize - 2)
  output = +"".b
  escapes = {
    "a" => 7, "b" => 8, "t" => 9, "n" => 10,
    "v" => 11, "f" => 12, "r" => 13, '"' => 34, "\\" => 92
  }
  index = 0
  while index < input.bytesize
    byte = input.getbyte(index)
    unless byte == 92
      output << byte
      index += 1
      next
    end

    index += 1
    raise "trailing backslash in Git path quote" if index >= input.bytesize

    escaped = input.getbyte(index).chr
    if escapes.key?(escaped)
      output << escapes.fetch(escaped)
      index += 1
      next
    end

    unless escaped.match?(/[0-7]/)
      raise "unsupported Git path escape"
    end
    octal = input.byteslice(index, 3)
    unless octal&.match?(/\A[0-7]{3}\z/)
      raise "invalid octal Git path escape"
    end
    output << octal.to_i(8)
    index += 3
  end
  output
end

def normalize_path(path)
  path = path.byteslice(2..-1) while path.start_with?("./".b)
  path
end

def private_path?(path)
  [
    ".superpowers/".b,
    "docs/superpowers/".b,
    "docs/plans/".b
  ].any? { |prefix| path.start_with?(prefix) }
end

def safe_display(path)
  output = +""
  index = 0
  while index < path.bytesize
    byte = path.getbyte(index)
    if byte < 128
      output <<
        case byte
        when 7 then "\\a"
        when 8 then "\\b"
        when 9 then "\\t"
        when 10 then "\\n"
        when 11 then "\\v"
        when 12 then "\\f"
        when 13 then "\\r"
        when 32..91, 93..126 then byte.chr
        when 92 then "\\\\"
        else format("\\x%02X", byte)
        end
      index += 1
      next
    end

    character_length =
      case byte
      when 0xC2..0xDF then 2
      when 0xE0..0xEF then 3
      when 0xF0..0xF4 then 4
      end
    character_bytes =
      character_length && path.byteslice(index, character_length)
    character =
      character_bytes&.dup&.force_encoding(Encoding::UTF_8)

    if character &&
       character.bytesize == character_length &&
       character.valid_encoding?
      if character.match?(/\p{C}/)
        character.bytes.each do |character_byte|
          output << format("\\x%02X", character_byte)
        end
      else
        output << character
      end
      index += character_length
    else
      output << format("\\x%02X", byte)
      index += 1
    end
  end
  output
end

object_paths = File.binread(ARGV.fetch(0)).lines(chomp: true).each_with_object([]) do |line, paths|
  separator = line.index(" ".b)
  next unless separator

  paths << decode_git_c_path(line.byteslice(separator + 1..-1))
end
name_paths = File.binread(ARGV.fetch(1)).split("\0".b, -1).reject(&:empty?)

offending_paths = (object_paths + name_paths)
  .map { |path| normalize_path(path) }
  .select { |path| private_path?(path) }
  .uniq
  .sort

File.open(ARGV.fetch(2), "wb") do |output|
  offending_paths.each { |path| output.puts(safe_display(path)) }
end
RUBY

if [ -s "$audit_dir/offending-paths" ]; then
  while IFS= read -r path; do
    printf 'private history path: %s\n' "$path" >&2
  done <"$audit_dir/offending-paths"
  exit 1
fi
