"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";
import { call, MIN_RUNS, type Agent, type Browse, type FolderInfo, type HarnessCheck } from "@/lib/api";
import { shortModel } from "@/lib/format";

const STEPS = ["Choose the folder", "Create harness.yaml", "Record baseline runs"];

function firstStep(a: Agent | null): number {
  if (!a) return 0;
  if (!a.harness_on_disk) return 1;
  return 2;
}

export function Onboarding({ root, initialAgent }: { root: string; initialAgent: Agent | null }) {
  const [agent, setAgent] = useState<Agent | null>(initialAgent);
  const [step, setStep] = useState(firstStep(initialAgent));

  return (
    <div className="stack" style={{ gap: 20 }}>
      <div className="wizard" role="list" aria-label="Setup steps">
        {STEPS.map((label, i) => {
          const reachable = i === 0 || (agent && (i === 1 || agent.harness_on_disk));
          const cls = i === step ? "on" : i < step ? "done" : "";
          return (
            <div key={label} role="listitem" className={cls} aria-current={i === step ? "step" : undefined}>
              <span className="n">{i < step ? "✓" : i + 1}</span>
              {reachable && i !== step ? (
                <button className="link-btn" style={{ color: "inherit", fontSize: 14 }} onClick={() => setStep(i)}>
                  {label}
                </button>
              ) : (
                <span>{label}</span>
              )}
            </div>
          );
        })}
      </div>
      {step === 0 && (
        <FolderStep
          root={root}
          initialPath={agent?.path ?? root}
          initialId={agent?.id}
          onAdded={(a) => {
            setAgent(a);
            setStep(a.harness_on_disk ? 2 : 1);
          }}
        />
      )}
      {step === 1 && agent && (
        <HarnessStep
          agent={agent}
          onDone={() => {
            setAgent({ ...agent, harness_on_disk: true });
            setStep(2);
          }}
        />
      )}
      {step === 2 && agent && <RecordStep agentId={agent.id} />}
    </div>
  );
}

/* ---- step 1: folder ------------------------------------------------------------------------- */

function FolderStep({ root, initialPath, initialId, onAdded }: { root: string; initialPath: string; initialId?: string; onAdded: (a: Agent) => void }) {
  const [path, setPath] = useState(initialPath);
  const [browsing, setBrowsing] = useState(false);
  const [info, setInfo] = useState<FolderInfo | null>(null);
  const [id, setId] = useState(initialId ?? "");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const inspect = useCallback(async (p: string) => {
    setBusy(true);
    setError(null);
    try {
      const i = await call<FolderInfo>("/v1/fs/inspect", { body: { path: p } });
      setInfo(i);
      setPath(i.path);
      setId((cur) => cur || i.suggested_id);
      setBrowsing(false);
    } catch (e) {
      setInfo(null);
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }, []);

  useEffect(() => {
    if (initialId) inspect(initialPath);
  }, [initialId, initialPath, inspect]);

  async function add() {
    if (!info) return;
    setBusy(true);
    setError(null);
    try {
      onAdded(await call<Agent>("/v1/agents", { body: { path: info.path, id: id || info.suggested_id, name: id || info.suggested_id } }));
    } catch (e) {
      setError((e as Error).message);
      setBusy(false);
    }
  }

  return (
    <div className="card card-pad stack" style={{ gap: 16 }}>
      <div>
        <h2>Where does your agent live?</h2>
        <p className="sub small" style={{ marginTop: 4 }}>
          Pick the folder that holds your agent&apos;s code. Downshift looks for a harness.yaml, a task list and a script that records runs. Folders inside <span className="kbd">{root}</span> can be used.
        </p>
      </div>
      <form
        className="input-row"
        onSubmit={(e) => {
          e.preventDefault();
          inspect(path);
        }}
      >
        <input className="input mono" value={path} onChange={(e) => setPath(e.target.value)} placeholder="/path/to/your/agent" aria-label="Agent folder" spellCheck={false} />
        <button type="button" className="btn secondary" onClick={() => setBrowsing((b) => !b)}>
          {browsing ? "Close" : "Browse…"}
        </button>
        <button type="submit" className="btn" disabled={busy || !path.trim()}>
          {busy && !info ? "Checking…" : "Check folder"}
        </button>
      </form>
      {browsing && <FolderBrowser start={path} onPick={inspect} />}
      {error && <div className="callout err">{error}</div>}
      {info && (
        <>
          <dl className="facts">
            <dt>Folder</dt>
            <dd className="mono">{info.path}</dd>
            <dt>harness.yaml</dt>
            <dd>
              {!info.harness ? (
                <span className="is-no">Not found. You will create it in the next step.</span>
              ) : info.harness.ok ? (
                <span className="is-yes">
                  Found · {info.harness.steps.join(" → ")} on {info.harness.models_used.map(shortModel).join(", ")}
                </span>
              ) : (
                <span style={{ color: "var(--bad)" }}>Found but not valid. You can fix it in the next step.</span>
              )}
            </dd>
            <dt>Records runs with</dt>
            <dd>{info.record_script ? <span className="mono">{info.record_script}</span> : <span className="is-no">{info.uses_sdk ? "SDK found in the code, no record script" : "No Downshift SDK usage found yet"}</span>}</dd>
            <dt>Tasks</dt>
            <dd>{info.questions_file ? <span className="mono">{info.questions_file}</span> : <span className="is-no">No questions.json or tasks.json</span>}</dd>
            <dt>Tools found</dt>
            <dd>{Object.keys(info.tools).length ? <span className="mono">{Object.keys(info.tools).join(", ")}</span> : <span className="is-no">None detected in tools*.py</span>}</dd>
          </dl>
          <div className="row" style={{ alignItems: "flex-end" }}>
            <label className="field" style={{ width: 280 }}>
              <span>Agent id (also the project name the SDK records under)</span>
              <input className="input mono" value={id} onChange={(e) => setId(e.target.value)} spellCheck={false} />
            </label>
            <span className="spacer" />
            <button className="btn" onClick={add} disabled={busy}>
              {busy ? "Adding…" : "Add agent and continue"}
            </button>
          </div>
        </>
      )}
    </div>
  );
}

function FolderBrowser({ start, onPick }: { start: string; onPick: (path: string) => void }) {
  const [view, setView] = useState<Browse | null>(null);
  const [error, setError] = useState<string | null>(null);

  const open = useCallback(async (p: string | null) => {
    setError(null);
    try {
      setView(await call<Browse>(`/v1/fs/browse${p ? `?path=${encodeURIComponent(p)}` : ""}`));
    } catch (e) {
      if (p) {
        // the typed path may not exist yet: fall back to the root
        try {
          setView(await call<Browse>("/v1/fs/browse"));
          return;
        } catch {
          /* report the first error */
        }
      }
      setError((e as Error).message);
    }
  }, []);

  useEffect(() => {
    open(start);
    // only on open: later navigation happens inside the browser
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  if (error) return <div className="callout err">{error}</div>;
  if (!view) return <div className="browser"><div className="where">Loading…</div></div>;
  return (
    <div className="browser">
      <div className="where">
        <button className="btn secondary small" onClick={() => open(view.parent)} disabled={!view.parent} aria-label="Up one folder">
          ↑
        </button>
        <span className="path" title={view.path}>
          {view.path}
        </span>
        <button className="btn small" onClick={() => onPick(view.path)}>
          Use this folder
        </button>
      </div>
      <ul>
        {view.dirs.map((d) => (
          <li key={d.path}>
            <button onClick={() => open(d.path)}>
              <span className="ico" aria-hidden />
              <span style={{ flex: 1 }}>{d.name}</span>
              {d.has_harness && <span className="tag soft">harness.yaml</span>}
            </button>
          </li>
        ))}
        {!view.dirs.length && <li className="small muted" style={{ padding: "10px 12px" }}>No subfolders.</li>}
      </ul>
    </div>
  );
}

/* ---- step 2: harness ------------------------------------------------------------------------ */

function HarnessStep({ agent, onDone }: { agent: Agent; onDone: () => void }) {
  const [folder, setFolder] = useState<FolderInfo | null>(null);
  const [text, setText] = useState("");
  const [editing, setEditing] = useState(false);
  const [check, setCheck] = useState<HarnessCheck | null>(null);
  const [tools, setTools] = useState<string[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setError(null);
    try {
      const f = await call<FolderInfo>(`/v1/agents/${agent.id}/folder`);
      setFolder(f);
      if (f.harness_yaml !== null) {
        setText(f.harness_yaml);
        setCheck(f.harness);
        setEditing(!f.harness?.ok);
      } else {
        const d = await call<{ yaml: string; validation: HarnessCheck; tools_detected: string[] }>(`/v1/agents/${agent.id}/harness/draft`, { method: "POST" });
        setText(d.yaml);
        setCheck(d.validation);
        setTools(d.tools_detected);
        setEditing(true);
      }
    } catch (e) {
      setError((e as Error).message);
    }
  }, [agent.id]);

  useEffect(() => {
    load();
  }, [load]);

  // validate as the user types
  const seq = useRef(0);
  useEffect(() => {
    if (!editing) return;
    const n = ++seq.current;
    const t = setTimeout(async () => {
      try {
        const r = await call<HarnessCheck>("/v1/harness/validate", { body: { yaml: text } });
        if (n === seq.current) setCheck(r);
      } catch {
        /* keep the last result */
      }
    }, 400);
    return () => clearTimeout(t);
  }, [text, editing]);

  async function save() {
    setBusy(true);
    setError(null);
    try {
      await call(`/v1/agents/${agent.id}/harness`, { method: "PUT", body: { yaml: text, overwrite: folder?.harness_yaml !== null } });
      await load();
      setEditing(false);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  if (!folder) return <div className="card card-pad">{error ? <div className="callout err">{error}</div> : <span className="muted">Reading the folder…</span>}</div>;
  const exists = folder.harness_yaml !== null;
  const file = `${folder.path}/harness.yaml`;

  return (
    <div className="card card-pad stack" style={{ gap: 16 }}>
      <div>
        <h2>{exists ? (editing ? "Edit harness.yaml" : "Your harness.yaml") : "Create harness.yaml"}</h2>
        <p className="sub small" style={{ marginTop: 4 }}>
          The harness holds your agent&apos;s system prompt, tool descriptions, step plan and the model for each step. The SDK loads it at runtime, the optimizer writes new versions of it, and the pull request changes only this file.
        </p>
      </div>
      {!exists && (
        <div className="callout">
          This is a starting draft built from your folder{tools.length ? ` (tools found: ${tools.join(", ")})` : ""}. Check the prompts and tool descriptions, then save it to <span className="kbd">{file}</span>.
        </div>
      )}
      {editing ? (
        <textarea className="textarea" value={text} onChange={(e) => setText(e.target.value)} spellCheck={false} aria-label="harness.yaml" />
      ) : (
        <pre className="card-pad" style={{ background: "var(--surface-2)", borderRadius: 8, maxHeight: 420, overflow: "auto", fontSize: 12.5 }}>
          {text}
        </pre>
      )}
      {check && (
        <div className="small" aria-live="polite">
          {check.ok ? (
            <span className="is-yes">
              ✓ Valid · steps {check.steps.join(" → ")} · models {check.models_used.map(shortModel).join(", ")} · tools {check.tools.join(", ") || "none"} · <span className="mono">{check.fingerprint}</span>
            </span>
          ) : (
            <span style={{ color: "var(--bad)" }}>{check.error}</span>
          )}
        </div>
      )}
      {error && <div className="callout err">{error}</div>}
      <div className="row">
        {editing ? (
          <>
            <button className="btn" onClick={save} disabled={busy || !check?.ok}>
              {busy ? "Saving…" : exists ? "Save harness.yaml" : "Create harness.yaml"}
            </button>
            {exists && folder.harness?.ok && (
              <button
                className="btn secondary"
                onClick={() => {
                  setText(folder.harness_yaml ?? "");
                  setCheck(folder.harness);
                  setEditing(false);
                }}
              >
                Cancel
              </button>
            )}
          </>
        ) : (
          <>
            <button className="btn" onClick={onDone}>
              Looks right, continue
            </button>
            <button className="btn secondary" onClick={() => setEditing(true)}>
              Edit
            </button>
          </>
        )}
        <span className="spacer" />
        <span className="small muted mono">{file}</span>
      </div>
    </div>
  );
}

/* ---- step 3: baseline runs ------------------------------------------------------------------- */

function RecordStep({ agentId }: { agentId: string }) {
  const router = useRouter();
  const [agent, setAgent] = useState<Agent | null>(null);
  const [folder, setFolder] = useState<FolderInfo | null>(null);

  useEffect(() => {
    call<FolderInfo>(`/v1/agents/${agentId}/folder`).then(setFolder).catch(() => {});
    let stop = false;
    async function tick() {
      try {
        const a = await call<Agent>(`/v1/agents/${agentId}`);
        if (!stop) setAgent(a);
      } catch {
        /* keep polling */
      }
      if (!stop) setTimeout(tick, 3000);
    }
    tick();
    return () => {
      stop = true;
    };
  }, [agentId]);

  const n = agent?.ok_task_count ?? 0;
  const ready = n >= MIN_RUNS;
  const cmd = folder?.record_script
    ? `cd ${folder.path}\nuv run python ${folder.record_script} --project ${agentId}`
    : `from downshift import Downshift\n\nds = Downshift(project="${agentId}")          # sends runs to DOWNSHIFT_ENDPOINT\nharness = ds.load_harness("harness.yaml")\n\nfor task in tasks:\n    with ds.run(task_id=task["id"], input=task["question"], harness=harness) as run:\n        ...                                  # run.chat(...), run.tool(...)\n        run.finish(answer=answer, sources=urls)`;

  return (
    <div className="grid-2">
      <div className="card card-pad stack" style={{ gap: 14 }}>
        <div>
          <h2>Record baseline runs</h2>
          <p className="sub small" style={{ marginTop: 4 }}>
            Run your agent on its current model with the SDK. Each run is recorded and becomes a test case: Downshift keeps 60% to optimize on and reports results only on the other 40%.
          </p>
        </div>
        <div className="eyebrow">{folder?.record_script ? "In a terminal" : "In your agent's code"}</div>
        <div className="cmd">
          <pre>{cmd}</pre>
          <CopyButton text={cmd} />
        </div>
        <p className="small muted">
          {folder?.record_script
            ? `Add --limit 5 for a quick first batch. More runs give a firmer result; the demo agent uses 42.`
            : `Record at least ${MIN_RUNS} tasks; more runs give a firmer result.`}
        </p>
      </div>
      <div className="card progress stack" style={{ gap: 12, alignContent: "start" }}>
        <div className="row">
          {!ready && <span className="dot-live" />}
          <span className="eyebrow">{ready ? "Ready" : "Waiting for runs"}</span>
        </div>
        <div className="row" style={{ alignItems: "baseline", gap: 10 }}>
          <span className="count">{n}</span>
          <span className="sub">successful task{n === 1 ? "" : "s"} recorded</span>
        </div>
        <div className="meter" aria-label={`${n} of ${MIN_RUNS} runs`}>
          <i style={{ width: `${Math.min(100, (n / MIN_RUNS) * 100)}%` }} />
        </div>
        <p className="small sub">{ready ? "Enough runs to start an optimization. You can keep recording; new runs are picked up when you start." : `At least ${MIN_RUNS} are needed. This updates as runs arrive.`}</p>
        <div className="row" style={{ marginTop: 6 }}>
          <button className="btn" disabled={!ready} onClick={() => router.push(`/agents/${agentId}`)}>
            Continue to run
          </button>
          <Link href="/agents" className="btn secondary">
            Finish later
          </Link>
        </div>
      </div>
    </div>
  );
}

function CopyButton({ text }: { text: string }) {
  const [done, setDone] = useState(false);
  return (
    <button
      className="btn secondary small"
      onClick={async () => {
        try {
          await navigator.clipboard.writeText(text);
          setDone(true);
          setTimeout(() => setDone(false), 1500);
        } catch {
          /* clipboard blocked */
        }
      }}
    >
      {done ? "Copied" : "Copy"}
    </button>
  );
}
