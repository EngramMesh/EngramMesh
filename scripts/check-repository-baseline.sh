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
"

for path in $required_files; do
  if [ ! -s "$path" ]; then
    printf 'missing or empty: %s\n' "$path" >&2
    exit 1
  fi
done

if ! grep -q "Apache License" LICENSE; then
  printf 'LICENSE is not Apache License 2.0\n' >&2
  exit 1
fi

if ! grep -q "git commit -s" CONTRIBUTING.md; then
  printf 'CONTRIBUTING.md does not enforce DCO sign-off\n' >&2
  exit 1
fi

for ignored_path in .superpowers/sdd/probe docs/superpowers/probe; do
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
