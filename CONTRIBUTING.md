# Contributing to EngramMesh

Thank you for helping improve EngramMesh. The project is currently in its architecture-approved, pre-implementation stage; please discuss material work in an issue or RFC before investing in it.

## Before opening a pull request

- Use a focused pull request. Link the issue it addresses, or the relevant RFC when the change needs one.
- Include tests and documentation for every behavior change. A defect fix must include permanent regression coverage.
- Deterministic tests must not require access to a paid model or paid service.
- Do not submit secrets, personal data, proprietary prompts, or datasets that you are not licensed to contribute and distribute.
- Review [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md), [GOVERNANCE.md](GOVERNANCE.md), and the applicable ADR or RFC process.

## Developer Certificate of Origin

Every commit must include a [Developer Certificate of Origin (DCO) 1.1](https://developercertificate.org/) sign-off. Use `git commit -s`, which adds this line to the commit message:

```text
Signed-off-by: Your Name <your.email@example.com>
```

By signing off, you certify that the contribution is your original work or that you otherwise have the right to submit it. Accepted contributions use the applicable repository license: Apache License 2.0 for code and CC BY 4.0 for documentation, unless explicitly stated otherwise.

Maintainers integrate pull requests with Rebase and Merge so each validated
DCO trailer remains in the main history. Squash Merge and Merge Commit are not used.

## Commit and review expectations

Use a Conventional Commits-style subject, for example:

```text
docs: clarify RFC review period
fix: preserve event ordering during replay
```

Keep the subject concise, imperative, and scoped to the change. Maintainers may request that unrelated changes be split into separate pull requests.

Be respectful and constructive in review. Disclose AI-assisted contributions in the pull request description, including the tools used and the human review or validation performed. You remain responsible for the submitted work, its provenance, and its license compliance.
