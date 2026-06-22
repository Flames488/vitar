/**
 * Vitar — Clinic Dashboard
 * Advanced, clean, actionable. Every pixel earns its place.
 */

import { useQuery } from '@tanstack/react-query';
import { Link } from 'react-router-dom';
import {
  Calendar, Users, CalendarDays, ArrowRight, Brain,
  AlertTriangle, Plus, Clock, QrCode, X, Download,
  RefreshCw, TrendingUp, TrendingDown, Activity,
  CheckCircle2, XCircle, UserX, Hourglass,
} from 'lucide-react';
import { analyticsApi, appointmentsApi, billingApi } from '@/lib/api/services';
import { useAuthStore } from '@/stores/authStore';
import { formatNaira } from '@/lib/currency';
import { format, isToday } from 'date-fns';
import { useState } from 'react';
import DashboardCountdowns from '@/components/shared/DashboardCountdowns';

const STATUS_META: Record<string, { label: string; cls: string }> = {
  confirmed:  { label: 'Confirmed',  cls: 'bg-blue-100 text-blue-700'   },
  completed:  { label: 'Completed',  cls: 'bg-green-100 text-green-700' },
  cancelled:  { label: 'Cancelled',  cls: 'bg-red-100 text-red-700'     },
  no_show:    { label: 'No-Show',    cls: 'bg-orange-100 text-orange-700'},
  pending:    { label: 'Pending',    cls: 'bg-yellow-100 text-yellow-700'},
};

function riskMeta(score: number) {
  if (score >= 0.75) return { label: 'Critical', cls: 'text-red-600 bg-red-50' };
  if (score >= 0.5)  return { label: 'High',     cls: 'text-orange-600 bg-orange-50' };
  if (score >= 0.25) return { label: 'Medium',   cls: 'text-yellow-600 bg-yellow-50' };
  return                     { label: 'Low',      cls: 'text-green-600 bg-green-50' };
}

function Trend({ value, suffix = '' }: { value: number; suffix?: string }) {
  if (value === 0) return <span className="text-slate-400 text-xs">No change</span>;
  const up = value > 0;
  return (
    <span className={`flex items-center gap-0.5 text-xs font-medium ${up ? 'text-green-600' : 'text-red-500'}`}>
      {up ? <TrendingUp className="w-3 h-3" /> : <TrendingDown className="w-3 h-3" />}
      {Math.abs(value)}{suffix}
    </span>
  );
}

export default function DashboardPage() {
  const clinic  = useAuthStore((s) => s.clinic);
  const formatMoney = formatNaira;
  const [qrOpen, setQrOpen] = useState(false);
  const [qrInfo, setQrInfo] = useState<{ qr_code_path: string; portal_url: string; slug: string } | null>(null);
  const [qrLoading, setQrLoading] = useState(false);

  const openQr = () => {
    setQrOpen(true);
    if (!qrInfo) {
      setQrLoading(true);
      fetch('/api/v1/qr/me', { credentials: 'include' })
        .then(r => r.ok ? r.json() : null)
        .then(d => { if (d) setQrInfo(d); })
        .finally(() => setQrLoading(false));
    }
  };

  // qr_code_path is an absolute path served by the static /uploads mount
  // (nginx / FastAPI StaticFiles) — it must NOT be prefixed with /api,
  // which only fronts the versioned JSON API at /api/v1/*.
  const qrSrc = qrInfo?.qr_code_path ?? null;

  const { data: summary, isLoading: summaryLoading } = useQuery({
    queryKey: ['analytics', 'summary'],
    queryFn: analyticsApi.summary,
    refetchInterval: 60_000,
  });

  const { data: todayData, isLoading: todayLoading } = useQuery({
    queryKey: ['appointments', 'today'],
    queryFn: () => appointmentsApi.list({
      date_from: new Date().toISOString().split('T')[0] + 'T00:00:00',
      date_to:   new Date().toISOString().split('T')[0] + 'T23:59:59',
      limit: 10,
    }),
  });

  const { data: subData } = useQuery({
    queryKey: ['billing', 'subscription'],
    queryFn: billingApi.getSubscription,
    staleTime: 60_000,
  });

  const todayApts   = todayData?.items ?? [];
  const highRisk    = todayApts.filter((a: any) => (a.no_show_risk_score ?? 0) >= 0.5);
  const completed   = todayApts.filter((a: any) => a.status === 'completed').length;
  const pending     = todayApts.filter((a: any) => a.status === 'confirmed' || a.status === 'pending').length;

  // Soonest upcoming appointment today that hasn't started yet (for the countdown card).
  const upcomingApts = todayApts
    .filter((a: any) => ['confirmed', 'pending'].includes(a.status) && new Date(a.scheduled_at).getTime() > Date.now())
    .sort((a: any, b: any) => new Date(a.scheduled_at).getTime() - new Date(b.scheduled_at).getTime());
  const nextAppointment = upcomingApts[0]
    ? {
        scheduled_at: upcomingApts[0].scheduled_at,
        doctor_name: upcomingApts[0].doctor?.full_name,
        patient_name: upcomingApts[0].patient?.full_name,
      }
    : null;

  const kpis = [
    {
      label: "Today's Appointments",
      value: summaryLoading ? null : (summary?.today_appointments ?? 0),
      icon: Calendar,
      tint: 'blue' as const,
      link: '/appointments',
      sub: pending > 0 ? `${pending} pending` : 'All clear',
    },
    {
      label: 'This Week',
      value: summaryLoading ? null : (summary?.week_appointments ?? 0),
      icon: CalendarDays,
      tint: 'teal' as const,
      link: '/appointments',
      sub: 'Scheduled',
    },
    {
      label: 'Total Patients',
      value: summaryLoading ? null : (summary?.total_patients ?? 0),
      icon: Users,
      tint: 'purple' as const,
      link: '/patients',
      sub: 'Registered',
    },
    {
      label: 'Monthly Revenue',
      value: summaryLoading ? null : formatMoney(summary?.month_revenue ?? 0),
      icon: null,
      tint: 'green' as const,
      link: '/earnings',
      sub: 'This month',
    },
  ];

  const tintMap = {
    blue:   { bg: 'bg-blue-50',   text: 'text-blue-600',   ring: 'ring-blue-100'   },
    teal:   { bg: 'bg-teal-50',   text: 'text-teal-600',   ring: 'ring-teal-100'   },
    purple: { bg: 'bg-purple-50', text: 'text-purple-600', ring: 'ring-purple-100' },
    green:  { bg: 'bg-green-50',  text: 'text-green-600',  ring: 'ring-green-100'  },
  };

  return (
    <>
      <div className="p-4 sm:p-6 space-y-5 max-w-7xl mx-auto">

        {/* ── Header ─────────────────────────────────────────────────── */}
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0">
            <p className="text-xs font-semibold uppercase tracking-widest text-teal-600 mb-0.5">
              {format(new Date(), 'EEEE, MMMM d, yyyy')}
            </p>
            <h1 className="text-2xl sm:text-3xl font-bold text-slate-900 truncate leading-tight">
              Good {getGreeting()}{clinic?.name ? `, ${clinic.name}` : ''} 👋
            </h1>
          </div>
          <div className="flex items-center gap-2 flex-shrink-0 pt-1">
            <button
              onClick={openQr}
              className="flex items-center gap-1.5 border border-slate-200 bg-white hover:bg-slate-50 text-slate-600 px-3 py-2 rounded-lg text-sm font-medium transition-colors shadow-sm"
            >
              <QrCode className="w-4 h-4" />
              <span className="hidden sm:inline">QR Code</span>
            </button>
            <Link
              to="/appointments/new"
              className="flex items-center gap-1.5 bg-teal-600 hover:bg-teal-700 text-white px-3 sm:px-4 py-2 rounded-lg text-sm font-semibold transition-colors shadow-sm"
            >
              <Plus className="w-4 h-4" />
              <span className="hidden sm:inline">New Appointment</span>
              <span className="sm:hidden">New</span>
            </Link>
          </div>
        </div>

        {/* ── Live Countdowns ────────────────────────────────────────── */}
        <DashboardCountdowns
          trial={clinic?.trial ? { ...clinic.trial, trial_ends_at: clinic.trial_ends_at } : null}
          nextAppointment={nextAppointment}
          renewal={subData?.subscription ?? null}
        />

        {/* ── High-risk alert ─────────────────────────────────────────── */}
        {highRisk.length > 0 && (
          <div className="relative overflow-hidden bg-gradient-to-r from-amber-500 to-orange-500 rounded-xl p-4 flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3 shadow-md">
            <div className="absolute inset-0 opacity-10 bg-[radial-gradient(ellipse_at_top_right,_white,_transparent)]" />
            <div className="flex items-center gap-3 relative">
              <div className="w-9 h-9 bg-white/20 rounded-full flex items-center justify-center flex-shrink-0">
                <AlertTriangle className="w-5 h-5 text-white" />
              </div>
              <div>
                <p className="font-bold text-white text-sm">
                  {highRisk.length} high-risk appointment{highRisk.length > 1 ? 's' : ''} today
                </p>
                <p className="text-amber-100 text-xs mt-0.5">AI flagged patients likely to no-show — act now</p>
              </div>
            </div>
            <Link
              to="/ai-risk"
              className="relative flex items-center gap-1.5 bg-white/20 hover:bg-white/30 text-white px-4 py-2 rounded-lg text-sm font-semibold transition-colors border border-white/30 flex-shrink-0"
            >
              <Brain className="w-4 h-4" />
              Review Risk
            </Link>
          </div>
        )}

        {/* ── KPI Cards ──────────────────────────────────────────────── */}
        <div className="grid grid-cols-2 xl:grid-cols-4 gap-3 sm:gap-4">
          {kpis.map((k) => {
            const t = tintMap[k.tint];
            const Icon = k.icon;
            return (
              <Link
                key={k.label}
                to={k.link}
                className="group bg-white rounded-xl border border-slate-200 p-4 sm:p-5 hover:shadow-md hover:border-slate-300 transition-all"
              >
                <div className="flex items-start justify-between mb-3">
                  <div className={`w-9 h-9 rounded-lg flex items-center justify-center ${t.bg} ring-4 ${t.ring}`}>
                    {Icon
                      ? <Icon className={`w-4 h-4 ${t.text}`} />
                      : <span className={`text-base font-bold ${t.text}`}>₦</span>
                    }
                  </div>
                  <ArrowRight className="w-3.5 h-3.5 text-slate-300 group-hover:text-teal-500 group-hover:translate-x-0.5 transition-all mt-1" />
                </div>
                <p className="text-slate-500 text-xs font-medium truncate">{k.label}</p>
                <p className="text-2xl font-bold text-slate-900 mt-0.5 leading-none">
                  {k.value === null ? (
                    <span className="inline-block w-12 h-6 bg-slate-100 rounded animate-pulse" />
                  ) : k.value}
                </p>
                <p className="text-xs text-slate-400 mt-1">{k.sub}</p>
              </Link>
            );
          })}
        </div>

        {/* ── Quick Stats Strip ───────────────────────────────────────── */}
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
          {[
            { label: 'Completed today', value: completed, icon: CheckCircle2, cls: 'text-green-600' },
            { label: 'High risk',       value: highRisk.length, icon: AlertTriangle, cls: 'text-orange-500' },
            { label: 'Pending',         value: pending,   icon: Hourglass,     cls: 'text-blue-500' },
            { label: 'No-shows (wk)',   value: summary?.week_no_shows ?? 0, icon: UserX, cls: 'text-red-500' },
          ].map((s) => (
            <div key={s.label} className="bg-white rounded-lg border border-slate-200 px-4 py-3 flex items-center gap-3">
              <s.icon className={`w-4 h-4 flex-shrink-0 ${s.cls}`} />
              <div className="min-w-0">
                <p className="text-lg font-bold text-slate-900 leading-none">{s.value}</p>
                <p className="text-xs text-slate-400 mt-0.5 truncate">{s.label}</p>
              </div>
            </div>
          ))}
        </div>

        {/* ── Today's Appointments ────────────────────────────────────── */}
        <div className="bg-white rounded-xl border border-slate-200 overflow-hidden">
          <div className="flex items-center justify-between px-5 py-4 border-b border-slate-100">
            <div className="flex items-center gap-2">
              <Activity className="w-4 h-4 text-teal-600" />
              <h2 className="font-semibold text-slate-900 text-sm">Today's Schedule</h2>
              {todayApts.length > 0 && (
                <span className="bg-teal-100 text-teal-700 text-xs font-bold px-2 py-0.5 rounded-full">
                  {todayApts.length}
                </span>
              )}
            </div>
            <Link to="/appointments" className="text-teal-600 text-xs font-semibold hover:text-teal-700 flex items-center gap-1">
              View all <ArrowRight className="w-3 h-3" />
            </Link>
          </div>

          {todayLoading ? (
            <div className="divide-y divide-slate-50">
              {[1,2,3].map(i => (
                <div key={i} className="flex items-center gap-4 px-5 py-4 animate-pulse">
                  <div className="w-9 h-9 rounded-full bg-slate-100 flex-shrink-0" />
                  <div className="flex-1 space-y-2">
                    <div className="h-3 bg-slate-100 rounded w-32" />
                    <div className="h-2.5 bg-slate-100 rounded w-24" />
                  </div>
                  <div className="h-5 bg-slate-100 rounded w-16" />
                </div>
              ))}
            </div>
          ) : todayApts.length === 0 ? (
            <div className="py-14 text-center">
              <div className="w-14 h-14 bg-slate-50 rounded-full flex items-center justify-center mx-auto mb-3">
                <Calendar className="w-7 h-7 text-slate-300" />
              </div>
              <p className="text-slate-500 text-sm font-medium">No appointments today</p>
              <p className="text-slate-400 text-xs mt-1 mb-4">Your schedule is clear</p>
              <Link
                to="/appointments/new"
                className="inline-flex items-center gap-1.5 bg-teal-600 hover:bg-teal-700 text-white text-sm font-semibold px-4 py-2 rounded-lg transition-colors"
              >
                <Plus className="w-3.5 h-3.5" /> Schedule appointment
              </Link>
            </div>
          ) : (
            <div className="divide-y divide-slate-50">
              {todayApts.map((apt: any) => {
                const risk = riskMeta(apt.no_show_risk_score ?? 0);
                const statusM = STATUS_META[apt.status] ?? { label: apt.status, cls: 'bg-slate-100 text-slate-600' };
                const initials = apt.patient?.full_name?.split(' ').map((n: string) => n[0]).join('').slice(0,2) ?? '?';
                return (
                  <Link
                    key={apt.id}
                    to={`/appointments/${apt.id}`}
                    className="flex items-center gap-3 px-5 py-3.5 hover:bg-slate-50/80 transition-colors"
                  >
                    {/* Avatar */}
                    <div className="w-9 h-9 rounded-full bg-gradient-to-br from-teal-400 to-teal-600 text-white flex items-center justify-center font-bold text-xs flex-shrink-0 shadow-sm">
                      {initials}
                    </div>
                    {/* Info */}
                    <div className="flex-1 min-w-0">
                      <p className="font-semibold text-slate-900 text-sm truncate">{apt.patient?.full_name}</p>
                      <p className="text-slate-400 text-xs truncate">Dr. {apt.doctor?.full_name}</p>
                    </div>
                    {/* Time + badges */}
                    <div className="flex items-center gap-2 flex-shrink-0">
                      <div className="flex items-center gap-1 text-slate-400 text-xs">
                        <Clock className="w-3 h-3" />
                        {format(new Date(apt.scheduled_at), 'h:mm a')}
                      </div>
                      {(apt.no_show_risk_score ?? 0) >= 0.5 && (
                        <span className={`hidden sm:inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-xs font-semibold ${risk.cls}`}>
                          <Brain className="w-3 h-3" />
                          {Math.round((apt.no_show_risk_score ?? 0) * 100)}%
                        </span>
                      )}
                      <span className={`px-2 py-0.5 rounded-full text-xs font-semibold ${statusM.cls}`}>
                        {statusM.label}
                      </span>
                      <ArrowRight className="w-3.5 h-3.5 text-slate-300 hidden sm:block" />
                    </div>
                  </Link>
                );
              })}
            </div>
          )}
        </div>

        {/* ── Quick Links ─────────────────────────────────────────────── */}
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
          {[
            { to: '/patients',     label: 'Patients',     icon: Users,          desc: 'View & manage'    },
            { to: '/ai-risk',      label: 'AI Risk',      icon: Brain,          desc: 'No-show prediction'},
            { to: '/waiting-list', label: 'Waiting List', icon: Hourglass,      desc: 'Queue management' },
            { to: '/analytics',    label: 'Analytics',    icon: TrendingUp,     desc: 'Reports & trends' },
          ].map((l) => (
            <Link
              key={l.to}
              to={l.to}
              className="group bg-white border border-slate-200 rounded-xl p-4 hover:border-teal-200 hover:shadow-sm transition-all"
            >
              <l.icon className="w-5 h-5 text-teal-500 mb-2 group-hover:scale-110 transition-transform" />
              <p className="font-semibold text-slate-800 text-sm">{l.label}</p>
              <p className="text-slate-400 text-xs mt-0.5">{l.desc}</p>
            </Link>
          ))}
        </div>
      </div>

      {/* ── QR Modal ───────────────────────────────────────────────────── */}
      {qrOpen && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center p-4"
          onClick={(e) => { if (e.target === e.currentTarget) setQrOpen(false); }}
        >
          <div className="absolute inset-0 bg-black/60 backdrop-blur-sm" />
          <div className="relative bg-white rounded-2xl shadow-2xl w-full max-w-sm overflow-hidden">
            <div className="flex items-center justify-between px-5 pt-5 pb-4 border-b border-slate-100">
              <div>
                <h2 className="font-bold text-slate-900">Clinic QR Code</h2>
                <p className="text-xs text-slate-400 mt-0.5">Patients scan to book instantly</p>
              </div>
              <button
                onClick={() => setQrOpen(false)}
                className="w-8 h-8 flex items-center justify-center rounded-full hover:bg-slate-100 text-slate-400 hover:text-slate-600 transition-colors"
              >
                <X className="w-4 h-4" />
              </button>
            </div>

            <div className="flex flex-col items-center px-6 py-6">
              {qrLoading ? (
                <div className="w-56 h-56 flex items-center justify-center">
                  <RefreshCw className="w-8 h-8 text-teal-400 animate-spin" />
                </div>
              ) : qrSrc ? (
                <div className="p-3 bg-white rounded-2xl shadow-md border border-slate-100">
                  <img src={qrSrc} alt="Clinic QR" className="w-52 h-52 object-contain" />
                </div>
              ) : (
                <div className="w-52 h-52 flex flex-col items-center justify-center rounded-2xl bg-slate-50 border-2 border-dashed border-slate-200 text-slate-400 text-xs text-center gap-2">
                  <QrCode className="w-8 h-8 text-slate-300" />
                  Go to Settings → QR Code to generate one.
                </div>
              )}
              {qrInfo?.portal_url && (
                <p className="mt-4 text-xs text-slate-400 text-center break-all px-2">{qrInfo.portal_url}</p>
              )}
            </div>

            <div className="px-5 pb-5 flex flex-col gap-2">
              {qrSrc && (
                <a
                  href={qrSrc}
                  download={`${qrInfo?.slug ?? 'clinic'}-qr.png`}
                  className="flex items-center justify-center gap-2 w-full bg-teal-600 hover:bg-teal-700 text-white font-semibold py-2.5 rounded-xl text-sm transition-colors"
                >
                  <Download className="w-4 h-4" /> Download PNG
                </a>
              )}
              <button
                onClick={() => { setQrOpen(false); window.location.href = '/settings/qr-code'; }}
                className="w-full border border-slate-200 text-slate-600 hover:bg-slate-50 font-medium py-2.5 rounded-xl text-sm transition-colors"
              >
                Manage QR Code
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}

function getGreeting() {
  const h = new Date().getHours();
  if (h < 12) return 'morning';
  if (h < 17) return 'afternoon';
  return 'evening';
}
