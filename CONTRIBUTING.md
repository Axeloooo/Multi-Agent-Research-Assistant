# Contributing to Multi-Agent Research Assistant

Thank you for helping improve the project. It is currently pre-alpha, so small,
well-tested changes are easier to review than large feature bundles.

By participating, you agree to follow the [Code of Conduct](CODE_OF_CONDUCT.md).

## Before you start

1. Search the open issues and pull requests for related work.
2. Open an issue before starting a large feature or architectural change.
3. Keep credentials, private research material, and generated reports out of
   commits and issue discussions.

## Local setup

Fork the repository, then clone your fork and configure the upstream remote:

```zsh
git clone https://github.com/<your-username>/Multi-Agent-Research-Assistant.git
cd Multi-Agent-Research-Assistant
git remote add upstream https://github.com/Axeloooo/Multi-Agent-Research-Assistant.git
```

Create the project and frontend environments:

```zsh
pyenv install
python -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements-dev.txt
cd frontend
npm install
cd ..
cp .env.example .env
```

The automated tests use mocks and do not require API keys. Add local Gemini or
Tavily credentials only when manually testing an integration, and never commit
them.

## Branches and commits

Create your branch from the latest `devel` branch:

```zsh
git fetch upstream
git switch devel
git pull --ff-only upstream devel
git switch -c feat/short-description
```

Open contributor pull requests against `devel`. Maintainers promote reviewed
changes from `devel` to `main`; releases are created from `main`.

Use [Conventional Commits](https://www.conventionalcommits.org/) so release
notes can be generated consistently. Common prefixes include:

- `feat:` for new behavior
- `fix:` for bug fixes
- `docs:` for documentation-only changes
- `test:` for test changes
- `chore:` for maintenance

## Development standards

- Keep agents, tools, pipelines, and interfaces separated by responsibility.
- Add type hints and concise docstrings to public Python interfaces.
- Write a failing test before changing production behavior.
- Mock Gemini, Tavily, and HTTP calls in the default test suite.
- Do not make tests depend on API keys, external services, or the network.
- Update documentation when commands, configuration, or behavior changes.

Run the full local quality gate before pushing:

```zsh
black --check .
flake8 .
pytest

cd frontend
npm run format
npm run lint
npm test
npm run build
npm run build-storybook
```

Run `npx playwright install chromium` once, then use `npm run test:e2e` for the
offline browser test. It starts a real local FastAPI API with a deterministic
fake pipeline; it never uses provider credentials or the network.

Apply formatters with `black .` and `cd frontend && npm run format:write`, then
repeat the checks.

## Pull request checklist

Before requesting review, confirm that:

- [ ] The change has a focused purpose and targets `devel`.
- [ ] Commit messages follow Conventional Commits.
- [ ] New or changed behavior is covered by tests.
- [ ] Tests do not use live network calls or real credentials.
- [ ] Black, Flake8, and pytest pass locally.
- [ ] Prettier, ESLint, Vitest, the frontend build, and Storybook pass locally.
- [ ] Playwright passes for UI or API streaming changes.
- [ ] Coverage remains at or above 80% for `src`.
- [ ] User-facing documentation is accurate.
- [ ] The pull request explains the change and how it was verified.

## Reporting conduct concerns

Do not place sensitive conduct reports in a public issue. Follow the private
reporting guidance in [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md).
