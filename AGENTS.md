# AGENTS.md

## Repository context

Multi-Agent Research Assistant is a pre-alpha Python project for a planned
Gemini- and Tavily-powered research workflow. Do not describe planned behavior
as implemented. The intended stages are Search, Reader, Writer, and Critic,
with future CLI and Streamlit interfaces.

## Architecture boundaries

- Keep external retrieval and extraction adapters in `src/tools/`.
- Keep agent construction and prompts in `src/agents/`.
- Keep cross-agent sequencing and state in `src/pipelines/`.
- Keep CLI and UI entry points thin; business logic belongs under `src/`.
- Prefer small, typed interfaces over shared mutable state.

## Setup and verification

Use Python 3.14.7 from `.python-version` and the repository virtual
environment:

```zsh
python -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements-dev.txt
```

Before declaring work complete, run:

```zsh
black --check .
flake8 .
pytest
```

Black is the only formatter. Flake8 is the linter. Do not introduce Ruff,
isort, uv, or a lockfile without an approved tooling change. Maintain at least
80% line coverage across `src`.

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

- Contributor branches start from and merge into `devel`.
- Maintainers promote reviewed changes from `devel` to `main`.
- Use Conventional Commit prefixes so semantic-release can classify changes.
- Do not push, merge, publish, or create releases without explicit approval.

## Code review rules

- Flag any claim that an unimplemented feature works.
- Flag live-network tests, committed secrets, and logs that could expose keys.
- Require tests for changes to agent prompts, tool behavior, pipeline state, or
  error handling.
- Confirm documentation commands match the repository before approval.
