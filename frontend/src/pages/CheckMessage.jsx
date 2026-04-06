import React, { useState, useEffect, useRef } from "react";
import { Link } from "react-router-dom";
import { authFetch, authFetchMultipart } from "../services/api";
import { extractTextFromImage } from "../utils/ocrHelper";
import PageLayout from "../components/PageLayout";
import {
  VERDICT_LABEL, VERDICT_HEADLINE, VERDICT_GUIDANCE, RISK_ITEMS,
  pillClass, verdictIcon, verdictClass, riskColor, riskLabel,
  confidenceColor, keyConcern, splitExplanation,
} from "../utils/verdictUtils";

// ============================================================
// CheckMessage.jsx — Verify MTN MoMo SMS / screenshot
// ============================================================
// Routes used:
//   POST /api/message-checks/sms-check         — submit SMS text
//   POST /api/message-checks/upload-screenshot  — upload image
//   GET  /api/wallet                            — populate wallet picker
// ============================================================

function CheckMessage() {
  const [tab, setTab] = useState("sms");

  // Shared
  const [wallets, setWallets] = useState([]);
  const [walletsLoading, setWalletsLoading] = useState(true);
  const [walletId, setWalletId] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [warning, setWarning] = useState("");   // Phase-10: separate warning state
  const [result, setResult] = useState(null);

  // SMS fields
  const [smsText, setSmsText] = useState("");

  // Screenshot fields
  const [file, setFile] = useState(null);
  const [fileName, setFileName] = useState("");
  const [filePreview, setFilePreview] = useState(null);  // image preview URL
  const [ocrPending, setOcrPending] = useState(false);   // true when backend returns 202
  const [ocrText, setOcrText] = useState("");             // Phase-8 Part 2: extracted OCR text
  const [ocrConfidence, setOcrConfidence] = useState(null);  // 0.0–1.0 from backend
  const [ocrLowConfidence, setOcrLowConfidence] = useState(false);
  const [ocrError, setOcrError] = useState("");           // OCR failure message
  const [ocrUsable, setOcrUsable] = useState(false);       // true when OCR text passed usability gate
  const [isDragging, setIsDragging] = useState(false);   // Phase-8: drag-and-drop highlight
  const [ocrProgress, setOcrProgress] = useState(null);  // { status, progress } from Tesseract.js
  const dropRef = useRef(null);
  const resultRef = useRef(null);

  // Phase-8 refinement: revoke object URL on unmount to prevent memory leaks
  useEffect(() => {
    return () => {
      if (filePreview) URL.revokeObjectURL(filePreview);
    };
  }, [filePreview]);

  // Fetch user wallets for the dropdown
  useEffect(() => {
    async function loadWallets() {
      try {
        const { data, response } = await authFetch("/wallet");
        if (response.ok) {
          const list = data.wallets || [];
          setWallets(list);
          if (list.length > 0) setWalletId(String(list[0].id));
        }
      } catch (err) {
        console.error("[CheckMessage] Failed to load wallets:", err);
      } finally {
        setWalletsLoading(false);
      }
    }
    loadWallets();
  }, []);

  // ---- Submit SMS ----
  async function handleSmsSubmit(e) {
    e.preventDefault();
    setError("");
    setWarning("");
    setResult(null);

    if (!smsText.trim()) { setError("Please paste the SMS message text."); return; }
    if (!walletId)        { setError("Please select a wallet first."); return; }

    setLoading(true);
    try {
      const { data, response } = await authFetch(
        "/message-checks/sms-check", "POST",
        { raw_text: smsText.trim(), wallet_id: Number(walletId) }
      );
      if (response.ok) {
        setResult(data.data);
        setSmsText("");
        // Show backend warnings (e.g. low parser confidence) as a yellow notice
        if (data.warnings && data.warnings.length > 0) {
          setWarning(data.warnings.join(" "));
        }
        // Scroll to result
        setTimeout(() => resultRef.current?.scrollIntoView({ behavior: "smooth", block: "start" }), 100);
      } else {
        setError(data.errors?.join(" ") || data.message || "Analysis failed.");
      }
    } catch (err) {
      console.error("[CheckMessage] SMS submit failed:", err);
      setError("Could not reach the server. Is the backend running?");
    } finally {
      setLoading(false);
    }
  }

  // ---- Submit Screenshot ----
  const MAX_FILE_SIZE = 5 * 1024 * 1024; // 5 MB — matches backend _MAX_FILE_SIZE
  const ALLOWED_TYPES = ["image/png", "image/jpeg", "image/webp"];

  // Phase-8 refinement: shared handler for both file-input and drag-drop
  function selectFile(f) {
    if (!f) return;
    // Revoke previous preview URL to free memory
    if (filePreview) URL.revokeObjectURL(filePreview);

    // Client-side MIME check (best-effort; backend also validates magic bytes)
    if (!ALLOWED_TYPES.includes(f.type)) {
      setError("Only PNG, JPG, and WEBP images are accepted.");
      return;
    }
    setFile(f);
    setFileName(f.name);
    setFilePreview(URL.createObjectURL(f));
    setError("");
  }

  function clearFile() {
    if (filePreview) URL.revokeObjectURL(filePreview);
    setFile(null);
    setFileName("");
    setFilePreview(null);
    // Reset the native file-input too
    const input = document.getElementById("screenshot-input");
    if (input) input.value = "";
  }

  // Phase-8 refinement: drag-and-drop handlers
  function handleDragOver(e) { e.preventDefault(); setIsDragging(true); }
  function handleDragLeave(e) { e.preventDefault(); setIsDragging(false); }
  function handleDrop(e) {
    e.preventDefault();
    setIsDragging(false);
    const droppedFile = e.dataTransfer?.files?.[0];
    if (droppedFile) selectFile(droppedFile);
  }

  async function handleScreenshotSubmit(e) {
    e.preventDefault();
    setError("");
    setWarning("");
    setResult(null);
    setOcrPending(false);
    setOcrText("");
    setOcrConfidence(null);
    setOcrLowConfidence(false);
    setOcrError("");
    setOcrUsable(false);
    setOcrProgress(null);

    if (!file)      { setError("Please select a screenshot file."); return; }
    if (!walletId)  { setError("Please select a wallet first."); return; }
    if (file.size > MAX_FILE_SIZE) {
      setError(`File is too large (${(file.size / 1024 / 1024).toFixed(1)} MB). Maximum size is 5 MB.`);
      return;
    }

    setLoading(true);

    // ── Step A: Run OCR in the browser using Tesseract.js ──
    let clientOcrText = "";
    let clientOcrConf = 0;
    try {
      setOcrProgress({ status: "Preparing image…", progress: 0 });
      const ocrResult = await extractTextFromImage(file, (info) => {
        // Map Tesseract internal status strings to user-friendly labels
        const LABELS = {
          "loading tesseract core": "Loading OCR engine…",
          "initializing tesseract":  "Starting OCR engine…",
          "loading language traineddata": "Loading language data…",
          "initializing api":        "Initialising…",
          "recognizing text":        "Reading text…",
        };
        const status = LABELS[info.status] || info.status;
        setOcrProgress({ status, progress: info.progress ?? 0 });
      });
      setOcrProgress(null);
      clientOcrText = ocrResult.text || "";
      clientOcrConf = ocrResult.confidence || 0;
      if (clientOcrText) {
        setOcrText(clientOcrText);
        setOcrConfidence(clientOcrConf);
        setOcrUsable(clientOcrText.length >= 10);
        setOcrLowConfidence(clientOcrConf < 0.4);
      }
      if (ocrResult.error) {
        setOcrError(ocrResult.error);
      }
    } catch (ocrErr) {
      console.error("[CheckMessage] Browser OCR failed:", ocrErr);
      setOcrProgress(null);
      // Non-fatal — continue uploading without extracted text
    }

    // ── Step B: Upload screenshot + pre-extracted text to backend ──
    try {
      const formData = new FormData();
      formData.append("file", file);          // must match backend field name
      formData.append("wallet_id", walletId);
      // Send browser-extracted text so backend skips server-side Tesseract
      if (clientOcrText) {
        formData.append("extracted_text", clientOcrText);
        formData.append("ocr_confidence", String(clientOcrConf));
      }

      const { data, response } = await authFetchMultipart(
        "/message-checks/upload-screenshot", formData
      );

      if (response.ok) {
        setResult(data.data);

        // Capture OCR text from whichever response path has it
        const extractedText =
          data.extracted_text ||
          data.data?.extracted_text ||
          data.data?.message_check?.extracted_text ||
          "";
        if (extractedText) setOcrText(extractedText);

        // Capture OCR metadata
        if (data.ocr_confidence != null) setOcrConfidence(data.ocr_confidence);
        if (data.ocr_low_confidence) setOcrLowConfidence(true);
        if (data.ocr_usable) setOcrUsable(true);

        // Surface backend warnings as a yellow notice
        if (data.warnings && data.warnings.length > 0) {
          setWarning(data.warnings.join(" "));
        }

        // 202 = uploaded but OCR not usable for analysis
        if (response.status === 202) {
          setOcrPending(true);
        }
        // Scroll to result
        setTimeout(() => resultRef.current?.scrollIntoView({ behavior: "smooth", block: "start" }), 100);
        setFile(null);
        setFileName("");
        if (filePreview) URL.revokeObjectURL(filePreview);
        setFilePreview(null);
      } else {
        setError(data.errors?.join(" ") || data.message || "Upload failed.");
      }
    } catch (err) {
      console.error("[CheckMessage] Screenshot submit failed:", err);
      setError("Could not reach the server. Is the backend running?");
    } finally {
      setLoading(false);
    }
  }

  // ---- Render ----
  const pred = result?.prediction;
  const mc   = result?.message_check;
  const hasNoWallet = !walletsLoading && wallets.length === 0;

  return (
    <PageLayout
      title="Verify Message"
      subtitle="Check incoming MTN MoMo credit alerts for authenticity."
    >
      <div className="check-message-layout">
      {/* Error banner */}
      {error && (
        <div className="message-box error" role="alert" aria-live="assertive">
          <span className="message-icon">{"\u274c"}</span>
          {error}
        </div>
      )}

      {/* Warning banner (non-blocking notices from backend) */}
      {warning && !error && (
        <div className="message-box warning" role="status" aria-live="polite">
          <span className="message-icon">{"\u26a0\ufe0f"}</span>
          {warning}
        </div>
      )}

      {/* ── Wallet required — shown before tabs so it is always visible ── */}
      {hasNoWallet && (
        <div className="wallet-required-card" role="alert">
          <div className="wallet-required-icon">💳</div>
          <div className="wallet-required-body">
            <h3 className="wallet-required-title">Link a Wallet First</h3>
            <p className="wallet-required-desc">
              You need at least one MTN MoMo wallet linked to your account before you can verify messages.
            </p>
            <Link to="/wallets" className="btn btn-primary wallet-required-cta">
              + Add Your Wallet
            </Link>
          </div>
        </div>
      )}

      {/* Tab switcher */}
      <div className="tab-switcher check-tab-switcher">
        <button
          className={`tab-btn ${tab === "sms" ? "active" : ""}`}
          onClick={() => { setTab("sms"); setResult(null); setError(""); setWarning(""); setOcrPending(false); setOcrText(""); setOcrConfidence(null); setOcrLowConfidence(false); setOcrError(""); setOcrUsable(false); }}
        >
          &#128241; SMS Text
        </button>
        <button
          className={`tab-btn ${tab === "screenshot" ? "active" : ""}`}
          onClick={() => { setTab("screenshot"); setResult(null); setError(""); setWarning(""); setOcrPending(false); setOcrText(""); setOcrConfidence(null); setOcrLowConfidence(false); setOcrError(""); setOcrUsable(false); }}
        >
          &#128248; Screenshot
          <span className="tab-badge">OCR</span>
        </button>
      </div>

      {/* Compact how-to panel — shown only before a result appears */}
      {!result && (
        <div className="check-guidance-strip">
          <span className="check-guidance-label">How to use</span>
          <div className="check-guidance-items">
            <div className="check-guidance-item">
              <span className="check-guidance-icon">1</span>
              Link a wallet, then select it from the dropdown below
            </div>
            <div className="check-guidance-item">
              <span className="check-guidance-icon">2</span>
              Paste the <strong>full SMS</strong> exactly as received — do not edit it
            </div>
            <div className="check-guidance-item">
              <span className="check-guidance-icon">3</span>
              Tap <strong>Verify Message</strong> and get an instant result
            </div>
            <div className="check-guidance-item">
              <span className="check-guidance-icon">📸</span>
              Can&rsquo;t copy the text? Use the <strong>Screenshot</strong> tab instead
            </div>
          </div>
        </div>
      )}

      {/* ── SMS Form ── */}
      {tab === "sms" && (
        <div className={`form-card check-form-card${hasNoWallet ? " form-card--muted" : ""}`}>
          <h3 className="check-form-title">Paste MoMo SMS</h3>
          <form onSubmit={handleSmsSubmit}>
            <div className="form-group">
              <label htmlFor="sms-wallet-id">
                Which wallet received this message?
              </label>
              {walletsLoading ? (
                <p className="form-loading-note">Loading wallets…</p>
              ) : wallets.length === 0 ? (
                <div className="wallet-inline-empty">
                  <span>No wallets linked yet — use the button above.</span>
                </div>
              ) : (
                <select id="sms-wallet-id" value={walletId} onChange={(e) => setWalletId(e.target.value)} required>
                  {wallets.map((w) => (
                    <option key={w.id} value={w.id}>
                      {w.phone_number} — {w.provider}
                    </option>
                  ))}
                </select>
              )}
            </div>
            <div className="form-group">
              <label htmlFor="sms-text">Full SMS Text</label>
              <textarea
                id="sms-text"
                className="form-textarea"
                rows={5}
                value={smsText}
                onChange={(e) => setSmsText(e.target.value)}
                placeholder="Paste the complete MoMo SMS here — do not edit any words or numbers"
                disabled={hasNoWallet}
                required
              />
              <div className="char-counter-row">
                <span className={`char-counter${smsText.length > 0 ? " char-counter--active" : ""}`}>
                  {smsText.length > 0 ? `${smsText.length} chars` : "0 chars"}
                </span>
                {smsText.length > 0 && smsText.length < 20 && (
                  <span className="char-counter-hint">Keep the full message for accurate results</span>
                )}
              </div>
            </div>
            <div className="check-submit-row">
              <span className="check-submit-note">
                {hasNoWallet ? "Add a wallet above to enable verification" : "Results appear below after submission"}
              </span>
              <button
                type="submit"
                className="btn btn-primary check-verify-btn"
                disabled={loading || hasNoWallet || !smsText.trim()}
                title={hasNoWallet ? "Link a wallet first" : !smsText.trim() ? "Paste an SMS first" : undefined}
              >
                {loading ? "Checking…" : "🔍 Verify Message"}
              </button>
            </div>
          </form>
        </div>
      )}

      {/* ── Screenshot Form ── */}
      {tab === "screenshot" && (
        <div className={`form-card check-form-card${hasNoWallet ? " form-card--muted" : ""}`}>
          <h3 className="check-form-title">Upload Screenshot</h3>
          <form onSubmit={handleScreenshotSubmit}>
            <div className="form-group">
              <label htmlFor="screenshot-wallet-id">Which wallet received this payment?</label>
              {walletsLoading ? (
                <p className="form-loading-note">Loading wallets…</p>
              ) : wallets.length === 0 ? (
                <div className="wallet-inline-empty">
                  <span>No wallets linked yet — use the button above.</span>
                </div>
              ) : (
                <select id="screenshot-wallet-id" value={walletId} onChange={(e) => setWalletId(e.target.value)} required>
                  {wallets.map((w) => (
                    <option key={w.id} value={w.id}>
                      {w.phone_number} — {w.provider}
                    </option>
                  ))}
                </select>
              )}
            </div>
            {/* Screenshot guidance callout */}
            <div className="message-box info" style={{ marginBottom: "0.75rem", fontSize: "0.85rem" }}>
              <span className="message-icon">📸</span>
              <div>
                <strong>For best results:</strong>
                <ul style={{ margin: "0.25rem 0 0", paddingLeft: "1.2rem" }}>
                  <li>Screenshot the full SMS notification or MoMo inbox message</li>
                  <li>Make sure all text is visible and not cropped</li>
                  <li>Avoid screenshots of screenshots or photos of screens</li>
                </ul>
              </div>
            </div>
            <div className="form-group">
              <label>Screenshot (PNG, JPG, WEBP — max 5 MB)</label>
              {/* Phase-8 refinement: drag-and-drop zone */}
              <div
                ref={dropRef}
                className="file-upload-area"
                onDragOver={handleDragOver}
                onDragLeave={handleDragLeave}
                onDrop={handleDrop}
                style={{
                  border: isDragging
                    ? "2px dashed var(--color-primary, #3b82f6)"
                    : "2px dashed var(--color-slate-300, #cbd5e1)",
                  background: isDragging
                    ? "rgba(59,130,246,0.05)"
                    : "transparent",
                  borderRadius: "var(--radius-md, 8px)",
                  padding: "1.5rem",
                  textAlign: "center",
                  transition: "border 0.2s, background 0.2s",
                  cursor: "pointer",
                }}
                onClick={() => document.getElementById("screenshot-input")?.click()}
              >
                <input
                  type="file"
                  id="screenshot-input"
                  accept=".png,.jpg,.jpeg,.webp"
                  style={{ display: "none" }}
                  onChange={(e) => selectFile(e.target.files[0] || null)}
                />
                <p style={{ margin: 0, fontSize: "0.95rem", color: "var(--color-slate-500)" }}>
                  {isDragging
                    ? "Drop your screenshot here…"
                    : file
                      ? "Click or drag to replace file"
                      : "📁 Click to choose a file, or drag & drop here"}
                </p>
              </div>

              {/* Phase-8 refinement: file info, preview, and clear button */}
              {file && (
                <div style={{ marginTop: "0.5rem" }}>
                  <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
                    <span className="form-hint" style={{ flex: 1, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", minWidth: 0 }}>
                      {fileName} — {(file.size / 1024).toFixed(0)} KB
                      {file.size > MAX_FILE_SIZE && (
                        <span style={{ color: "var(--color-danger)", marginLeft: "0.5rem", fontWeight: 600 }}>
                          ⚠ Exceeds 5 MB limit
                        </span>
                      )}
                    </span>
                    <button
                      type="button"
                      onClick={clearFile}
                      style={{
                        background: "none",
                        border: "none",
                        cursor: "pointer",
                        fontSize: "1.1rem",
                        color: "var(--color-slate-400)",
                        padding: "0.25rem",
                      }}
                      title="Remove file"
                    >
                      ✕
                    </button>
                  </div>
                  {filePreview && (
                    <img
                      src={filePreview}
                      alt="Screenshot preview"
                      style={{
                        display: "block",
                        marginTop: "0.5rem",
                        maxWidth: "100%",
                        maxHeight: "200px",
                        borderRadius: "var(--radius-md, 8px)",
                        border: "1px solid var(--color-slate-200, #e2e8f0)",
                        objectFit: "contain",
                      }}
                    />
                  )}
                </div>
              )}
            </div>
            <div className="check-submit-row">
              <span className="check-submit-note">
                {hasNoWallet ? "Add a wallet above to enable verification" : "Text is extracted automatically from your image"}
              </span>
              <button
                type="submit"
                className="btn btn-primary check-verify-btn"
                disabled={loading || hasNoWallet || !file || (file && file.size > MAX_FILE_SIZE)}
                title={hasNoWallet ? "Link a wallet first" : !file ? "Select a screenshot first" : undefined}
              >
                {loading ? "Uploading…" : "📤 Upload & Verify"}
              </button>
            </div>
          </form>
        </div>
      )}

      {/* ── Loading overlay ── */}
      {loading && (
        <div className="loading-state">
          <div className="spinner"></div>
          {tab === "sms" ? (
            <p>Checking message…</p>
          ) : ocrProgress ? (
            <div style={{ textAlign: "center", minWidth: "200px" }}>
              <p style={{ margin: "0 0 0.5rem", fontSize: "0.9rem" }}>
                {ocrProgress.status}
              </p>
              <div style={{
                height: "6px", background: "var(--color-slate-200, #e2e8f0)",
                borderRadius: "3px", overflow: "hidden",
              }}>
                <div style={{
                  height: "100%",
                  width: `${Math.round((ocrProgress.progress || 0) * 100)}%`,
                  background: "var(--color-primary, #3b82f6)",
                  borderRadius: "3px",
                  transition: "width 0.3s ease",
                }} />
              </div>
              <p style={{ margin: "0.4rem 0 0", fontSize: "0.78rem", color: "var(--color-slate-400)" }}>
                {Math.round((ocrProgress.progress || 0) * 100)}%
              </p>
            </div>
          ) : (
            <p>Uploading &amp; analysing…</p>
          )}
        </div>
      )}

      {/* ── OCR Pending notice (screenshot uploaded but analysis not run) ── */}
      {ocrPending && !pred && (
        <div className="message-box success" style={{ marginTop: "1rem" }}>
          <span className="message-icon">📸</span>
          <div>
            <strong>Screenshot received.</strong>
            <p style={{ margin: "0.25rem 0 0", fontSize: "0.9rem" }}>
              {ocrText && !ocrUsable
                ? "Some text was extracted, but it doesn\u2019t look like a standard MTN MoMo notification. You can review it below, or paste the message in the SMS tab for better accuracy."
                : "We couldn\u2019t extract readable text from this image. Try a clearer screenshot, or paste the SMS text in the other tab."
              }
            </p>
            {mc && (
              <p style={{ margin: "0.25rem 0 0", fontSize: "0.85rem", color: "var(--color-slate-400)" }}>
                Check ID: {mc.id || "—"} · Status: {mc.status || "pending"}
              </p>
            )}
          </div>
        </div>
      )}

      {/* ── OCR failed fallback — clear prompt to use SMS tab ── */}
      {!loading && ocrError && !result && tab === "screenshot" && (
        <div className="message-box warning" style={{ marginTop: "1rem" }} role="status">
          <span className="message-icon">⚠️</span>
          <div>
            <strong>Could not read text from this screenshot.</strong>
            <p style={{ margin: "0.35rem 0 0.5rem", fontSize: "0.9rem" }}>
              {ocrError}
            </p>
            <button
              type="button"
              className="btn btn-secondary"
              style={{ fontSize: "0.85rem", padding: "0.3rem 0.8rem" }}
              onClick={() => {
                setTab("sms");
                setError(""); setWarning(""); setOcrError("");
                setResult(null); setOcrText(""); setOcrConfidence(null);
              }}
            >
              Switch to SMS Text tab
            </button>
          </div>
        </div>
      )}

      {/* ── Phase-8 Part 2 refined: OCR Extracted Text with confidence + copy ── */}
      {ocrText && tab === "screenshot" && (
        <div className="form-card" style={{ marginTop: "1rem" }}>
          {/* ocr-header-row: flex-wrap prevents overflow at 375px (title+pills+btn ~380px) */}
          <div className="ocr-header-row">
            <h4 className="section-title" style={{ margin: 0 }}>Extracted Text</h4>
            {ocrConfidence != null && (
              <span className={`ocr-conf-pill ${ocrConfidence >= 0.6 ? "ocr-high" : ocrConfidence >= 0.35 ? "ocr-medium" : "ocr-low"}`}>
                OCR {Math.round(ocrConfidence * 100)}%
              </span>
            )}
            {ocrUsable && (
              <span className="ocr-momo-chip">✓ MoMo text detected</span>
            )}
            <button
              type="button"
              className="ocr-copy-btn"
              onClick={() => { navigator.clipboard.writeText(ocrText); }}
              title="Copy extracted text"
              style={{
                background: "none",
                border: "1px solid var(--color-slate-200, #e2e8f0)",
                borderRadius: "var(--radius-sm, 4px)",
                padding: "0.2rem 0.5rem",
                fontSize: "0.75rem",
                cursor: "pointer",
                color: "var(--color-slate-500)",
              }}
            >
              📋 Copy
            </button>
          </div>

          {/* Low-confidence warning */}
          {ocrLowConfidence && (
            <div className="message-box warning" style={{ marginBottom: "0.5rem", fontSize: "0.85rem" }}>
              <span className="message-icon">⚠️</span>
              Image quality is low — some text may be missing or misread. For best results, try a clearer screenshot or paste the SMS text directly.
            </div>
          )}

          <div
            className="raw-text-block"
            style={{ maxHeight: "200px" }}
          >
            {ocrText}
          </div>
          <p className="form-hint" style={{ textAlign: "left", marginTop: "0.4rem" }}>
            {ocrText.length} characters extracted from your screenshot{pred ? " and analyzed below" : ""}.
          </p>
        </div>
      )}

      {/* ── OCR error notice (OCR failed but screenshot was saved) ── */}
      {ocrError && !ocrPending && !ocrText && tab === "screenshot" && (
        <div className="message-box warning" style={{ marginTop: "1rem" }}>
          <span className="message-icon">⚠️</span>
          <div>
            <strong>We couldn\u2019t read this image.</strong>
            <p style={{ margin: "0.25rem 0 0", fontSize: "0.85rem" }}>
              This usually happens with blurry images. Try a clearer screenshot, or paste the message in the SMS tab.
            </p>
          </div>
        </div>
      )}

      {/* ══════════════════════════════════════════════
          RESULT CARD — distinct styling per verdict
          ══════════════════════════════════════════════ */}
      {pred && (
        <div
          ref={resultRef}
          className={`result-card ${verdictClass(pred.predicted_label)}`}
          aria-live="polite"
          aria-atomic="true"
          aria-label={`Analysis result: ${pred.predicted_label?.replace(/_/g, " ") || "unknown"}`}
        >

          {/* Source badge for screenshot results */}
          {tab === "screenshot" && mc?.source_channel === "screenshot" && (
            <div className="source-chip">📸 Analyzed from screenshot</div>
          )}

          {/* Big verdict banner */}
          <div className="verdict-banner">
            <span className="verdict-icon">{verdictIcon(pred.predicted_label)}</span>
            <div className="verdict-text">
              <span className={`status-pill ${pillClass(pred.predicted_label)}`}>
                {VERDICT_LABEL[pred.predicted_label] || (pred.predicted_label || "").replace("_", " ")}
              </span>
              <p className="verdict-headline">{VERDICT_HEADLINE[pred.predicted_label] || "Could not determine"}</p>
            </div>
            {pred.predicted_label !== "out_of_scope" && (
              <div className="verdict-score">
                <span className="verdict-pct">{Math.round((pred.confidence_score || 0) * 100)}%</span>
                <span className="verdict-sub">confidence</span>
              </div>
            )}
          </div>

          {/* Confidence bar — hidden for out-of-scope (no fraud score was calculated) */}
          {pred.predicted_label !== "out_of_scope" && (
            <div className="confidence-track">
              <div
                className="confidence-fill"
                style={{
                  width: `${Math.round((pred.confidence_score || 0) * 100)}%`,
                  background: confidenceColor(pred.predicted_label),
                }}
              />
            </div>
          )}

          {/* Action guidance */}
          {VERDICT_GUIDANCE[pred.predicted_label] && (
            <div className="verdict-guidance">
              {VERDICT_GUIDANCE[pred.predicted_label].split('\n').map((line, i) => (
                <p key={i} style={{ margin: i === 0 ? 0 : "0.25rem 0 0" }}>{line}</p>
              ))}
            </div>
          )}

          {/* Key concern — shown first as a quick summary */}
          {keyConcern(pred) && (
            <div className="key-concern" style={{ marginTop: "1rem" }}>
              {keyConcern(pred)}
            </div>
          )}

          {/* Explanation — split into short sentence chunks */}
          {pred.explanation && (() => {
            const chunks = splitExplanation(pred.explanation, pred.predicted_label);
            // out_of_scope explanations are neutral informational notes
            const boxType = pred.predicted_label === "genuine" ? "success"
              : pred.predicted_label === "out_of_scope" ? "info"
              : pred.predicted_label === "suspicious" ? "warning" : "error";
            return (
              <div className={`message-box ${boxType}`} style={{ marginTop: "0.75rem" }}>
                <span className="message-icon">💡</span>
                <div>
                  {chunks.length <= 1
                    ? <span>{chunks[0]}</span>
                    : <ul style={{ margin: 0, paddingLeft: "1.1rem" }}>
                        {chunks.map((s, i) => <li key={i} style={{ marginBottom: "0.2rem" }}>{s}</li>)}
                      </ul>
                  }
                </div>
              </div>
            );
          })()}

          {/* Risk scores — hidden for out-of-scope results (fraud model didn't run) */}
          {pred.predicted_label !== "out_of_scope" && (
            <>
              <h4 className="section-title" style={{ marginTop: "1.25rem" }}>Risk Breakdown</h4>
              <div className="risk-grid">
                {RISK_ITEMS.map(({ label, key }) => (
                  <div className={`risk-item ${riskColor(pred[key])}`} key={key}>
                    <span className="risk-label">{label}</span>
                    <span className="risk-value">
                      {riskLabel(pred[key])}
                      {pred[key] != null && (
                        <span className="risk-detail">({Math.round(pred[key] * 100)}%)</span>
                      )}
                    </span>
                  </div>
                ))}
              </div>
            </>
          )}

          {/* ML model supplementary signal — collapsed for non-technical users */}
          {pred.ml_available && (
            <details className="tech-details">
              <summary>Technical details</summary>
              <div className={`ml-badge ${pred.ml_agrees ? "ml-agrees" : "ml-differs"}`}>
                <strong>ML Model:</strong>{" "}
                {pred.ml_label === "genuine" ? "Genuine" : "Fraudulent"}
                {pred.ml_confidence > 0 && (
                  <span className="ml-conf">({Math.round(pred.ml_confidence * 100)}% confidence)</span>
                )}
                {pred.ml_agrees != null && (
                  <span className="ml-status">{pred.ml_agrees ? "✓ Agrees with rules" : "⚡ Differs from rules"}</span>
                )}
              </div>
            </details>
          )}

          {/* Extracted fields (SMS and screenshot when parsed) */}
          {mc && ((mc.sender_name || mc.counterparty_name) || mc.amount != null || mc.mtn_transaction_id) && (
            <>
              <h4 className="section-title" style={{ marginTop: "1.5rem" }}>Transaction Details</h4>
              <div className="extracted-grid">
                {mc.transaction_type && (
                  <div className="extracted-item">
                    <span className="extracted-label">Type</span>
                    <span className="extracted-value">{mc.transaction_type}</span>
                  </div>
                )}
                {mc.mtn_transaction_id && (
                  <div className="extracted-item">
                    <span className="extracted-label">MTN Txn ID</span>
                    <span className="extracted-value mono">{mc.mtn_transaction_id}</span>
                  </div>
                )}
                {(mc.sender_name || mc.counterparty_name) && (
                  <div className="extracted-item">
                    <span className="extracted-label">Sender</span>
                    <span className="extracted-value">{mc.sender_name || mc.counterparty_name}</span>
                  </div>
                )}
                {(mc.sender_number || mc.counterparty_number) && (
                  <div className="extracted-item">
                    <span className="extracted-label">Sender Number</span>
                    <span className="extracted-value mono">{mc.sender_number || mc.counterparty_number}</span>
                  </div>
                )}
                {mc.amount != null && (
                  <div className="extracted-item">
                    <span className="extracted-label">Amount</span>
                    <span className="extracted-value amount">{mc.currency || "GHS"} {mc.amount}</span>
                  </div>
                )}
                {mc.balance_after != null && (
                  <div className="extracted-item">
                    <span className="extracted-label">Balance After</span>
                    <span className="extracted-value">GHS {mc.balance_after}</span>
                  </div>
                )}
                {mc.available_balance != null && (
                  <div className="extracted-item">
                    <span className="extracted-label">Available Balance</span>
                    <span className="extracted-value">GHS {mc.available_balance}</span>
                  </div>
                )}
                {mc.fee != null && (
                  <div className="extracted-item">
                    <span className="extracted-label">Fee</span>
                    <span className="extracted-value">GHS {mc.fee}</span>
                  </div>
                )}
                {mc.parser_confidence != null && (
                  <div className="extracted-item">
                    <span className="extracted-label">Parser Confidence</span>
                    <span className="extracted-value">{Math.round(mc.parser_confidence * 100)}%</span>
                  </div>
                )}
              </div>
            </>
          )}

          {/* Result footer */}
          <div className="result-footer">
            Checked {mc?.created_at ? new Date(mc.created_at).toLocaleString() : "just now"}
          </div>
        </div>
      )}
      </div>
    </PageLayout>
  );
}

export default CheckMessage;
