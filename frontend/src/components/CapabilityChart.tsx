import { Cell, Pie, PieChart, ResponsiveContainer, Tooltip } from "recharts";

import type { ModelCapability, ModelLifecycle } from "../api/types";
import { humanize } from "../lib/format";

const colors: Record<ModelLifecycle, string> = {
  validated_baseline: "#49d6b0",
  experimental: "#eeb66b",
  rejected_experiment: "#d17c8f",
};

export function CapabilityChart({ models }: { models: ModelCapability[] }) {
  const data = Object.entries(
    models.reduce<Partial<Record<ModelLifecycle, number>>>((totals, model) => {
      totals[model.status] = (totals[model.status] ?? 0) + 1;
      return totals;
    }, {}),
  ).map(([name, value]) => ({ name: humanize(name), status: name as ModelLifecycle, value }));

  return (
    <section className="chart-card glass-card" aria-labelledby="lifecycle-chart-title">
      <div className="section-heading">
        <div>
          <p className="eyebrow">Actual capability registry</p>
          <h2 id="lifecycle-chart-title">Model lifecycle</h2>
        </div>
      </div>
      <div className="chart-card__body">
        <div className="chart-card__plot" aria-hidden="true">
          <ResponsiveContainer width="100%" height="100%">
            <PieChart>
              <Pie data={data} dataKey="value" nameKey="name" innerRadius="66%" outerRadius="88%" paddingAngle={5} strokeWidth={0} isAnimationActive animationDuration={550}>
                {data.map((entry) => <Cell key={entry.status} fill={colors[entry.status]} />)}
              </Pie>
              <Tooltip contentStyle={{ display: "none" }} />
            </PieChart>
          </ResponsiveContainer>
          <div className="chart-card__total"><strong>{models.length}</strong><span>registered</span></div>
        </div>
        <ul className="chart-legend">
          {data.map((entry) => (
            <li key={entry.status}><i style={{ backgroundColor: colors[entry.status] }} /><span>{entry.name}</span><strong>{entry.value}</strong></li>
          ))}
        </ul>
      </div>
      <p className="chart-card__note">Counts are derived only from the authoritative model capability registry.</p>
    </section>
  );
}
