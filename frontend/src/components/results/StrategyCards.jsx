// Best-for strategy summary: overall / with battery / without battery / EV.
function Card({ title, plan }) {
  if (!plan) return null;
  return (
    <div style={{
      border: "1px solid #e5e7eb", borderRadius: 10, padding: 16, flex: 1, minWidth: 200,
    }}>
      <div style={{ fontSize: 12, color: "#6b7280", textTransform: "uppercase" }}>{title}</div>
      <div style={{ fontWeight: 600, marginTop: 4 }}>{plan.provider}</div>
      <div style={{ color: "#374151" }}>{plan.plan_name}</div>
      <div style={{ marginTop: 8, fontSize: 18, color: "#059669" }}>
        ${Number(plan.est_annual_bill).toFixed(0)}/yr
      </div>
    </div>
  );
}

export default function StrategyCards({ recommendation }) {
  if (!recommendation) return null;
  return (
    <div style={{ display: "flex", gap: 12, flexWrap: "wrap", margin: "16px 0" }}>
      <Card title="Best Overall" plan={recommendation.best_overall} />
      <Card title="Best Without Battery" plan={recommendation.best_without_battery} />
      <Card title="Best With Battery" plan={recommendation.best_with_battery} />
      <Card title="Best For EV" plan={recommendation.best_for_ev} />
    </div>
  );
}
