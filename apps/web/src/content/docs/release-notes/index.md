---
title: Release Notes
description: Current project status, milestones, and release notes.
---

This page documents the current state and capabilities of the Vishwakarma autonomous software factory.

## Current Project State

Vishwakarma is active and operates as a monorepo with the software factory package, documentation site, and backend services.

### Core Capabilities

- **Autonomous Factory Engine (`packages/vk`)**:
  - Five specialized agent clans: Classifier, Researcher, Analyst, Implementer, and Reviewer.
  - Multi-provider LLM support with PydanticAI (Anthropic Claude, Google Gemini, OpenAI GPT).
  - CLI commands: `vk issue`, `vk review`, and `vk ci-fix`.
  - Non-interactive mode with `--unattended` for runs in CI workflows.

- **GitHub Actions Workflows**:
  - Automatic workflow start on `vk` label addition (`.github/workflows/vishwakarma.yml`).
  - Strict role-based authorization for sender permissions (`admin`, `maintain`, `write`, `triage`).
  - Failure reports and automated draft pull request creation.

- **Documentation Site (`apps/web`)**:
  - Built with Astro Starlight.
  - Organized into nine standard sections: Getting Started, Concepts, How-to Guides, Advanced, Examples, Integrations, API Reference, Contribute, and Release Notes.

- **Verification Pipeline**:
  - Centralized Makefile (`make setup`, `make check`, `make format`).
  - Strict quality gates across Python (`ruff`, `mypy --strict`, `pytest`) and Web workspace (`prettier`, `astro check`, `astro build`).
