import { FormEvent, useState } from "react";

import { ResultPanel } from "./components/ResultPanel";
import { RunTimeline } from "./components/RunTimeline";
import { useResearchRun } from "./useResearchRun";

const emptyAgents = {
  search: "pending",
  reader: "pending",
  writer: "pending",
  critic: "pending"
} as const;
const emptySummaries = { search: "", reader: "", writer: "", critic: "" };

export default function App() {
  const [topic, setTopic] = useState("");
  const [formError, setFormError] = useState("");
  const research = useResearchRun();
  const snapshot = research.snapshot;
  const active = snapshot?.status === "running" || snapshot?.status === "queued";

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!topic.trim()) {
      setFormError("Enter a research topic to begin.");
      return;
    }
    setFormError("");
    try {
      await research.start(topic);
    } catch {
      setFormError("Unable to start research. Please try again.");
    }
  }

  async function cancel() {
    try {
      await research.cancel();
    } catch {
      setFormError("Unable to cancel this run. Please try again.");
    }
  }

  return (
    <main className="min-h-screen bg-[#07111f] text-slate-100">
      <div className="mx-auto flex min-h-screen max-w-[1600px] flex-col px-4 py-5 sm:px-7 lg:px-10">
        <header className="flex flex-col justify-between gap-5 border-b border-white/10 pb-6 md:flex-row md:items-center">
          <div className="flex items-center gap-3">
            <div className="grid size-11 place-items-center rounded-2xl bg-cyan-300 text-lg font-black text-slate-950 shadow-[0_0_36px_rgba(103,232,249,0.24)]">
              R
            </div>
            <div>
              <p className="text-sm font-semibold tracking-wide text-white">
                Research Command Center
              </p>
              <p className="mt-1 text-sm text-slate-400">
                Multi-agent research, visible as it happens.
              </p>
            </div>
          </div>
          <div className="flex items-center gap-3 text-sm text-slate-400">
            <span className="size-2 rounded-full bg-emerald-300 shadow-[0_0_12px_rgba(110,231,183,0.9)]" />
            Local orchestration ready
          </div>
        </header>

        <section className="grid flex-1 gap-6 py-7 xl:grid-cols-[300px_minmax(0,1fr)]">
          <aside className="panel h-fit p-5 xl:sticky xl:top-7">
            <p className="eyebrow">New investigation</p>
            <h1 className="mt-3 text-2xl font-semibold tracking-tight text-white">
              What should we research?
            </h1>
            <p className="mt-3 text-sm leading-6 text-slate-400">
              Start one focused question. The agents will search, read, write, and critique in
              sequence.
            </p>
            <form className="mt-6 space-y-3" onSubmit={submit}>
              <label className="sr-only" htmlFor="research-topic">
                Research topic
              </label>
              <textarea
                id="research-topic"
                className="field min-h-32 resize-y"
                value={topic}
                maxLength={1000}
                onChange={(event) => setTopic(event.target.value)}
                placeholder="e.g. What changed in grid-scale energy storage this year?"
              />
              <p className="text-right text-xs text-slate-500">{topic.length}/1000</p>
              {formError ? (
                <p role="alert" className="text-sm text-rose-300">
                  {formError}
                </p>
              ) : null}
              <button
                className="primary-button w-full"
                disabled={research.isSubmitting || active}
                type="submit"
              >
                {research.isSubmitting
                  ? "Starting…"
                  : active
                    ? "Research in progress"
                    : "Start research"}
              </button>
            </form>
            {active ? (
              <button
                className="danger-button mt-3 w-full"
                type="button"
                onClick={() => void cancel()}
              >
                Cancel research
              </button>
            ) : null}
            {snapshot && !active ? (
              <button
                className="mt-4 text-sm font-medium text-cyan-200 hover:text-cyan-100"
                type="button"
                onClick={() => {
                  research.clear();
                  setTopic("");
                }}
              >
                Start a fresh run
              </button>
            ) : null}
          </aside>

          <div className="space-y-6">
            <section className="panel overflow-hidden p-6 sm:p-8">
              <div className="flex flex-col gap-5 md:flex-row md:items-end md:justify-between">
                <div>
                  <p className="eyebrow">Current run</p>
                  <h2 className="mt-3 max-w-3xl text-2xl font-semibold tracking-tight text-white sm:text-3xl">
                    {snapshot?.topic || "Waiting for your first question"}
                  </h2>
                </div>
                <RunStatus status={snapshot?.status} />
              </div>
              {snapshot?.error ? (
                <p role="alert" className="mt-5 text-sm text-rose-300">
                  {snapshot.error}
                </p>
              ) : null}
            </section>
            <RunTimeline
              agents={snapshot?.agents ?? emptyAgents}
              summaries={snapshot?.summaries ?? emptySummaries}
            />
            <ResultPanel snapshot={snapshot} />
          </div>
        </section>
      </div>
    </main>
  );
}

function RunStatus({ status }: { status?: string }) {
  const copy =
    status === "queued"
      ? "Queued"
      : status === "running"
        ? "Live"
        : status === "completed"
          ? "Complete"
          : status === "failed"
            ? "Failed"
            : status === "cancelled"
              ? "Cancelled"
              : "Ready";
  const style =
    status === "running"
      ? "bg-cyan-300/15 text-cyan-100"
      : status === "completed"
        ? "bg-emerald-300/15 text-emerald-100"
        : "bg-white/6 text-slate-300";
  return (
    <span className={`w-fit rounded-full px-3 py-1.5 text-sm font-medium ${style}`}>{copy}</span>
  );
}
