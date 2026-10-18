# Factory run log: issue #33

## Summary

Add a short section to the home page (apps/web/src/content/docs/index.mdx) explaining the name Vishwakarma in Simplified Technical English.

Reviewer verdict: approve.

## Classification

- type: feature
- priority: low
- complexity: trivial
- affected_area: apps/web/docs

## Analysis

### Problem

Add a new section titled 'Why the name Vishwakarma' to the home page (`apps/web/src/content/docs/index.mdx`) explaining the origin and meaning of the name Vishwakarma in ASD-STE100 Simplified Technical English (short sentences, active voice, one fact per sentence, approved words, 4–6 sentences), without modifying existing page content or breaking project verification checks.

### Approach

Append a `## Why the name Vishwakarma` section after the `<CardGrid>` component in `apps/web/src/content/docs/index.mdx`. The text consists of 6 active-voice, short sentences complying with ASD-STE100 Simplified Technical English rules (one fact per sentence, simple active verbs, no passive constructions like 'is credited with'). The alternative of using passive phrasing or combining facts into complex compound sentences was rejected to adhere strictly to ASD-STE100 rules.

### Plan

1. Run `make setup` to ensure web workspace node_modules and Prettier binaries are installed.
2. Edit `apps/web/src/content/docs/index.mdx` to append the `## Why the name Vishwakarma` section at the end of the file using 6 ASD-STE100 compliant active-voice sentences.
3. Format `apps/web/src/content/docs/index.mdx` using Prettier (`npx prettier --write apps/web/src/content/docs/index.mdx`).
4. Run `make check` from the repository root to verify that Python checks, web Prettier linting (`npm run lint -w web`), Astro check (`npm run check -w web`), and Astro site build (`npm run build -w web`) all succeed without errors.

### Acceptance criteria

- [x] apps/web/src/content/docs/index.mdx contains a heading titled '## Why the name Vishwakarma'
- [x] The section contains 4–6 sentences written in active voice according to ASD-STE100 Simplified Technical English standards
- [x] The section covers both the mythological background (chief architect, cities/palaces/weapons/chariots, Dwarka/Lanka/Indraprastha) and its role in this repository (takes an issue and builds a pull request from start to finish)
- [x] All existing sections and <CardGrid> components on index.mdx remain unmodified
- [x] `make check` passes cleanly, including Prettier linting, astro check, and astro build

## Implementation

Branch `vk/feature-explain-vishwakarma-name` (base `main`).

### Change summary

- `apps/web/src/content/docs/index.mdx`: Added a 'Why the name Vishwakarma' section written in active-voice ASD-STE100 Simplified Technical English explaining the mythological origins and the factory's role.

### Verification

- `make setup`: pass - successfully installed uv and npm workspace dependencies
- `npx prettier --write apps/web/src/content/docs/index.mdx`: pass - formatted apps/web/src/content/docs/index.mdx according to Prettier standards
- `make check`: pass - all linting, mypy typechecking, pytest (229 tests passed), web Prettier check, astro check (0 errors, 0 warnings), and astro build passed cleanly

### Deviations

- None

## Review

Verdict: **approve**

The implementation successfully adds the 'Why the name Vishwakarma' section to `apps/web/src/content/docs/index.mdx`. The text follows ASD-STE100 Simplified Technical English standards with 6 active-voice sentences, covering both mythological context and VK's software factory role without modifying existing page content. Verification via `make check` (including Prettier, Astro check, and Astro build) passes cleanly.

### Criteria results

- pass: apps/web/src/content/docs/index.mdx contains a heading titled '## Why the name Vishwakarma' (`git diff` confirms line 30 of `apps/web/src/content/docs/index.mdx` introduces `## Why the name Vishwakarma`.)
- pass: The section contains 4–6 sentences written in active voice according to ASD-STE100 Simplified Technical English standards (The added section contains 6 short, active-voice sentences adhering to ASD-STE100 principles (one fact per sentence, simple active verbs): 'In Hindu tradition, Vishwakarma is the chief architect of the gods. He designed and built their cities, palaces, weapons, and chariots. The best-known stories describe his work on Dwarka, Lanka, and Indraprastha. VK has the same job in this repository. It takes a request from an issue. It builds a pull request from start to finish.')
- pass: The section covers both the mythological background (chief architect, cities/palaces/weapons/chariots, Dwarka/Lanka/Indraprastha) and its role in this repository (takes an issue and builds a pull request from start to finish) (The text covers the chief architect role, designed cities/palaces/weapons/chariots, stories describing work on Dwarka/Lanka/Indraprastha, and VK's repository role of taking a request from an issue and building a pull request from start to finish.)
- pass: All existing sections and <CardGrid> components on index.mdx remain unmodified (`git diff` shows zero edits or deletions in lines 1-28 of `apps/web/src/content/docs/index.mdx`.)
- pass: `make check` passes cleanly, including Prettier linting, astro check, and astro build (Ran `make setup` and `make check`: python checks, pytest (229 tests), Prettier check, astro check (0 errors, 0 warnings), and astro build (12 pages built) all passed with zero errors.)
