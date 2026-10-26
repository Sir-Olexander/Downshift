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

export function NoResultsYet({ runCount }: { runCount: number }) {
  return (
    <div className="card empty">
      <h2>No optimization yet</h2>
      <p className="sub">
        {runCount > 0 ? `${runCount} recorded runs are waiting. Start an optimization from the top bar.` : "Record baseline runs with the SDK first, then start an optimization from the top bar."}
      </p>
      <p className="sub small" style={{ marginTop: 10 }}>
        <span className="kbd">uv run python demo_agent/record_baseline.py</span> records the demo agent on Nemotron 3 Ultra.
      </p>
      <p style={{ marginTop: 14 }}>
        <Link href="/optimizations">See past optimizations</Link>
      </p>
    </div>
  );
}
