import { useEffect, useState } from "react";
import { api } from "./api";
import PassRateChart from "./components/PassRateChart";
import DiffPanel from "./components/DiffPanel";

function shortModel(ref) {
  return ref.split("/").pop();
}
function shortTime(iso) {
  return iso ? iso.slice(0, 19).replace("T", " ") : "";
}

function RunsTable({ model, onDiff }) {
  return (
    <div className="rounded-xl border border-slate-800 bg-slate-900/50 p-4">
      <h3 className="mb-2 text-sm font-medium text-slate-300">
        {shortModel(model.model_ref)}
      </h3>
      <table className="w-full text-left text-sm">
        <thead className="text-xs uppercase text-slate-500">
          <tr>
            <th className="py-1">When</th>
            <th className="py-1">Pass</th>
            <th className="py-1">Version</th>
            <th className="py-1"></th>
          </tr>
        </thead>
        <tbody>
          {model.runs.map((r) => {
            const ok = r.pass_count === r.total_count;
            return (
              <tr key={r.id} className="border-t border-slate-800/60">
                <td className="py-1 pr-2 text-slate-400">{shortTime(r.started_at)}</td>
                <td className={`py-1 pr-2 font-medium ${ok ? "text-emerald-400" : "text-red-400"}`}>
                  {r.pass_count}/{r.total_count}
                </td>
                <td className="py-1 pr-2 text-xs text-slate-500">{r.model_version}</td>
                <td className="py-1 text-right">
                  {r.is_baseline ? (
                    <span className="rounded border border-sky-500/40 bg-sky-500/20 px-1.5 py-0.5 text-xs text-sky-300">
                      baseline
                    </span>
                  ) : model.baseline_run_id ? (
                    <button
                      onClick={() => onDiff(model.baseline_run_id, r.id)}
                      className="text-xs text-slate-500 hover:text-sky-300"
                    >
                      diff vs baseline
                    </button>
                  ) : null}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

export default function App() {
  const [suites, setSuites] = useState([]);
  const [selected, setSelected] = useState(null);
  const [detail, setDetail] = useState(null);
  const [diff, setDiff] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    api
      .suites()
      .then((s) => {
        setSuites(s);
        if (s.length) setSelected(s[0].name);
      })
      .catch((e) => setError(String(e)));
  }, []);

  useEffect(() => {
    if (!selected) return;
    setDiff(null);
    api.suite(selected).then(setDetail).catch((e) => setError(String(e)));
  }, [selected]);

  const showDiff = (baseId, curId) =>
    api.diff(baseId, curId).then(setDiff).catch((e) => setError(String(e)));

  return (
    <div className="flex h-full">
      {/* Sidebar */}
      <aside className="w-64 shrink-0 border-r border-slate-800 bg-slate-900/40 p-4">
        <div className="mb-4 flex items-center gap-2">
          <span className="text-lg">✓</span>
          <h1 className="text-lg font-semibold text-slate-100">PromptCheck</h1>
        </div>
        <div className="mb-2 text-xs uppercase tracking-wide text-slate-500">Suites</div>
        <ul className="space-y-1">
          {suites.map((s) => (
            <li key={s.name}>
              <button
                onClick={() => setSelected(s.name)}
                className={`w-full rounded-lg px-3 py-2 text-left text-sm ${
                  selected === s.name
                    ? "bg-sky-500/20 text-sky-200"
                    : "text-slate-300 hover:bg-slate-800/60"
                }`}
              >
                <div className="font-medium">{s.name}</div>
                <div className="text-xs text-slate-500">
                  {s.models.length} model{s.models.length > 1 ? "s" : ""} · {s.total_runs} runs
                </div>
              </button>
            </li>
          ))}
          {suites.length === 0 && !error && (
            <li className="text-sm text-slate-500">No runs yet.</li>
          )}
        </ul>
      </aside>

      {/* Main */}
      <main className="flex-1 overflow-auto p-6">
        {error && (
          <div className="mb-4 rounded-lg border border-red-500/40 bg-red-500/10 p-3 text-sm text-red-300">
            {error}
          </div>
        )}
        {detail && (
          <>
            <h2 className="mb-4 text-xl font-semibold text-slate-100">{detail.name}</h2>
            <PassRateChart suite={detail} />
            <div className="mt-4 grid gap-4 md:grid-cols-2">
              {detail.models.map((m) => (
                <RunsTable key={m.model_ref} model={m} onDiff={showDiff} />
              ))}
            </div>
            <DiffPanel diff={diff} onClose={() => setDiff(null)} />
          </>
        )}
        {!detail && !error && (
          <div className="text-slate-500">Select a suite…</div>
        )}
      </main>
    </div>
  );
}
