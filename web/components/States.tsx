import Link from "next/link";

export function ApiDown({ message }: { message: string }) {
  return (
    <div className="card empty">
      <h2>The API is not answering</h2>
      <p className="sub">{message}</p>
      <p className="sub small" style={{ marginTop: 10 }}>
        Start it with <span className="kbd">uv run uvicorn app.main:app --app-dir server --port 8000</span> and reload.
      </p>
    </div>
  );
}

export function NoResultsYet({ runCount, agentId }: { runCount: number; agentId?: string }) {
  return (
    <div className="card empty">
      <h2>No optimization yet</h2>
      <p className="sub">{runCount > 0 ? `${runCount} recorded runs are waiting. Start an optimization from the Run screen.` : "Record baseline runs with the SDK first, then start an optimization from the Run screen."}</p>
      <p style={{ marginTop: 16 }} className="row" >
        <span className="spacer" />
        {agentId && (
          <Link href={`/agents/${agentId}`} className="btn">
            Go to Run
          </Link>
        )}
        <Link href="/agents" className="btn secondary">
          Manage agents
        </Link>
        <span className="spacer" />
      </p>
    </div>
  );
}
