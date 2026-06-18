// Headline comparison table — one row per plan, ranked by lowest annual cost.
// Columns match the required output spec.
const fmt = (n) => (n == null ? "—" : `$${Number(n).toFixed(2)}`);

export default function PlanComparisonTable({ ranking }) {
  const rows = ranking?.ranked ?? [];
  return (
    <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 14 }}>
      <thead>
        <tr style={{ background: "#1f2937", color: "#fff", textAlign: "left" }}>
          {["#", "Provider", "Plan Type", "Energy Cost", "Buyback Credit",
            "TDU Charges", "Base Fees", "Est. Monthly", "Est. Annual", "Savings"]
            .map((h) => <th key={h} style={{ padding: "8px 10px" }}>{h}</th>)}
        </tr>
      </thead>
      <tbody>
        {rows.map((r, i) => {
          const m = r.monthly?.[0] ?? {};
          return (
            <tr key={i} style={{
              borderBottom: "1px solid #e5e7eb",
              background: i === 0 ? "#ECFDF5" : "#fff",
              fontWeight: i === 0 ? 600 : 400,
            }}>
              <td style={{ padding: "8px 10px" }}>{r.rank}</td>
              <td style={{ padding: "8px 10px" }}>{r.provider}</td>
              <td style={{ padding: "8px 10px" }}>{r.plan_type}</td>
              <td style={{ padding: "8px 10px" }}>{fmt(m.imported_energy_cost)}</td>
              <td style={{ padding: "8px 10px", color: "#059669" }}>
                {m.export_credit ? `-${fmt(m.export_credit)}` : "—"}
              </td>
              <td style={{ padding: "8px 10px" }}>{fmt(m.tdu_delivery_cost)}</td>
              <td style={{ padding: "8px 10px" }}>{fmt(m.base_fee)}</td>
              <td style={{ padding: "8px 10px" }}>{fmt(m.est_monthly_bill)}</td>
              <td style={{ padding: "8px 10px" }}>{fmt(r.est_annual_bill)}</td>
              <td style={{ padding: "8px 10px", color: "#059669" }}>
                {r.annual_savings_vs_current != null
                  ? fmt(r.annual_savings_vs_current) : "—"}
              </td>
            </tr>
          );
        })}
      </tbody>
    </table>
  );
}
