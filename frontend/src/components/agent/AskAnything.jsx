import { useState } from "react";
import { routeAgent } from "../../api/client";

// Free-text box that routes a question to the multi-agent coordinator and shows
// which domain (energy / finance / healthcare) answered.
const DOMAIN_COLOR = { energy: "#059669", finance: "#2563eb", healthcare: "#b91c1c" };

export default function AskAnything({ intake }) {
  const [q, setQ] = useState("");
  const [resp, setResp] = useState(null);
  const [busy, setBusy] = useState(false);

  async function ask() {
    if (!q.trim()) return;
    setBusy(true); setResp(null);
    try {
      // Energy questions reuse the on-screen intake numbers.
      const data = await routeAgent(q, { intake });
      setResp(data);
    } catch (err) {
      setResp({ status: "error", detail: err.response?.data?.detail || err.message });
    } finally {
      setBusy(false);
    }
  }

  const badge = resp?.domain && (
    <span style={{ background: DOMAIN_COLOR[resp.domain] || "#475569", color: "#fff",
                   borderRadius: 6, padding: "2px 8px", fontSize: 12, marginRight: 8 }}>
      {resp.domain}
    </span>
  );

  return (
    <div style={{ border: "1px solid #e5e7eb", borderRadius: 10, padding: 14, margin: "16px 0" }}>
      <div style={{ fontWeight: 600, marginBottom: 6 }}>Ask anything (multi-agent)</div>
      <div style={{ fontSize: 12, color: "#64748b", marginBottom: 8 }}>
        Routes to energy (this app), finance (10-Ks, loans), or healthcare (readmission risk).
      </div>
      <div style={{ display: "flex", gap: 8 }}>
        <input value={q} onChange={(e) => setQ(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && ask()}
          placeholder="e.g. What was ACME's revenue in the 10-K?"
          style={{ flex: 1, padding: 6 }} />
        <button onClick={ask} disabled={busy}>{busy ? "Routing…" : "Ask"}</button>
      </div>

      {resp && (
        <div style={{ marginTop: 10, fontSize: 13 }}>
          {badge}
          <span style={{ color: resp.status === "ok" ? "#059669" : "#b91c1c" }}>
            {resp.status}
          </span>
          {resp.status === "not_connected" && (
            <div style={{ color: "#92400e", marginTop: 6 }}>{resp.how_to_enable}</div>
          )}
          {resp.detail && <div style={{ color: "#b91c1c", marginTop: 6 }}>{resp.detail}</div>}
          {resp.result && (
            <pre style={{ background: "#f8fafc", padding: 8, marginTop: 8,
                          maxHeight: 260, overflow: "auto", fontSize: 11 }}>
              {JSON.stringify(resp.result, null, 2)}
            </pre>
          )}
        </div>
      )}
    </div>
  );
}
