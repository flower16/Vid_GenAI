import { useState } from "react";
import { startCompare, getResult } from "../../api/client";
import PlanComparisonTable from "./PlanComparisonTable";
import StrategyCards from "./StrategyCards";
import AssumptionsBanner from "./AssumptionsBanner";
import FileUpload from "../upload/FileUpload";
import HistoryPanel from "../history/HistoryPanel";
import AskAnything from "../agent/AskAnything";

// Minimal end-to-end page: submit intake -> poll job -> render results.
export default function ResultsPage() {
  const [intake, setIntake] = useState({
    avg_monthly_usage_kwh: 1100, monthly_export_kwh: 600,
    monthly_self_consume_kwh: 350, solar_kw: 8, battery_installed: false,
    ev_owned: false, current_annual_bill: 1400,
  });
  const [files, setFiles] = useState({});  // {bill_file_id, solar_file_id, smt_file_id}
  const [rec, setRec] = useState(null);
  const [loading, setLoading] = useState(false);
  const [refreshKey, setRefreshKey] = useState(0);  // bump to refresh HistoryPanel

  async function run() {
    setLoading(true); setRec(null);
    const jobId = await startCompare({ ...intake, ...files });
    setRefreshKey((k) => k + 1);  // show the queued run immediately
    // poll until complete
    let data;
    for (let i = 0; i < 30; i++) {
      data = await getResult(jobId);
      if (data.status === "complete" || data.status === "error") break;
      await new Promise((r) => setTimeout(r, 1000));
    }
    setRec(data?.result ?? null);
    setLoading(false);
    setRefreshKey((k) => k + 1);  // refresh once the run + calculations are saved
  }

  // Re-open a past run from the history panel.
  async function loadPast(jobId) {
    const data = await getResult(jobId);
    setRec(data?.result ?? null);
  }

  const set = (k) => (e) =>
    setIntake({ ...intake, [k]: e.target.type === "checkbox" ? e.target.checked : Number(e.target.value) });

  return (
    <div style={{ maxWidth: 1300, margin: "0 auto", padding: 24, fontFamily: "system-ui",
                  display: "flex", gap: 24, alignItems: "flex-start" }}>
      <div style={{ flex: 1, minWidth: 0 }}>
      <h1>SolarBillIQ — Frisco / Oncor Plan Comparison</h1>
      <AskAnything intake={intake} />
      <div style={{ display: "flex", gap: 12, flexWrap: "wrap", margin: "12px 0" }}>
        <label>Usage kWh/mo <input type="number" value={intake.avg_monthly_usage_kwh} onChange={set("avg_monthly_usage_kwh")} /></label>
        <label>Export kWh/mo <input type="number" value={intake.monthly_export_kwh} onChange={set("monthly_export_kwh")} /></label>
        <label>Self-consumed kWh/mo <input type="number" value={intake.monthly_self_consume_kwh} onChange={set("monthly_self_consume_kwh")} /></label>
        <label>Battery <input type="checkbox" checked={intake.battery_installed} onChange={set("battery_installed")} /></label>
        <label>EV <input type="checkbox" checked={intake.ev_owned} onChange={set("ev_owned")} /></label>
      </div>
      <div style={{ display: "flex", gap: 10, flexWrap: "wrap", margin: "12px 0" }}>
        <FileUpload kind="solar" label="Solar production CSV" accept=".csv"
          onUploaded={(id) => setFiles((f) => ({ ...f, solar_file_id: id }))} />
        <FileUpload kind="smt" label="Smart Meter Texas CSV" accept=".csv"
          onUploaded={(id) => setFiles((f) => ({ ...f, smt_file_id: id }))} />
        <FileUpload kind="bill" label="Electricity bill PDF" accept="application/pdf"
          onUploaded={(id) => setFiles((f) => ({ ...f, bill_file_id: id }))} />
      </div>
      <button onClick={run} disabled={loading}>
        {loading ? "Comparing…" : "Compare plans"}
      </button>

      {rec && (
        <div style={{ marginTop: 24 }}>
          <StrategyCards recommendation={rec} />
          <AssumptionsBanner assumptions={rec.assumptions} />
          <PlanComparisonTable ranking={{ ranked: rec.best_overall ? buildRanked(rec) : [] }} />
          <p style={{ marginTop: 16, color: "#374151" }}>{rec.explanation}</p>
        </div>
      )}
      </div>

      <HistoryPanel refreshKey={refreshKey} onSelect={loadPast} />
    </div>
  );
}

// The /compare result returns best_* picks; for the full table we also expose
// the ranked list via recommendation. Here we read it if present.
function buildRanked(rec) {
  return rec.ranked ?? [rec.best_overall, rec.best_without_battery, rec.best_with_battery, rec.best_for_ev]
    .filter(Boolean);
}
