import Link from "next/link";

type Nav = "agents" | "run" | "results" | "history";

export function TopBar({ crumbs, projectId = "research-agent", active }: { crumbs?: { label: string; href?: string }[]; projectId?: string; active?: Nav }) {
  const links: { key: Nav; label: string; href: string }[] = [
    { key: "agents", label: "Agents", href: "/agents" },
    { key: "run", label: "Run", href: `/agents/${projectId}` },
    { key: "results", label: "Results", href: "/" },
    { key: "history", label: "History", href: "/optimizations" },
  ];
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
      <nav className="topnav" aria-label="Main">
        {links.map((l) => (
          <Link key={l.key} href={l.href} className={l.key === active ? "on" : undefined} aria-current={l.key === active ? "page" : undefined}>
            {l.label}
          </Link>
        ))}
      </nav>
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
