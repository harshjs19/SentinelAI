import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

import type { Machine } from "../api/types";

export function AssetChart({ machines }: { machines: Machine[] }) {
  const data = Object.entries(
    machines.reduce<Record<string, number>>((totals, machine) => {
      totals[machine.asset_type] = (totals[machine.asset_type] ?? 0) + 1;
      return totals;
    }, {}),
  ).sort(([a], [b]) => a.localeCompare(b)).map(([name, count]) => ({ name, count }));

  return (
    <section className="chart-card glass-card" aria-labelledby="asset-chart-title">
      <div className="section-heading">
        <div><p className="eyebrow">Persisted machine inventory</p><h2 id="asset-chart-title">Assets by type</h2></div>
      </div>
      <div className="asset-chart" aria-label="Machine count grouped by asset type">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={data} layout="vertical" margin={{ top: 4, right: 16, left: 10, bottom: 4 }}>
            <CartesianGrid stroke="rgba(255,255,255,.06)" horizontal={false} />
            <XAxis type="number" allowDecimals={false} stroke="#768393" fontSize={11} />
            <YAxis type="category" dataKey="name" width={172} stroke="#95a2b3" fontSize={10} tickLine={false} axisLine={false} />
            <Tooltip cursor={{ fill: "rgba(99,220,255,.04)" }} contentStyle={{ background: "#101821", border: "1px solid rgba(255,255,255,.12)", borderRadius: 10 }} />
            <Bar dataKey="count" fill="#56c9e8" radius={[0, 6, 6, 0]} animationDuration={550} />
          </BarChart>
        </ResponsiveContainer>
      </div>
      <p className="chart-card__note">Counts are derived only from GET /machines.</p>
    </section>
  );
}
