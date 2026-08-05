/**
 * Vitar - Public Clinic Directory Page (Phase 2)
 *
 * /clinic/{slug} — a lightweight landing page so a patient can confirm
 * they've found the right clinic before booking. Not a profile system:
 * only renders what the Phase 1 public endpoint actually returns, no
 * placeholder content for missing fields. Sibling of PublicBookingPage,
 * same visual language, same "no login" reality — a single Book
 * Appointment action routes straight into the existing booking flow
 * (see /book/:slug — Vitar has no patient accounts to sign into).
 *
 * OG/JSON-LD tags are set client-side (no react-helmet-async or any other
 * meta-tag manager exists in this codebase, and there's no SSR/prerendering
 * to make them reliably crawlable by non-JS bots). This helps Google (which
 * executes JS) and keeps the tab title/meta correct for real visitors, but
 * WhatsApp/SMS link-preview bots won't see them — that needs real
 * server-side rendering or bot-detection middleware, neither of which
 * exists today; flagged as a known follow-up, not solved here.
 */
import { useEffect } from 'react';
import { useParams, Link } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { MapPin, Phone, Clock, Stethoscope, Loader2 } from 'lucide-react';
import { publicClinicsApi } from '@/lib/api/services';

export default function ClinicPage() {
  const { slug } = useParams<{ slug: string }>();
  const { data: clinic, isLoading, isError } = useQuery({
    queryKey: ['clinic-directory', slug],
    queryFn: () => publicClinicsApi.getBySlug(slug!),
    enabled: !!slug,
    retry: 1,
  });

  useEffect(() => {
    if (!clinic) return;
    const prevTitle = document.title;
    document.title = `${clinic.name} — Book an Appointment | Vitar`;
    const tags = setMetaTags(clinic, slug!);
    const ld = setJsonLd(clinic);
    return () => {
      document.title = prevTitle;
      tags.forEach((t) => t.remove());
      ld.remove();
    };
  }, [clinic, slug]);

  if (isLoading) return (
    <div className="min-h-screen bg-slate-50 flex items-center justify-center">
      <Loader2 className="w-8 h-8 text-teal-600 animate-spin" />
    </div>
  );

  if (isError || !clinic) return (
    <div className="min-h-screen bg-slate-50 flex items-center justify-center px-4">
      <div className="max-w-sm text-center space-y-2">
        <h1 className="text-xl font-bold text-slate-900">Clinic not found</h1>
        <p className="text-slate-500 text-sm">
          This link may be mistyped, or the clinic isn't listed. Please check the link with the clinic directly.
        </p>
      </div>
    </div>
  );

  return (
    <div className="min-h-screen bg-slate-50">
      <div className="bg-teal-700 text-white py-10 px-4">
        <div className="max-w-2xl mx-auto text-center">
          {/* Logo space — reserved square, text-only until logo_url exists for a clinic */}
          <div className="w-16 h-16 mx-auto mb-4 rounded-2xl bg-white/10 flex items-center justify-center overflow-hidden">
            {clinic.logo_url ? (
              <img src={clinic.logo_url} alt={`${clinic.name} logo`} className="w-full h-full object-cover" />
            ) : (
              <span className="text-xl font-bold">{clinic.name.charAt(0)}</span>
            )}
          </div>
          <h1 className="text-3xl font-bold">{clinic.name}</h1>
        </div>
      </div>

      <div className="max-w-2xl mx-auto px-4 py-8 space-y-4">
        <div className="bg-white rounded-2xl border border-slate-200 shadow-sm p-6 space-y-4">
          {clinic.address && (
            <div className="flex items-start gap-3">
              <MapPin className="w-5 h-5 text-teal-600 flex-shrink-0 mt-0.5" />
              <p className="text-sm text-slate-700">{clinic.address}</p>
            </div>
          )}
          {clinic.phone && (
            <div className="flex items-start gap-3">
              <Phone className="w-5 h-5 text-teal-600 flex-shrink-0 mt-0.5" />
              <p className="text-sm text-slate-700">{clinic.phone}</p>
            </div>
          )}
          {clinic.opening_hours && (
            <div className="flex items-start gap-3">
              <Clock className="w-5 h-5 text-teal-600 flex-shrink-0 mt-0.5" />
              <p className="text-sm text-slate-700">{clinic.opening_hours}</p>
            </div>
          )}
          {clinic.services?.length > 0 && (
            <div className="flex items-start gap-3">
              <Stethoscope className="w-5 h-5 text-teal-600 flex-shrink-0 mt-0.5" />
              <div className="flex flex-wrap gap-1.5">
                {clinic.services.map((s: string) => (
                  <span key={s} className="text-xs font-medium bg-teal-50 text-teal-700 px-2.5 py-1 rounded-full">{s}</span>
                ))}
              </div>
            </div>
          )}
        </div>

        <Link
          to={`/book/${slug}`}
          className="block w-full text-center bg-teal-600 hover:bg-teal-700 text-white font-semibold py-3 rounded-xl transition-colors"
        >
          Book Appointment
        </Link>
      </div>
    </div>
  );
}

function setMetaTags(clinic: { name: string; address?: string }, slug: string) {
  const description = clinic.address
    ? `Book an appointment with ${clinic.name} — ${clinic.address}. Powered by Vitar.`
    : `Book an appointment with ${clinic.name}. Powered by Vitar.`;
  const url = `${window.location.origin}/clinic/${slug}`;
  const entries: [string, string][] = [
    ['og:title', `${clinic.name} — Book an Appointment`],
    ['og:description', description],
    ['og:image', `${window.location.origin}/og-image.png`],
    ['og:url', url],
    ['og:type', 'website'],
  ];
  return entries.map(([property, content]) => {
    const tag = document.createElement('meta');
    tag.setAttribute('property', property);
    tag.setAttribute('content', content);
    document.head.appendChild(tag);
    return tag;
  });
}

function setJsonLd(clinic: { name: string; address?: string; phone?: string; opening_hours?: string }) {
  const script = document.createElement('script');
  script.type = 'application/ld+json';
  script.text = JSON.stringify({
    '@context': 'https://schema.org',
    '@type': 'MedicalOrganization',
    name: clinic.name,
    ...(clinic.address ? { address: clinic.address } : {}),
    ...(clinic.phone ? { telephone: clinic.phone } : {}),
    ...(clinic.opening_hours ? { openingHours: clinic.opening_hours } : {}),
  });
  document.head.appendChild(script);
  return script;
}
