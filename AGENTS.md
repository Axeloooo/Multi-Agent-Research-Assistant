# AGENTS.md

## Repository context

Multi-Agent Research Assistant is a Beta, local-first Gemini- and
Tavily-powered research workflow. Search, Reader, Writer, and Critic run
through a typed backend and stream safe status, activity, and output updates to
the frontend. Do not describe planned work such as durable storage,
authentication, citations, or evaluations as implemented.

## Architecture boundaries

- Keep external retrieval and extraction adapters in
  `backend/src/research_assistant/tools/`.
- Keep agent construction and prompts in `backend/src/research_assistant/agents/`.
- Keep cross-agent sequencing and state in
  `backend/src/research_assistant/pipelines/`.
- Keep API entry points thin; backend logic belongs under
  `backend/src/research_assistant/` and UI logic under `frontend/src/`.
- Keep backend tests in `backend/tests/{agents,api,pipelines,tools}/` and
  frontend tests in `frontend/tests/{unit,e2e}/`.
- Prefer small, typed interfaces over shared mutable state.

## Setup and verification

Use Python 3.14.7 from `backend/.python-version` and the backend virtual
environment:

```zsh
cd backend
python -m venv .venv
.venv/bin/python -m pip install -r requirements-dev.txt
```

Before declaring work complete, run:

```zsh
cd backend && .venv/bin/black --check .
cd backend && .venv/bin/flake8 .
cd backend && .venv/bin/pytest
```

Black is the only formatter. Flake8 is the linter. Do not introduce Ruff,
isort, uv, or a lockfile without an approved tooling change. Maintain at least
80% line coverage across `backend/src/research_assistant`.

## Change discipline

- Use test-driven development for behavior changes: red, green, then refactor.
- Test public behavior and failure modes rather than implementation details.
- Mock Gemini, Tavily, and HTTP boundaries; default tests must be offline and
  credential-free.
- Preserve `web_search(query: str) -> str` and `scrape_url(url: str) -> str`
  unless an approved design changes those tool contracts.
- Keep user-facing errors concise and safe; never expose credentials.
- Update README and contributor guidance whenever commands, configuration, or
  project status changes.

## Secrets and research data

- Never commit `.env`, API keys, private URLs, downloaded personal data, or
  generated reports containing sensitive information.
- Keep only variable names and safe examples in `.env.example`.
- Do not add live API calls to CI or the default test suite.

## Git workflow

- Contributor branches start from and merge into `devel`; use `feature/` or
  `fix/` branch prefixes.
- Maintainers promote reviewed changes from `devel` to `main`.
- Use Conventional Commit prefixes so semantic-release can classify changes.
- Do not push, merge, publish, or create releases without explicit approval.

## Code review rules

- Flag any claim that an unimplemented feature works.
- Flag live-network tests, committed secrets, and logs that could expose keys.
- Require tests for changes to agent prompts, tool behavior, pipeline state, or
  error handling.
- Confirm documentation commands match the repository before approval.
