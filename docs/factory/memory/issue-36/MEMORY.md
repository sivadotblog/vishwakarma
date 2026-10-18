- Issue #36 triaged: Non-duplicate documentation request to rewrite root README.md following six specified sections based on facts in AGENTS.md, Makefile, and packages/vk/README.md. Proceeding with 'documentation' label.

- Classified issue #36 as type=chore, priority=medium, complexity=small, affected_area=documentation.
- Verified root README.md current status (2 lines) and requirements. Verified AGENTS.md, Makefile, packages/vk/README.md, and LICENSE for facts, commands, and links. Drafted 6-section structure (~45 lines) meeting all constraints.
- Created feature branch `vk/chore-root-readme`.
- Rewrote root `README.md` into 40 lines containing all 6 required sections with verified relative links (`packages/vk/README.md#run-on-prefect`, `LICENSE`).
- Ran `make setup` and `make check` - all linting, typechecking, pytest tests (245 passed), web linting, astro checking, and astro building passed cleanly.
- Confirmed git diff shows only `README.md` modified.
