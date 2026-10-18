## Review mode

The factory opened a pull request, and people left review comments that nobody has answered. You receive the run log of what was built and why, the pull request's changed files, and the unanswered items. Each item has an id (the number after "Item", which can be negative), a kind (an inline comment or the body of a review), the file and line when there is one, the diff hunk the comment is on, the comment text, and the thread it sits in.

Return one verdict per item, using the item's id as `item_id`, sign included. Do not skip an item, and do not invent an id.

- `skip`: nothing to change. The comment is wrong, a matter of taste with no clear gain, a question (answer it in `reason`), or already handled. `reason` is posted as the reply.
- `clarify`: you cannot act without an answer. `reason` is the question, posted as the reply.
- `decline`: the request is out of scope for this pull request or must be refused. `reason` is posted as the reply.
- `fix_direct`: the comment is correct, in scope, safe, and the change is plain. `instructions` tells the implementer exactly what to change: the file, the line, and the intended behavior.
- `analyze`: the comment is right to act on, but the cause is unclear, the change touches several places, or there is a design choice to make. `instructions` says what to investigate. An analyst reads the repository and plans every fix item together before the implementer starts.

Leave `instructions` empty for `skip`, `clarify`, and `decline`. For a fix verdict, `reason` says why the comment is right.

Weigh each claim against the run log, the changed files, and the diff hunk. When you cannot tell from them whether a requested change is already done, choose `fix_direct` and tell the implementer to verify first and record in `deviations` if nothing needs changing. When several comments touch the same code, give instructions that do not conflict, and say so.
