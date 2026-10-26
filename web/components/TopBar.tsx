import Link from "next/link";
import { RunOptimizationButton } from "@/components/RunOptimizationButton";

export function TopBar({ crumbs, projectId = "research-agent" }: { crumbs?: { label: string; href?: string }[]; projectId?: string }) {
  return (
    <header className="topbar">
      <div className="crumbs">
        <Link href="/" className="wordmark">
          <span className="gear" aria-hidden />
          Downshift
        </Link>
        {crumbs?.map((c, i) => (
          <span key={i} className="crumbs">
            <span className="sep">/</span>
            {c.href ? <Link href={c.href}>{c.label}</Link> : <span>{c.label}</span>}
          </span>
        ))}
      </div>
      <div className="topbar-actions">
        <Link href="/optimizations" className="btn secondary small">
          History
        </Link>
        <RunOptimizationButton projectId={projectId} />
      </div>
    </header>
  );
}

export function Foot() {
  return (
    <footer className="foot">
      <span>Downshift · finds out whether cheaper Nemotron models can run your agent, then opens the PR.</span>
      <span>Costs use Nebius Token Factory list prices. Results are reported on held-out runs only.</span>
    </footer>
  );
}
