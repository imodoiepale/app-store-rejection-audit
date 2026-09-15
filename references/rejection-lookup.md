# Looking up a real rejection — the `appstore-rejections-mcp` server

This repository ships knowledge and scanners. It does not ship a case database. When a rejection notice arrives, the fastest source of "what cleared this for other developers" is [robertojoseph/appstore-rejections-mcp](https://github.com/robertojoseph/appstore-rejections-mcp): an MCP server over a hosted database of **48 rejection reasons, 51 solutions, 554 real-world cases and all 130 guideline subsections**.

It is an optional runtime dependency. Nothing in this repository imports it; the skill only tells Claude when to reach for it.

## Install

Claude Code, project or user scope:

```bash
claude mcp add --transport stdio appstore-rejections -- npx -y appstore-rejections-mcp
```

Any other MCP client:

```json
{
  "mcpServers": {
    "appstore-rejections": {
      "command": "npx",
      "args": ["-y", "appstore-rejections-mcp"]
    }
  }
}
```

Requires Node 18+. The server talks to a public Supabase instance; no key is needed for reads.

## Which tool for which moment

| Situation | Tool | Input |
|---|---|---|
| A rejection notice was pasted | `search_rejections` | The reviewer's paragraph, verbatim |
| The notice names a guideline number | `get_guideline` | `"3.1.2"`, `"5.1.1"`, `"4.3"` |
| You know the reason id and want the fix | `get_solutions` | The reason id from `search_rejections` |
| You want to see how it ended for others | `get_cases` | Reason id, app category, or appeal status |
| Pre-submission, "what do apps like this get hit with?" | `list_common_rejections` | none |
| Full detail on one reason | `get_rejection_reason` | Reason id |

## How to use it inside the audit workflow

1. Run `audit_project.py` first. Its findings are grounded in the repo; the case database is grounded in other people's repos.
2. For each FAIL or WARN with a guideline number, call `get_guideline` for the current text, then `get_cases` filtered to the app's category to see the typical fix and whether appeals worked.
3. When the user pastes a notice, `search_rejections` with the verbatim text, then map each returned reason back to a check id in `audit_project.py` and confirm it against the code before advising.
4. Quote the case outcome, not only the guideline: "three of five voice apps that hit 5.1.2(i) cleared it by naming the vendor on the consent screen" is what changes a decision.

## Caveats

- The database is community-curated and not official. Treat success rates as anecdotes with a sample size, not statistics.
- It lags the guidelines by weeks after a November update. Cross-check `get_guideline` output against <https://developer.apple.com/app-store/review/guidelines/> for anything load-bearing.
- Do not paste demo credentials, customer data or unreleased product details into `search_rejections`; the query leaves your machine.
