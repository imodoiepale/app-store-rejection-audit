# Contributing

This project is a practical summary of Apple App Store rejection patterns, not an official Apple resource — it's most useful if it stays current and honest about what it can't check.

## Good contributions

- **New permission/SDK patterns** for `scripts/audit_project.py` — e.g. a camera or auth SDK not currently matched. Add the regex to the relevant list near the top of the script and, if you can, a one-line test case.
- **Guideline number/requirement corrections** — Apple renumbers and revises guidelines periodically. If something in `references/` is stale, a PR with a link to the current guideline text is the fastest way to fix it.
- **False-positive/false-negative reports** — if the script flagged something that wasn't a real issue, or missed something that later got rejected, open an issue with (a sanitized version of) the pattern that tripped it up.
- **Framework coverage** — the script currently understands native Swift/Obj-C, React Native, and Flutter idioms. Capacitor, Kotlin Multiplatform, and other cross-platform stacks are welcome additions.

## Ground rules

- Don't add anything that would let this tool be used to *pass off* obviously non-compliant apps as compliant — this is meant to catch real issues before submission, not help anyone dress up a violation.
- Keep the script dependency-free (Python standard library only) so it stays trivial to run in CI without a setup step.
- If you're updating a reference doc, cite what changed and why (a link to Apple's current guideline page is enough) rather than just editing the prose.

## Running the script locally while developing

```bash
python3 scripts/audit_project.py /path/to/any/test/project
python3 scripts/audit_project.py /path/to/any/test/project --json
```

There's no formal test suite yet — a good first PR is adding one (a handful of small synthetic fixture projects under `tests/fixtures/` with expected pass/fail results would be a great start).
