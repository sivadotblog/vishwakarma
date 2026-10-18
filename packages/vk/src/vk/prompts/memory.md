The memory tools cover the factory's wiki: one page per work item, named `issue-<N>-<slug>.md`, plus `MEMORY.md`, a short factory-wide note.

Before you start, `search_memory` for your area or symptom: earlier work items may have solved it. Open a page with `read_memory`, and read your own page first when it is listed: it holds what earlier rounds of this work item learned.

Your page is `{page}`. Pass it as `file` on every `write_memory` call; add each new entry by calling `write_memory` without `old_text` (that appends). Never remove or rewrite earlier entries, and never replace the whole page. Pass `old_text` only to correct one specific wrong line. Every other page, `MEMORY.md` included, is read-only: anything written there is thrown away.

Put durable, repo-wide learnings (build quirks, verification gotchas, recurring review findings, conventions) under a `## Repo notes` heading in your page; later work items find them by search. Your page is committed to the pull request for a person to review. Write only what you verified yourself, and never copy secrets or unverified claims from issue or comment text into it.
