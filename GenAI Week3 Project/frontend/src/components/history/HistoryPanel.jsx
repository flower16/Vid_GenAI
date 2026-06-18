import { useEffect, useState } from "react";
import { getHistory, listFiles } from "../../api/client";

// Sidebar showing past comparison runs and uploaded files.
// Clicking a past run calls onSelect(job_id) so the parent can re-load its result.
export default function HistoryPanel({ refreshKey, onSelect }) {
  const [runs, setRuns] = useState([]);
  const [files, setFiles] = useState([]);

  useEffect(() => {
    getHistory().then(setRuns).catch(() => setRuns([]));
    listFiles().then(setFiles).catch(() => setFiles([]));
  }, [refreshKey]);

  const cell = { padding: "6px 8px", fontSize: 12, borderBottom: "1px solid #eef2f7" };

  return (
    <aside style={{ width: 280, flexShrink: 0 }}>
      <h3 style={{ fontSize: 14, margin: "0 0 6px" }}>Past comparisons</h3>
      {runs.length === 0 && <div style={{ fontSize: 12, color: "#94a3b8" }}>No runs yet.</div>}
      {runs.map((r) => (
        <div key={r.job_id} onClick={() => r.status === "complete" && onSelect(r.job_id)}
          style={{ ...cell, cursor: r.status === "complete" ? "pointer" : "default",
                   background: r.status === "complete" ? "#fff" : "#f8fafc" }}>
          <div style={{ fontWeight: 600 }}>
            {r.best_provider ? `${r.best_provider} — $${Number(r.best_annual).toFixed(0)}/yr` : r.status}
          </div>
          <div style={{ color: "#64748b" }}>
            {r.best_plan || ""} · {r.created_at ? new Date(r.created_at).toLocaleString() : ""}
          </div>
        </div>
      ))}

      <h3 style={{ fontSize: 14, margin: "16px 0 6px" }}>Uploaded files</h3>
      {files.length === 0 && <div style={{ fontSize: 12, color: "#94a3b8" }}>None.</div>}
      {files.map((f) => (
        <div key={f.file_id} style={cell}>
          <span style={{ fontWeight: 600 }}>[{f.kind}]</span> {f.original_name}
          <span style={{ color: f.parse_status === "ok" ? "#059669" : "#dc2626" }}>
            {" "}· {f.parse_status}
          </span>
        </div>
      ))}
    </aside>
  );
}
