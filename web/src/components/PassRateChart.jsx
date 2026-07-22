import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  Tooltip,
  CartesianGrid,
  ResponsiveContainer,
  Legend,
} from "recharts";

const COLORS = ["#38bdf8", "#a78bfa", "#f472b6", "#34d399", "#fbbf24"];

function shortModel(ref) {
  return ref.split("/").pop();
}

function shortTime(iso) {
  return iso ? iso.slice(5, 16).replace("T", " ") : "";
}

// Merge every model's runs into one time-ordered dataset, one series per model.
function buildData(models) {
  const byTime = new Map();
  for (const m of models) {
    const key = shortModel(m.model_ref);
    for (const run of m.runs) {
      const t = run.started_at;
      if (!byTime.has(t)) byTime.set(t, { t, label: shortTime(t) });
      byTime.get(t)[key] = Math.round(run.pass_rate * 100);
    }
  }
  return [...byTime.values()].sort((a, b) => (a.t < b.t ? -1 : 1));
}

export default function PassRateChart({ suite }) {
  const data = buildData(suite.models);
  const keys = suite.models.map((m) => shortModel(m.model_ref));

  return (
    <div className="h-72 w-full rounded-xl border border-slate-800 bg-slate-900/50 p-4">
      <h3 className="mb-2 text-sm font-medium text-slate-400">
        Pass rate over time (%)
      </h3>
      <ResponsiveContainer width="100%" height="90%">
        <LineChart data={data} margin={{ top: 5, right: 20, bottom: 5, left: -20 }}>
          <CartesianGrid stroke="#1e293b" strokeDasharray="3 3" />
          <XAxis dataKey="label" tick={{ fill: "#64748b", fontSize: 11 }} />
          <YAxis domain={[0, 100]} tick={{ fill: "#64748b", fontSize: 11 }} />
          <Tooltip
            contentStyle={{
              background: "#0f172a",
              border: "1px solid #1e293b",
              borderRadius: 8,
              color: "#e2e8f0",
            }}
          />
          <Legend wrapperStyle={{ fontSize: 12 }} />
          {keys.map((k, i) => (
            <Line
              key={k}
              type="monotone"
              dataKey={k}
              stroke={COLORS[i % COLORS.length]}
              strokeWidth={2}
              dot={{ r: 3 }}
              connectNulls
            />
          ))}
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
