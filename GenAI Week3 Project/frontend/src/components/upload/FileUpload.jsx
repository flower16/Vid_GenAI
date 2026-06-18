import { useState } from "react";
import { uploadFile } from "../../api/client";

// Single file picker for one kind (bill | solar | smt). On success it reports
// the returned file_id up to the parent and shows the parse preview.
export default function FileUpload({ kind, label, accept, onUploaded }) {
  const [status, setStatus] = useState(null);
  const [preview, setPreview] = useState(null);

  async function handle(e) {
    const file = e.target.files?.[0];
    if (!file) return;
    setStatus("uploading…");
    try {
      const res = await uploadFile(kind, file);
      setStatus(`✓ ${res.original_name}`);
      setPreview(res.preview);
      onUploaded(res.file_id);
    } catch (err) {
      setStatus(`✗ ${err.message}`);
    }
  }

  return (
    <div style={{ border: "1px dashed #cbd5e1", borderRadius: 8, padding: 10, flex: 1, minWidth: 220 }}>
      <div style={{ fontSize: 13, fontWeight: 600 }}>{label}</div>
      <input type="file" accept={accept} onChange={handle} style={{ marginTop: 6, fontSize: 12 }} />
      {status && <div style={{ fontSize: 12, color: "#475569", marginTop: 4 }}>{status}</div>}
      {preview && (
        <pre style={{ fontSize: 11, background: "#f8fafc", padding: 6, marginTop: 6,
                      maxHeight: 110, overflow: "auto" }}>
          {JSON.stringify(preview, null, 1)}
        </pre>
      )}
    </div>
  );
}
