import { useState } from "react";
import { login, register } from "../../api/client";

// Simple email/password gate. onAuthed() flips the app into the main UI.
export default function LoginPage({ onAuthed }) {
  const [mode, setMode] = useState("login");      // "login" | "register"
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);

  async function submit(e) {
    e.preventDefault();
    setBusy(true); setError(null);
    try {
      if (mode === "register") await register(email, password);
      else await login(email, password);
      onAuthed();
    } catch (err) {
      setError(err.response?.data?.detail || err.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div style={{ maxWidth: 360, margin: "80px auto", fontFamily: "system-ui" }}>
      <h1 style={{ fontSize: 22 }}>SolarBillIQ</h1>
      <p style={{ color: "#64748b", fontSize: 14 }}>
        {mode === "login" ? "Sign in to compare plans." : "Create an account."}
      </p>
      <form onSubmit={submit} style={{ display: "flex", flexDirection: "column", gap: 10 }}>
        <input type="email" placeholder="email" value={email} required
          onChange={(e) => setEmail(e.target.value)} />
        <input type="password" placeholder="password" value={password} required
          onChange={(e) => setPassword(e.target.value)} />
        <button type="submit" disabled={busy}>
          {busy ? "…" : mode === "login" ? "Sign in" : "Register"}
        </button>
      </form>
      {error && <div style={{ color: "#dc2626", fontSize: 13, marginTop: 8 }}>{error}</div>}
      <button onClick={() => setMode(mode === "login" ? "register" : "login")}
        style={{ marginTop: 12, background: "none", border: "none",
                 color: "#2563eb", cursor: "pointer", fontSize: 13 }}>
        {mode === "login" ? "Need an account? Register" : "Have an account? Sign in"}
      </button>
    </div>
  );
}
