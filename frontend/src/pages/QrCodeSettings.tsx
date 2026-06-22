/**
 * Vitar — QR Code Settings
 * Professional QR code management page with large display, download, and regenerate.
 */

import { useEffect, useState } from "react";
import { Download, RefreshCw, Printer, QrCode, ExternalLink, FileText } from "lucide-react";

interface QrInfo {
  qr_code_path: string | null;
  portal_url: string;
  slug: string;
}

export default function QrCodeSettings() {
  const [qrInfo, setQrInfo] = useState<QrInfo | null>(null);
  const [loading, setLoading] = useState(true);
  const [regenerating, setRegenerating] = useState(false);
  const [downloadingPoster, setDownloadingPoster] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  // qr_code_path is an absolute path served by the static /uploads mount
  // (nginx / FastAPI StaticFiles) — it must NOT be prefixed with /api,
  // which only fronts the versioned JSON API at /api/v1/*.
  const qrSrc = qrInfo?.qr_code_path ?? null;

  const fetchQr = () => {
    setLoading(true);
    fetch("/api/v1/qr/me", { credentials: "include" })
      .then((r) => (r.ok ? r.json() : null))
      .then((data) => { if (data) setQrInfo(data); })
      .catch(() => setError("Could not load QR code"))
      .finally(() => setLoading(false));
  };

  useEffect(() => { fetchQr(); }, []);

  const getCsrf = () =>
    document.cookie.split("; ").find((r) => r.startsWith("vitar_csrf="))?.split("=")[1] ?? "";

  const handleRegenerate = async () => {
    setRegenerating(true);
    setError(null);
    setSuccess(null);
    try {
      const res = await fetch("/api/v1/qr/me/regenerate", {
        method: "POST",
        credentials: "include",
        headers: { "X-CSRF-Token": getCsrf() },
      });
      if (!res.ok) throw new Error();
      const data = await res.json();
      setQrInfo((prev) => (prev ? { ...prev, ...data } : data));
      setSuccess("QR code regenerated successfully.");
    } catch {
      setError("Could not regenerate QR code. Please try again.");
    } finally {
      setRegenerating(false);
    }
  };

  const handleDownloadPoster = async () => {
    setDownloadingPoster(true);
    setError(null);
    try {
      const res = await fetch("/api/v1/qr/me/poster", { credentials: "include" });
      if (!res.ok) throw new Error();
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = `${qrInfo?.slug ?? "clinic"}-poster.pdf`;
      link.click();
      URL.revokeObjectURL(url);
    } catch {
      setError("Could not generate the printable poster.");
    } finally {
      setDownloadingPoster(false);
    }
  };

  const handlePrint = () => {
    if (!qrSrc) return;
    const w = window.open("", "_blank");
    if (!w) return;
    w.document.write(`<html><body style="margin:0;display:flex;align-items:center;justify-content:center;min-height:100vh;">
      <img src="${qrSrc}" style="width:400px;height:400px;" onload="window.print();" />
    </body></html>`);
    w.document.close();
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-[400px]">
        <RefreshCw className="w-6 h-6 text-teal-500 animate-spin" />
      </div>
    );
  }

  return (
    <div className="p-4 sm:p-8 max-w-2xl mx-auto space-y-6">
      {/* Page header */}
      <div>
        <div className="flex items-center gap-2 text-teal-600 mb-1">
          <QrCode className="w-5 h-5" />
          <span className="text-xs font-semibold uppercase tracking-widest">Settings</span>
        </div>
        <h1 className="text-2xl font-bold text-slate-900">Clinic QR Code</h1>
        <p className="text-slate-500 text-sm mt-1">
          Display this code at your front desk or print it for patients to scan and book appointments instantly.
        </p>
      </div>

      {/* Alerts */}
      {error && (
        <div className="bg-red-50 border border-red-200 text-red-700 text-sm rounded-xl px-4 py-3">
          {error}
        </div>
      )}
      {success && (
        <div className="bg-green-50 border border-green-200 text-green-700 text-sm rounded-xl px-4 py-3">
          {success}
        </div>
      )}

      {/* QR Card — large, centred, professional */}
      <div className="bg-white border border-slate-200 rounded-2xl shadow-sm overflow-hidden">
        {/* QR display area */}
        <div className="flex flex-col items-center px-8 py-10 bg-gradient-to-b from-slate-50 to-white border-b border-slate-100">
          {qrSrc ? (
            <div className="p-4 bg-white rounded-2xl shadow-md border border-slate-100">
              <img
                src={qrSrc}
                alt="Clinic QR code"
                className="w-64 h-64 sm:w-72 sm:h-72 object-contain"
              />
            </div>
          ) : (
            <div className="w-64 h-64 sm:w-72 sm:h-72 flex flex-col items-center justify-center rounded-2xl bg-slate-100 border-2 border-dashed border-slate-300 text-slate-400 text-sm text-center p-6 gap-3">
              <QrCode className="w-10 h-10 text-slate-300" />
              <p>No QR code generated yet.<br />Click <strong>Generate QR Code</strong> below.</p>
            </div>
          )}

          {/* Portal URL */}
          {qrInfo?.portal_url && (
            <a
              href={qrInfo.portal_url}
              target="_blank"
              rel="noopener noreferrer"
              className="mt-5 flex items-center gap-1.5 text-xs text-teal-600 hover:text-teal-700 hover:underline transition-colors"
            >
              <ExternalLink className="w-3.5 h-3.5" />
              {qrInfo.portal_url}
            </a>
          )}
        </div>

        {/* Action buttons */}
        <div className="px-6 py-5 space-y-3">
          {/* Primary actions row */}
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
            {qrSrc && (
              <a
                href={qrSrc}
                download={`${qrInfo?.slug ?? "clinic"}-qr.png`}
                className="flex items-center justify-center gap-2 bg-teal-600 hover:bg-teal-700 text-white font-semibold py-2.5 rounded-xl transition-colors text-sm"
              >
                <Download className="w-4 h-4" />
                Download PNG
              </a>
            )}
            {qrSrc && (
              <button
                onClick={handlePrint}
                className="flex items-center justify-center gap-2 border border-slate-200 text-slate-700 hover:bg-slate-50 font-medium py-2.5 rounded-xl transition-colors text-sm"
              >
                <Printer className="w-4 h-4" />
                Print QR
              </button>
            )}
            <button
              onClick={handleRegenerate}
              disabled={regenerating}
              className={`flex items-center justify-center gap-2 border font-medium py-2.5 rounded-xl transition-colors text-sm disabled:opacity-60
                ${qrSrc ? "border-slate-200 text-slate-700 hover:bg-slate-50" : "border-teal-600 bg-teal-600 text-white hover:bg-teal-700"}`}
            >
              <RefreshCw className={`w-4 h-4 ${regenerating ? "animate-spin" : ""}`} />
              {regenerating ? "Generating..." : qrSrc ? "Regenerate" : "Generate QR Code"}
            </button>
          </div>

          {/* PDF poster — full width, prominent */}
          <button
            onClick={handleDownloadPoster}
            disabled={downloadingPoster || !qrSrc}
            className="w-full flex items-center justify-center gap-2 bg-slate-900 hover:bg-slate-800 disabled:opacity-40 text-white font-semibold py-3 rounded-xl transition-colors text-sm"
          >
            <FileText className="w-4 h-4" />
            {downloadingPoster ? "Generating PDF..." : "Download printable poster (PDF)"}
          </button>
        </div>
      </div>

      {/* How to use */}
      <div className="bg-teal-50 border border-teal-100 rounded-xl p-5">
        <h3 className="text-sm font-semibold text-teal-800 mb-3">How to use your QR code</h3>
        <ul className="space-y-2 text-sm text-teal-700">
          <li className="flex gap-2"><span className="font-bold text-teal-500 flex-shrink-0">1.</span>Print or display the QR code at your reception area.</li>
          <li className="flex gap-2"><span className="font-bold text-teal-500 flex-shrink-0">2.</span>Patients scan it with any phone camera to open your booking page.</li>
          <li className="flex gap-2"><span className="font-bold text-teal-500 flex-shrink-0">3.</span>They register and book — no app download needed.</li>
          <li className="flex gap-2"><span className="font-bold text-teal-500 flex-shrink-0">4.</span>Appointments appear in your dashboard instantly.</li>
        </ul>
      </div>

      <p className="text-xs text-slate-400 text-center">Powered by Vitar Healthcare Platform</p>
    </div>
  );
}
