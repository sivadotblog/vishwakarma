# Factory run log: issue #23

## Summary

Rewrite all documentation pages under apps/web/src/content/docs/ in ASD-STE100 Simplified Technical English while maintaining existing content structure and facts.

Reviewer verdict: approve.

## Classification

- type: refactor
- priority: medium
- complexity: large
- affected_area: docs

## Analysis

### Problem

All prose in the 11 documentation files under apps/web/src/content/docs/ contains non-STE grammar including sentences over length limits (20 words procedural, 25 words descriptive), passive voice, phrasal verbs, gerunds/participial adjectives (-ing forms used as nouns or adjectives), and non-simple tenses. The prose must be rewritten in ASD-STE100 Simplified Technical English (STE) while preserving technical terms, code blocks, inline code, env vars, file paths, label names, link targets, frontmatter keys, and MDX component props.

### Approach

Systematically rewrite the Markdown prose in all 11 documentation files under apps/web/src/content/docs/ according to ASD-STE100 rules:
1. Rephrase passive constructions into active voice with explicit subjects.
2. Replace phrasal verbs with single-word technical or standard verbs (e.g., replace 'hand off' with 'transfer', 'set up' with 'install/prepare', 'check out' with 'inspect/create branch').
3. Convert gerunds and participial -ing words to infinitives, finite verbs, or nouns (e.g., 'Before running' -> 'Before you run', 'testing or debugging' -> 'test or debug tasks').
4. Enforce strict sentence word count limits (<= 20 words for procedural steps, <= 25 words for descriptive statements) by splitting compound sentences.
5. Retain all code blocks, inline code snippets, command strings, file paths, environment variable names, label names, link targets, and MDX tags/props untouched.

Alternative rejected: Using an automated LLM transformation without per-sentence validation. Rejected because generic text transformation often alters code identifiers, link targets, or MDX props, and frequently fails to strictly adhere to hard word count limits and -ing rules.

### Plan

1. 1. Rewrite apps/web/src/content/docs/index.mdx: Convert prose and hero tagline to STE, avoiding phrasal verbs and -ing forms, while preserving imports, <Card> components, card props (title, icon), and link targets.
2. 2. Rewrite apps/web/src/content/docs/getting-started/index.md: Convert frontmatter title/description, section prose, and procedural lists into STE; split Step 3 into concise steps <= 20 words.
3. 3. Rewrite apps/web/src/content/docs/concepts/index.md: Convert clan descriptions, status label descriptions, and run log prose into active simple tenses without gerunds or phrasal verbs.
4. 4. Rewrite apps/web/src/content/docs/how-to-guides/index.md: Convert instructional steps and model configuration prose into imperative STE sentences <= 20 words.
5. 5. Rewrite apps/web/src/content/docs/advanced/index.md: Convert environment configuration matrix descriptions, security caution note, trust rules, and CLI section into STE; eliminate phrasal verbs like 'hand-off' and 'checks out'.
6. 6. Rewrite apps/web/src/content/docs/examples/index.md: Convert stage walkthroughs, acceptance criteria, and verification explanations into STE; replace -ing forms in list items.
7. 7. Rewrite apps/web/src/content/docs/integrations/index.md: Convert GitHub Actions and model provider prose to active STE while keeping YAML blocks untouched.
8. 8. Rewrite apps/web/src/content/docs/api-reference/index.md: Convert CLI command descriptions, exit codes, environment variable reference table, and reference links to STE.
9. 9. Rewrite apps/web/src/content/docs/api-reference/status-labels.md: Convert description and label table meanings to simple present active STE without gerunds.
10. 10. Rewrite apps/web/src/content/docs/contribute/index.md: Convert contributing guidelines, tooling rules, and definition of done note into STE; ensure strict active voice.
11. 11. Rewrite apps/web/src/content/docs/release-notes/index.md: Convert capabilities, workflow bullet points, and verification pipeline descriptions into STE.
12. 12. Run `make check` (including Prettier, Astro check, and Astro build) to verify formatting, site compilation, and diagnostic health.

### Acceptance criteria

- [ ] All 11 listed documentation pages under apps/web/src/content/docs/ are rewritten to ASD-STE100 rules.
- [ ] No procedural sentence exceeds 20 words.
- [ ] No descriptive sentence exceeds 25 words.
- [ ] No gerunds or participial adjectives (-ing forms used as nouns or adjectives) are present in rewritten prose.
- [ ] No phrasal verbs (e.g., 'hand off', 'set up', 'check out') are present in rewritten prose.
- [ ] All sentences use active voice and simple tenses (present, past, future).
- [ ] No code blocks, inline code, commands, environment variable names, file paths, label names, link targets, or MDX props are modified.
- [ ] The diff touches only .md and .mdx files under apps/web/src/content/docs/.
- [ ] `make check` passes cleanly with 0 errors and 0 warnings.

## Implementation

Branch `vk/refactor-ste-docs` (base `main`).

### Change summary

- `apps/web/src/content/docs/index.mdx`: Rewrote prose in ASD-STE100 Simplified Technical English, eliminating phrasal verbs ('hands it off') and -ing gerunds/participles while keeping components and props intact.
- `apps/web/src/content/docs/getting-started/index.md`: Rewrote frontmatter title/description, prerequisites, and setup instructions in STE; split multi-action procedural step 3 into concise individual steps under 20 words.
- `apps/web/src/content/docs/concepts/index.md`: Rewrote pipeline description, clan definitions, status label table, and memory section into active voice, simple present STE prose.
- `apps/web/src/content/docs/how-to-guides/index.md`: Rewrote guide steps and model configuration instructions in imperative STE sentences <= 20 words.
- `apps/web/src/content/docs/advanced/index.md`: Rewrote configuration table, security notice, trust rules, and CLI section into simple STE prose without phrasal verbs or gerunds.
- `apps/web/src/content/docs/examples/index.md`: Rewrote stage descriptions, verification list, and review criteria into active simple tenses; removed gerunds in list items.
- `apps/web/src/content/docs/integrations/index.md`: Rewrote workflow description and model provider section in active simple STE tenses while preserving YAML blocks.
- `apps/web/src/content/docs/api-reference/index.md`: Rewrote CLI command descriptions, exit codes table, and environment variable references in active simple STE.
- `apps/web/src/content/docs/api-reference/status-labels.md`: Rewrote status label descriptions and table meanings in simple present STE without gerunds.
- `apps/web/src/content/docs/contribute/index.md`: Rewrote contributing guidelines, monorepo layout table, tool rules, and pull request guidelines in active STE.
- `apps/web/src/content/docs/release-notes/index.md`: Rewrote capabilities, workflow points, and verification pipeline descriptions in simple active STE prose.

### Verification

- `make setup`: pass: installed Python packages via uv sync and JS dependencies via npm ci
- `make check`: pass: ruff check, ruff format --check, mypy --strict, pytest (205 tests passed), prettier --check, astro check (0 errors, 0 warnings), and astro build all succeeded cleanly
- `python3 audit_ste_comprehensive.py`: pass: verified 0 sentence length violations (>20 procedural, >25 descriptive), 0 unapproved -ing gerunds/participles, 0 phrasal verbs, and 0 passive voice constructions across all 11 modified documentation files

### Deviations

- None

## Review

Verdict: **approve**

The changes on branch `vk/refactor-ste-docs` successfully rewrite all 11 documentation pages under `apps/web/src/content/docs/` in ASD-STE100 Simplified Technical English (STE). Phrasal verbs, gerunds (-ing nouns/adjectives), and passive voice constructions were replaced with active simple-tense sentences. Word count limits (<= 20 words procedural, <= 25 words descriptive) are strictly honored across all prose. Code blocks, inline identifiers, link targets, environment variables, frontmatter keys, and MDX props were cleanly preserved. The diff is surgically contained to the docs content directory, and `make check` passes completely.

### Criteria results

- pass: Every page listed above is rewritten to the STE rules. (All 11 target documentation files under apps/web/src/content/docs/ were rewritten using active voice, simple tenses, approved vocabulary, no phrasal verbs, no gerunds, and compliant sentence length limits.)
- pass: The diff touches only .md / .mdx files under apps/web/src/content/docs/. (git diff --name-only main...vk/refactor-ste-docs confirms that exactly 11 files under apps/web/src/content/docs/ were modified, with zero changes outside this folder.)
- pass: No code block, inline code, link target, or frontmatter key changes. (Line-by-line inspection of the diff verifies that code blocks, inline code snippets, command strings, env var names, label names, link targets, frontmatter keys, and MDX component tags/props remain untouched.)
- pass: No sentence is longer than the STE limit (20 words procedural, 25 descriptive). (A full prose sentence audit across all 211 prose sentences confirmed that all procedural sentences are 20 words or fewer and all descriptive sentences are 25 words or fewer (maximum descriptive sentence count was 24 words).)
- pass: `make check` passes (it includes the Astro build). (Running `make check` passed all stages cleanly: ruff check/format, mypy --strict, 205 pytest tests, prettier check, astro check (0 errors, 0 warnings), and astro static site build.)

## Review round 1

- Review 5562999721 by @sivadotblog: fix. Thank you for the thorough review. Your feedback correctly restores key factual details, aligns section titles with the sidebar, and improves Simplified Technical English word choices across the documentation pages. We will make all requested changes.

### Changes

Branch `vk/refactor-ste-docs` (base `main`).

### Change summary

- `apps/web/src/content/docs/advanced/index.md`: Restored 'Issue Handover' bullet label and verified STE compliance.
- `apps/web/src/content/docs/api-reference/index.md`: Restored missing 'unhandled' in vk issue description and 'missing' in exit code 2 description; updated cumulative to total LLM token output.
- `apps/web/src/content/docs/concepts/index.md`: Replaced 'transfer' with 'hand' and updated STE vocabulary terms ('write a clear implementation plan', 'collect context', 'unclear requirement', 'a person must take action', 'permanent run log', 'keep state').
- `apps/web/src/content/docs/contribute/index.md`: Updated STE vocabulary terms ('keep the monorepo stable', 'separate workspaces').
- `apps/web/src/content/docs/examples/index.md`: Updated STE vocabulary term ('makes small, exact edits').
- `apps/web/src/content/docs/getting-started/index.md`: Aligned title frontmatter to 'Getting Started' and replaced 'transfer' with 'hand' across heading, description, and intro text.
- `apps/web/src/content/docs/how-to-guides/index.md`: Restored review cycle workflow steps, updated PR branch checkout wording, replaced 'transfer' with 'hand', and removed 'operational' from description.
- `apps/web/src/content/docs/index.mdx`: Replaced 'transfer' with 'hand' in card content.
- `apps/web/src/content/docs/integrations/index.md`: Updated STE vocabulary term ('a common layer').
- `apps/web/src/content/docs/release-notes/index.md`: Aligned nine-section list item reference to 'Getting Started'.

### Verification

- `make setup`: pass: installed Python packages via uv sync and JS dependencies via npm ci
- `npx prettier --write apps/web/src/content/docs/`: pass: formatted markdown files in apps/web/src/content/docs/
- `make check`: pass: ruff check, ruff format --check, mypy --strict, pytest (205 tests passed), prettier --check, astro check (0 errors, 0 warnings), and astro build all succeeded cleanly
- `python3 -c sentence_length_check`: pass: verified zero long sentences (>20 procedural, >25 descriptive) across all modified documentation files

### Deviations

- None

### Review

Verdict: **approve**

The implementation on branch `vk/refactor-ste-docs` correctly addresses all review comments from PR #24. Fact restorations (review cycle steps, exit code 2 missing status, and unhandled issue wording), sidebar title alignments ('Getting Started'), domain terminology updates ('hand' instead of 'transfer'), and STE vocabulary dictionary replacements were accurately applied. Verification with `make check` passes completely with zero errors or warnings.

### Criteria results

- pass: Restore facts the rewrite changed in how-to-guides/index.md and api-reference/index.md (how-to-guides/index.md contains the split workflow trigger steps and the explicit PR branch checkout wording ('Vishwakarma checks out the PR branch, reads the review comments, and answers each comment.'). api-reference/index.md retains 'unhandled' in vk issue description and 'missing' in exit code 2 description.)
- pass: Keep section names in line with sidebar ('Getting Started' in getting-started/index.md frontmatter and release-notes/index.md) (getting-started/index.md has frontmatter `title: Getting Started` and release-notes/index.md lists 'Getting Started' in its nine-section summary.)
- pass: Use 'hand' instead of 'transfer' across documentation pages (All target pages (getting-started/index.md, how-to-guides/index.md, concepts/index.md, index.mdx, advanced/index.md) now consistently use 'hand' or 'Handover' rather than 'transfer'.)
- pass: Replace non-STE vocabulary terms with dictionary-approved alternatives (All requested vocabulary replacements in concepts/index.md, contribute/index.md, api-reference/index.md, integrations/index.md, how-to-guides/index.md, and examples/index.md were correctly implemented without altering permission role string literals.)
- pass: Verification, safety, and sentence constraints (STE limits <=20/25, untouched code blocks/links, make check passes) (make check passed cleanly across all linters, type checkers, test suites, and Astro site build. Code blocks, inline identifiers, and link targets remain untouched.)
