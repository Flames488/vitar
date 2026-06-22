/**
 * Vitar — Hospital/Clinic QR Onboarding: Public Portal Page
 *
 * Reached when a patient scans a clinic's printed QR code. URL pattern:
 *   /portal/:slug
 *
 * Route is registered in App.tsx:
 *   <Route path="/portal/:slug" element={<Portal />} />
 */

import VitarLogo from '@/components/shared/VitarLogo';
import { useEffect, useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { bookingApi } from '@/lib/api/services';
import { getApiError } from '@/lib/api/client';

interface ClinicPortalInfo {
  id: string;
  name: string;
  slug: string;
  logo_url: string;
  address: string;
  city: string;
  phone: string;
  booking_enabled: boolean;
}

type ViewMode = "landing" | "register" | "registered";

export default function Portal() {
  const { slug } = useParams<{ slug: string }>();
  const navigate = useNavigate();

  const [clinic, setClinic] = useState<ClinicPortalInfo | null>(null);
  const [loading, setLoading] = useState(true);
  const [notFound, setNotFound] = useState(false);
  const [view, setView] = useState<ViewMode>("landing");

  const [form, setForm] = useState({ full_name: "", phone: "", email: "" });
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [welcomeMessage, setWelcomeMessage] = useState("");

  useEffect(() => {
    if (!slug) return;
    bookingApi.getPortal(slug)
      .then((data) => setClinic(data))
      .catch(() => setNotFound(true))
      .finally(() => setLoading(false));
  }, [slug]);

  const handleRegister = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!slug) return;
    setSubmitting(true);
    setError(null);
    try {
      const data = await bookingApi.registerPatient(slug, {
        full_name: form.full_name,
        phone: form.phone,
        email: form.email || undefined,
      });
      setWelcomeMessage(data.message || `You're registered at ${clinic?.name}.`);
      setView("registered");
    } catch (err) {
      setError(getApiError(err));
    } finally {
      setSubmitting(false);
    }
  };

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-slate-50">
        <p className="text-slate-500">Loading...</p>
      </div>
    );
  }

  if (notFound || !clinic) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-slate-50 px-6">
        <div className="text-center max-w-sm">
          <h1 className="text-xl font-semibold text-slate-900 mb-2">
            Page not found
          </h1>
          <p className="text-slate-500">
            This hospital/clinic link is invalid or no longer active.
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-slate-50 flex flex-col items-center px-6 py-10">
      <div className="w-full max-w-sm">
        {/* Branding */}
        <div className="flex flex-col items-center text-center mb-8">
          {clinic.logo_url ? (
            <img
              src={clinic.logo_url}
              alt={clinic.name}
              className="w-16 h-16 rounded-full object-cover mb-4 border border-slate-200"
            />
          ) : (
            <div className="mb-4">
              <VitarLogo size={64} />
            </div>
          )}
          <h1 className="text-2xl font-bold text-slate-900">{clinic.name}</h1>
          {(clinic.address || clinic.city) && (
            <p className="text-sm text-slate-500 mt-1">
              {[clinic.address, clinic.city].filter(Boolean).join(", ")}
            </p>
          )}
        </div>

        {view === "landing" && (
          <div className="space-y-3">
            <button
              onClick={() => setView("register")}
              className="w-full bg-teal-600 hover:bg-teal-700 text-white font-semibold py-3 rounded-lg transition"
            >
              Register
            </button>
            <button
              onClick={() => navigate(`/login?clinic=${clinic.slug}`)}
              className="w-full border border-slate-300 text-slate-700 font-semibold py-3 rounded-lg hover:bg-slate-100 transition"
            >
              Sign in (staff)
            </button>
            {clinic.booking_enabled && (
              <button
                onClick={() => navigate(`/book/${clinic.slug}`)}
                className="w-full text-teal-700 font-medium py-2 hover:underline"
              >
                Book an appointment instead →
              </button>
            )}
          </div>
        )}

        {view === "register" && (
          <form onSubmit={handleRegister} className="space-y-4">
            {error && (
              <div className="bg-red-50 text-red-700 text-sm rounded-lg p-3">
                {error}
              </div>
            )}
            <div>
              <label className="block text-sm font-medium text-slate-700 mb-1">
                Your name
              </label>
              <input
                type="text"
                required
                value={form.full_name}
                onChange={(e) => setForm({ ...form, full_name: e.target.value })}
                className="w-full border border-slate-300 rounded-lg px-4 py-2.5"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-slate-700 mb-1">
                Phone
              </label>
              <input
                type="tel"
                required
                value={form.phone}
                onChange={(e) => setForm({ ...form, phone: e.target.value })}
                className="w-full border border-slate-300 rounded-lg px-4 py-2.5"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-slate-700 mb-1">
                Email (optional)
              </label>
              <input
                type="email"
                value={form.email}
                onChange={(e) => setForm({ ...form, email: e.target.value })}
                className="w-full border border-slate-300 rounded-lg px-4 py-2.5"
              />
            </div>
            <button
              type="submit"
              disabled={submitting}
              className="w-full bg-teal-600 hover:bg-teal-700 disabled:opacity-60 text-white font-semibold py-3 rounded-lg transition"
            >
              {submitting ? "Registering..." : "Complete registration"}
            </button>
            <button
              type="button"
              onClick={() => setView("landing")}
              className="w-full text-slate-500 text-sm py-1"
            >
              ← Back
            </button>
          </form>
        )}

        {view === "registered" && (
          <div className="text-center space-y-4">
            <div className="w-12 h-12 rounded-full bg-teal-100 text-teal-700 flex items-center justify-center mx-auto text-2xl">
              ✓
            </div>
            <p className="text-slate-700">{welcomeMessage}</p>
            {clinic.booking_enabled && (
              <button
                onClick={() => navigate(`/book/${clinic.slug}`)}
                className="w-full bg-teal-600 hover:bg-teal-700 text-white font-semibold py-3 rounded-lg transition"
              >
                Book an appointment now
              </button>
            )}
          </div>
        )}
      </div>

      <p className="text-xs text-slate-400 mt-10">Powered by Vitar</p>
    </div>
  );
}
