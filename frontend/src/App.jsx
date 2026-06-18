import { useState } from "react";
import ResultsPage from "./components/results/ResultsPage";
import LoginPage from "./components/auth/LoginPage";
import { isAuthed, logout } from "./api/client";

export default function App() {
  const [authed, setAuthed] = useState(isAuthed());

  if (!authed) return <LoginPage onAuthed={() => setAuthed(true)} />;

  return (
    <div>
      <div style={{ textAlign: "right", padding: "8px 16px" }}>
        <button onClick={() => { logout(); setAuthed(false); }}
          style={{ background: "none", border: "none", color: "#2563eb",
                   cursor: "pointer", fontSize: 13 }}>
          Sign out
        </button>
      </div>
      <ResultsPage />
    </div>
  );
}
