// Surfaces the "state assumptions clearly" rule so users never mistake
// substituted defaults for real data.
export default function AssumptionsBanner({ assumptions = [] }) {
  if (!assumptions.length) return null;
  return (
    <div style={{
      background: "#FFF7E6", border: "1px solid #FFD591",
      borderRadius: 8, padding: "12px 16px", margin: "12px 0",
    }}>
      <strong>⚠️ Assumptions applied (verify for accuracy):</strong>
      <ul style={{ margin: "6px 0 0", paddingLeft: 20 }}>
        {assumptions.map((a, i) => <li key={i}>{a}</li>)}
      </ul>
    </div>
  );
}
