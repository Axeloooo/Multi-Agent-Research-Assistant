import Markdown from "react-markdown";
import remarkGfm from "remark-gfm";

import type { RunSnapshot } from "../useResearchRun";

interface ResultPanelProps {
  snapshot: RunSnapshot | null;
}

export function ResultPanel({ snapshot }: ResultPanelProps) {
  const complete = snapshot?.status === "completed";
  const downloadBase = snapshot ? `/api/runs/${snapshot.run_id}/downloads` : "";

  return (
    <section aria-labelledby="research-output-heading" className="panel overflow-hidden">
      <div className="flex flex-col justify-between gap-4 border-b border-white/8 p-6 sm:flex-row sm:items-center">
        <div>
          <p className="eyebrow">Deliverable</p>
          <h2 id="research-output-heading" className="mt-2 text-xl font-semibold text-white">
            Research output
          </h2>
        </div>
        <div className="flex flex-wrap gap-2">
          {complete ? (
            <>
              <a className="secondary-button" href={`${downloadBase}/report.md`} download>
                Download Markdown
              </a>
              <a className="secondary-button" href={`${downloadBase}/result.json`} download>
                Download JSON
              </a>
            </>
          ) : (
            <span className="text-sm text-slate-400">Downloads unlock when the run completes.</span>
          )}
        </div>
      </div>
      <div className="grid divide-y divide-white/8 lg:grid-cols-[1.7fr_0.8fr] lg:divide-x lg:divide-y-0">
        <article className="min-h-72 p-6">
          {snapshot?.report ? (
            <div className="markdown-body">
              <Markdown remarkPlugins={[remarkGfm]}>{snapshot.report}</Markdown>
            </div>
          ) : (
            <EmptyOutput label="The Writer will stream the report here." />
          )}
        </article>
        <aside className="min-h-72 bg-slate-950/30 p-6">
          <p className="eyebrow">Critic notes</p>
          {snapshot?.critique ? (
            <div className="markdown-body mt-4 text-sm">
              <Markdown remarkPlugins={[remarkGfm]}>{snapshot.critique}</Markdown>
            </div>
          ) : (
            <EmptyOutput label="Quality checks and gaps will appear here." />
          )}
        </aside>
      </div>
    </section>
  );
}

function EmptyOutput({ label }: { label: string }) {
  return <p className="pt-10 text-sm leading-6 text-slate-500">{label}</p>;
}
