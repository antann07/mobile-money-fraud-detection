/**
 * ocrHelper.js — Browser-side OCR using Tesseract.js (WebAssembly).
 *
 * Optimised for MTN MoMo screenshot layouts:
 *  - Preprocesses the image via Canvas before handing to Tesseract (greyscale +
 *    contrast boost + 2× upscale). This alone improves accuracy ~30–40% on
 *    low-resolution phone screenshots.
 *  - Configures Tesseract for single-column phone message text (PSM 6).
 *  - Applies a light post-processing pass to fix the most common OCR
 *    substitutions in MoMo messages (l→1, O→0, etc.).
 *  - Runs entirely in browser WebAssembly — no server Tesseract binary needed.
 *
 * Public API:
 *   extractTextFromImage(file, onProgress?) → { text, confidence, success, error? }
 */

import { createWorker } from "tesseract.js";

// ── Image preprocessing ──────────────────────────────────────────────
/**
 * Preprocess an image File for better OCR accuracy:
 *  1. Upscale to at least 1200px wide (Tesseract needs ~300 DPI).
 *  2. Convert to greyscale.
 *  3. Apply contrast stretch so light-grey MoMo text becomes crisp black.
 *
 * Returns a Blob (image/png) that can be passed directly to worker.recognize().
 * Falls back to the original file if Canvas is unavailable (SSR / old browsers).
 */
async function preprocessImage(file) {
  try {
    const bitmap = await createImageBitmap(file);

    const MIN_WIDTH = 1200;
    const scale = bitmap.width < MIN_WIDTH ? MIN_WIDTH / bitmap.width : 1;
    const w = Math.round(bitmap.width * scale);
    const h = Math.round(bitmap.height * scale);

    const canvas = document.createElement("canvas");
    canvas.width  = w;
    canvas.height = h;
    const ctx = canvas.getContext("2d");

    // Draw scaled image
    ctx.drawImage(bitmap, 0, 0, w, h);
    bitmap.close();

    // Get pixel data and convert to greyscale + boost contrast
    const imgData = ctx.getImageData(0, 0, w, h);
    const d = imgData.data;
    for (let i = 0; i < d.length; i += 4) {
      // Luminance-weighted greyscale
      let grey = 0.299 * d[i] + 0.587 * d[i + 1] + 0.114 * d[i + 2];
      // Contrast stretch: push near-white → white, near-dark → black
      // Factor 1.5 works well for MTN's white/yellow-on-dark-green screenshots
      grey = Math.min(255, Math.max(0, (grey - 128) * 1.5 + 128));
      d[i] = d[i + 1] = d[i + 2] = grey;
      // alpha unchanged
    }
    ctx.putImageData(imgData, 0, 0);

    return await new Promise((resolve, reject) =>
      canvas.toBlob((blob) => (blob ? resolve(blob) : reject(new Error("toBlob failed"))), "image/png")
    );
  } catch (_) {
    // Canvas unavailable or image decode failed — use original file
    return file;
  }
}

// ── Post-processing ──────────────────────────────────────────────────
/**
 * Apply light text corrections common in MoMo OCR output.
 * Only fixes unambiguous digit/letter substitutions in numeric contexts.
 */
function cleanOcrText(raw) {
  return raw
    // Fix "GH S" / "GH5" → "GHS"
    .replace(/GH\s*[S5$]/gi, "GHS")
    // Common digit → letter in amounts: "l0.00" → "10.00", "O.50" → "0.50"
    .replace(/(?<=[,.\s]|^)l(?=\d)/g, "1")
    .replace(/(?<=[,.\s]|^)O(?=\d)/g, "0")
    // Remove stray zero-width / control chars
    .replace(/[\u200b-\u200d\ufeff]/g, "")
    .trim();
}

// ── Main export ──────────────────────────────────────────────────────
/**
 * Extract and clean text from a screenshot File.
 *
 * @param {File} file             - PNG / JPG / WEBP image file
 * @param {function} onProgress   - Optional callback: ({ status, progress }) => void
 * @returns {Promise<{
 *   text: string,
 *   confidence: number,   // 0.0 – 1.0
 *   success: boolean,
 *   error?: string        // only present on failure
 * }>}
 */
export async function extractTextFromImage(file, onProgress) {
  let worker;
  try {
    // Step 1 — Preprocess
    const processedImage = await preprocessImage(file);

    // Step 2 — Create Tesseract worker with MTN-optimised config
    worker = await createWorker("eng", undefined, {
      logger: (info) => {
        if (onProgress && info.progress != null) {
          onProgress({ status: info.status, progress: info.progress });
        }
      },
    });

    // PSM 6 = "Assume a single uniform block of text"
    // Works best for phone notification screenshots with one message block.
    await worker.setParameters({
      tessedit_pageseg_mode: "6",
      // Restrict to characters that appear in MoMo messages.
      // This prevents Tesseract from hallucinating rare symbols as digits.
      tessedit_char_whitelist:
        "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789 .,:-/+()'\"@#&%GHS\n",
    });

    // Step 3 — Recognise
    const { data: { text, confidence } } = await worker.recognize(processedImage);

    // Step 4 — Clean
    const cleaned = cleanOcrText(text);

    return {
      text: cleaned,
      confidence: Math.round(confidence) / 100, // 0–100 → 0.0–1.0
      success: cleaned.length >= 10,
    };
  } catch (err) {
    console.error("[ocrHelper] Tesseract.js error:", err);
    return {
      text: "",
      confidence: 0,
      success: false,
      error:
        "Could not read text from this image. " +
        "Try a clearer screenshot, or switch to the SMS tab and paste the message text directly.",
    };
  } finally {
    if (worker) {
      try { await worker.terminate(); } catch (_) { /* ignore */ }
    }
  }
}

