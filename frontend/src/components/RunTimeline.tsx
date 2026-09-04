import type { AgentName, AgentStatus } from "../useResearchRun";

interface RunTimelineProps {
  agents: Record<AgentName, AgentStatus>;
  summaries: Record<AgentName, string>;
}

const stages: Array<{ name: AgentName; label: string; detail: string }> = [
  { name: "search", label: "Search", detail: "Locate reliable sources" },
  { name: "reader", label: "Reader", detail: "Extract useful context" },
  { name: "writer", label: "Writer", detail: "Draft the research brief" },
  { name: "critic", label: "Critic", detail: "Check quality and gaps" }
];

const statusCopy: Record<AgentStatus, string> = {
  pending: "Waiting",
  running: "In progress",
  completed: "Complete",
  failed: "Needs attention",
  cancelled: "Cancelled",
  skipped: "Skipped"
};

export function RunTimeline({ agents, summaries }: RunTimelineProps) {
  return (
    <section aria-labelledby="agent-progress-heading" className="panel p-6">
      <div className="mb-6 flex items-start justify-between gap-4">
        <div>
          <p className="eyebrow">Live orchestration</p>
          <h2 id="agent-progress-heading" className="mt-2 text-xl font-semibold text-white">
            Agent progress
          </h2>
        </div>
        <span className="rounded-full border border-cyan-300/20 bg-cyan-300/10 px-3 py-1 text-xs font-medium text-cyan-100">
          Safe summaries only
        </span>
      </div>
      <ol className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
        {stages.map((stage, index) => {
          const status = agents[stage.name];
          const summary = summaries[stage.name];
          return (
            <li key={stage.name} className="stage-card" data-status={status}>
              <div className="flex items-start justify-between gap-3">
                <span className="stage-number">0{index + 1}</span>
                <span className={`status-pill status-${status}`}>{statusCopy[status]}</span>
              </div>
              <h3 className="mt-6 font-semibold text-white">{stage.label}</h3>
              <p className="mt-1 text-sm text-slate-400">{stage.detail}</p>
              {summary ? (
                <details className="mt-4 border-t border-white/8 pt-3">
                  <summary className="cursor-pointer text-sm font-medium text-cyan-200">
                    View summary
                  </summary>
                  <p className="mt-3 text-sm leading-6 text-slate-300">{summary}</p>
                </details>
              ) : null}
            </li>
          );
        })}
      </ol>
    </section>
  );
}
