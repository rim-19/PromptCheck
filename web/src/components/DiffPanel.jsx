const BADGE = {
  regressed: "bg-red-500/20 text-red-300 border-red-500/40",
  improved: "bg-emerald-500/20 text-emerald-300 border-emerald-500/40",
  same: "bg-slate-700/40 text-slate-400 border-slate-600/40",
  new: "bg-sky-500/20 text-sky-300 border-sky-500/40",
};

export default function DiffPanel({ diff, onClose }) {
  if (!diff) return null;
  const { base_run, current_run, version_changed, regressions, improvements, tests } =
    diff;

  return (
    <div className="mt-4 rounded-xl border border-slate-800 bg-slate-900/50 p-4">
      <div className="mb-3 flex items-center justify-between">
        <h3 className="text-sm font-medium text-slate-300">
          Diff · baseline #{base_run.id} ({base_run.pass_count}/{base_run.total_count})
          {"  →  "} run #{current_run.id} ({current_run.pass_count}/
          {current_run.total_count})
        </h3>
        <button
          onClick={onClose}
          className="text-xs text-slate-500 hover:text-slate-300"
        >
          ✕ close
        </button>
      </div>

      <div className="mb-3 flex flex-wrap gap-2 text-xs">
        {regressions > 0 && (
          <span className="rounded border border-red-500/40 bg-red-500/20 px-2 py-1 text-red-300">
            {regressions} regression{regressions > 1 ? "s" : ""}
          </span>
        )}
        {improvements > 0 && (
          <span className="rounded border border-emerald-500/40 bg-emerald-500/20 px-2 py-1 text-emerald-300">
            {improvements} improvement{improvements > 1 ? "s" : ""}
          </span>
        )}
        {version_changed && (
          <span className="rounded border border-amber-500/40 bg-amber-500/20 px-2 py-1 text-amber-300">
            ⚠ model version changed: {base_run.model_version} → {current_run.model_version}
          </span>
        )}
        {regressions === 0 && !version_changed && (
          <span className="rounded border border-emerald-500/40 bg-emerald-500/20 px-2 py-1 text-emerald-300">
            no regressions
          </span>
        )}
      </div>

      <table className="w-full text-left text-sm">
        <thead className="text-xs uppercase text-slate-500">
          <tr>
            <th className="py-1">#</th>
            <th className="py-1">Test</th>
            <th className="py-1">Change</th>
            <th className="py-1">Baseline → Current</th>
          </tr>
        </thead>
        <tbody>
          {tests.map((t) => (
            <tr key={t.test_index} className="border-t border-slate-800/60">
              <td className="py-1 pr-2 text-slate-500">{t.test_index}</td>
              <td className="py-1 pr-2">{t.test_label}</td>
              <td className="py-1 pr-2">
                <span
                  className={`rounded border px-1.5 py-0.5 text-xs ${BADGE[t.change]}`}
                >
                  {t.change}
                </span>
              </td>
              <td className="py-1 font-mono text-xs text-slate-400">
                {t.baseline_passed === null ? "—" : t.baseline_passed ? "✓" : "✗"} →{" "}
                {t.current_passed ? "✓" : "✗"}
                <span className="ml-2 text-slate-600">
                  {(t.current_output || "").slice(0, 40)}
                </span>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
