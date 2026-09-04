# Backend Runtime and Live Agent Activity Design

## Goal

Turn the repository into a clear `backend/` and `frontend/` split, make every
agent stage bounded and observable, and show safe live operational updates in
the command-center UI.

## Status and scope

The project is a Beta local research assistant. It supports a local FastAPI
runtime and Vite UI; production durability, multi-user authorization, and
credential-free live provider operation are outside this change.

## Repository layout

All Python runtime code and its Python-specific configuration move beneath
`backend/`; no Python application package, test, dependency list, Python
version file, or executable entry point remains at the repository root.

```text
backend/
├── .env.example
├── .flake8
├── .python-version
├── pyproject.toml
├── requirements.txt
├── requirements-dev.txt
├── main.py
├── src/research_assistant/
│   ├── agents/
│   ├── api/
│   ├── pipelines/
│   └── tools/
└── tests/
    ├── agents/
    ├── api/
    ├── pipelines/
    └── tools/

frontend/
├── src/
└── tests/
    ├── e2e/
    └── unit/
```

The backend package is named `research_assistant`, not `backend`, so imports
describe the application rather than the deployment boundary. `backend/api`
remains a thin HTTP adapter; agent construction, tools, and sequencing are
separate packages inside the same backend runtime.

Root-level files remain only when they are repository-wide: Git metadata,
GitHub workflows, project README, license, code of conduct, contributor guide,
and Codex instructions. Root documentation commands explicitly `cd backend`
or `cd frontend` before invoking their respective tooling.

## Bounded execution and failure model

The existing Search-stage behavior is unbounded: it emits `search: running`
then awaits the LangChain agent. Tavily's `search()` has its own 60-second
default, but that does not impose a pipeline deadline and provider/model work
can still block after it.

The backend introduces `StageTimeouts` with these defaults:

| Stage | Deadline |
| --- | --- |
| Search | 45 seconds |
| Reader | 45 seconds |
| Writer | 90 seconds |
| Critic | 45 seconds |

`web_search()` passes a 30-second timeout to Tavily. Each pipeline stage is
also wrapped by its declared asynchronous deadline. On timeout, the pipeline
emits the active agent's `failed` status, marks later agents `skipped`, and
emits a concise safe `run.failed` message. The registry receives the terminal
event, closes the SSE stream, and starts the next queued run.

Cancellation remains explicit. The registry may cancel its task immediately;
the pipeline observes cancellation between emitted events. A cancelled thread
cannot terminate an already-running synchronous provider call, but it cannot
publish late output to a terminal run and no longer blocks the single-run queue.

## Live activity contract

The pipeline extends its safe domain event union with `agent.activity`:

```json
{
  "type": "agent.activity",
  "agent": "search",
  "payload": {
    "kind": "thinking",
    "label": "Planning the research query"
  }
}
```

Allowed activity kinds are `thinking`, `using_tool`, `observing`, and
`streaming`. Labels are application-owned, short, and safe. They never include
prompts, model reasoning, tool arguments, raw tool results, provider metadata,
or exception text.

The Search and Reader LangChain calls receive a run-scoped callback handler.
The callback uses the event loop's thread-safe scheduling API to send only tool
lifecycle notifications to the pipeline: Search emits `Using web search` only
when LangChain starts the `web_search` tool; Reader emits `Reading selected
source` only when it starts `scrape_url`. Writer and Critic emit `Thinking`
before generation and `Streaming response` upon their first text delta. This
means UI activity is based on observable lifecycle events, not inferred private
reasoning.

The FastAPI registry persists and replays `agent.activity` exactly like the
existing safe domain events. The React reducer stores the latest activity per
agent while preserving stale-event protection. The agent cards render a
subtle animated shimmer/dot only for an active status and show the last safe
activity label. The report and critique continue to stream Markdown deltas.

## Test strategy

All default backend tests remain offline and credential-free. Unit tests use a
blocking injected Search stage to prove the 45-second deadline emits the safe
terminal failure sequence without waiting for real time. Tool tests verify the
explicit Tavily timeout argument. Callback tests use a fake LangChain callback
invocation and assert the emitted activity contains the fixed label only.

API tests validate SSE replay includes activity events and that a timed-out
run releases the queued run. Frontend unit tests validate activity reduction and
animated activity rendering. Playwright keeps using the real FastAPI contract
with a deterministic fake backend pipeline and asserts the live activity label
appears before the completed output.

## Tooling and delivery

The GitHub workflow uses `backend/` for Python install, Black, Flake8, and
pytest; it uses `frontend/` for npm format, lint, unit test, build, Storybook,
and Playwright. The browser test starts `backend`'s deterministic fake API
server and Vite. The branch is
`feature/streaming-research-command-center`; the existing pull request remains
associated with the renamed branch and continues to target `devel`.

The README describes the Beta status, two-root local setup, activity privacy
boundary, stage deadlines, and commands. Contributor guidance mirrors those
commands.
