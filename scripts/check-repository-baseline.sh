#!/bin/sh
set -eu

required_files="
LICENSE
NOTICE
README.md
README.zh-CN.md
CONTRIBUTING.md
CODE_OF_CONDUCT.md
SECURITY.md
SUPPORT.md
GOVERNANCE.md
ROADMAP.md
TRADEMARKS.md
CHANGELOG.md
THIRD_PARTY_NOTICES.md
.gitattributes
.gitignore
docs/LICENSE
docs/architecture/engrammesh-production-architecture.md
docs/adr/README.md
docs/rfcs/README.md
.github/CODEOWNERS
.github/PULL_REQUEST_TEMPLATE.md
.github/ISSUE_TEMPLATE/bug.yml
.github/ISSUE_TEMPLATE/feature.yml
.github/ISSUE_TEMPLATE/config.yml
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
"

for path in $required_files; do
  if [ ! -s "$path" ]; then
    printf 'missing or empty: %s\n' "$path" >&2
    exit 1
  fi
done

required_executables="
scripts/install-policy-tools.sh
scripts/check-dco.sh
scripts/check-markdown-links.sh
scripts/check-community-yaml.rb
scripts/check-private-history.sh
scripts/check-workflow-policy.rb
scripts/test-repository-policy.sh
scripts/check-repository-policy.sh
"

for path in $required_executables; do
  if [ ! -x "$path" ]; then
    printf 'not executable: %s\n' "$path" >&2
    exit 1
  fi
done

if ! ruby <<'RUBY'
# This is a bounded lexer for command-shaped POSIX shell source, not a full
# shell parser. Runtime fixtures under a PATH without ripgrep are the backstop
# for executable forms outside this static detector's scope.
def shell_tokens(source)
  tokens = []
  word = +""
  word_started = false
  quote = nil
  index = 0

  emit_word = lambda do
    if word_started
      tokens << word
      word = +""
      word_started = false
    end
  end

  while index < source.length
    character = source[index]

    if quote == :single
      if character == "'"
        quote = nil
      else
        word << character
      end
      index += 1
      next
    end

    if quote == :double
      if character == '"'
        quote = nil
        index += 1
        next
      end
      if character == "\\" && index + 1 < source.length
        following = source[index + 1]
        if ["$", "`", '"', "\\", "\n"].include?(following)
          word << following unless following == "\n"
          index += 2
          next
        end
      end
      word << character
      index += 1
      next
    end

    case character
    when "'"
      quote = :single
      word_started = true
      index += 1
    when '"'
      quote = :double
      word_started = true
      index += 1
    when "\\"
      word_started = true
      if index + 1 < source.length
        following = source[index + 1]
        word << following unless following == "\n"
        index += 2
      else
        word << character
        index += 1
      end
    when "#"
      if word_started
        word << character
        index += 1
      else
        newline = source.index("\n", index)
        if newline
          tokens << "\n"
          index = newline + 1
        else
          index = source.length
        end
      end
    when " ", "\t", "\r"
      emit_word.call
      index += 1
    when "\n"
      emit_word.call
      tokens << character
      index += 1
    when ";", "|", "&", "(", ")", "{", "}"
      emit_word.call
      if ["|", "&"].include?(character) &&
          source[index + 1] == character
        tokens << character * 2
        index += 2
      else
        tokens << character
        index += 1
      end
    else
      word_started = true
      word << character
      index += 1
    end
  end

  emit_word.call
  tokens
end

target_command = "r" + "g"
command_leaders = %w[if then elif else while until do ! run: -].freeze
command_boundaries = ["\n", ";", "&&", "||", "|", "&", "(", ")", "{", "}"].freeze
assignment = /\A[A-Za-z_][A-Za-z0-9_]*=/

paths =
  Dir.glob("scripts/**/*.sh").sort +
  Dir.glob(".github/workflows/**/*.{yml,yaml}").sort

paths.each do |path|
  command_position = true
  shell_tokens(File.read(path)).each do |token|
    if command_boundaries.include?(token)
      command_position = true
      next
    end
    next unless command_position
    next if command_leaders.include?(token)
    next if assignment.match?(token)
    next if token == "command"

    exit 1 if token == target_command
    command_position = false
  end
end
RUBY
then
  printf 'public policy files must not invoke ripgrep\n' >&2
  exit 1
fi

if ! grep -q "Apache License" LICENSE; then
  printf 'LICENSE is not Apache License 2.0\n' >&2
  exit 1
fi

if ! grep -q "git commit -s" CONTRIBUTING.md; then
  printf 'CONTRIBUTING.md does not enforce DCO sign-off\n' >&2
  exit 1
fi

if ! awk '
  {
    current = $0
    sub(/\r$/, "", current)
    if (previous == "Maintainers integrate pull requests with Rebase and Merge so each validated" &&
        current == "DCO trailer remains in the main history. Squash Merge and Merge Commit are not used.") {
      found = 1
    }
    previous = current
  }
  END { exit found ? 0 : 1 }
' CONTRIBUTING.md; then
  printf 'CONTRIBUTING.md does not require rebase-only DCO integration\n' >&2
  exit 1
fi

for ignored_path in \
  .superpowers \
  docs/superpowers \
  docs/plans \
  .superpowers/sdd/probe \
  .superpowers/specs/probe \
  .superpowers/plans/probe \
  docs/superpowers/probe \
  docs/plans/probe
do
  if ! git check-ignore -- "$ignored_path" >/dev/null 2>&1; then
    printf 'expected ignored local artifact path is not ignored: %s\n' "$ignored_path" >&2
    exit 1
  fi
done

if git ls-files -ci --exclude-standard | grep . >/dev/null 2>&1; then
  printf 'an ignored local artifact is tracked\n' >&2
  exit 1
fi

printf 'repository baseline: ok\n'
