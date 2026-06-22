/**
 * Vitar — Superadmin Dashboard: Overview
 * Platform command centre. Real numbers, real actions, no filler.
 */
import { useQuery } from '@tanstack/react-query';
import { Link } from 'react-router-dom';
import {
  Users, Building2, CreditCard, ScrollText,
  TrendingUp, TrendingDown, AlertCircle, Activity,
  ArrowRight, RefreshCw, Clock,
} from 'lucide-react';
import {
  AreaChart, Area, XAxis, YAxis, CartesianGrid,
  Tooltip, ResponsiveContainer, BarChart, Bar,
} from 'recharts';
import { adminApi } from '@/lib/api/services';
import { useGeoStore } from '@/stores/geoStore';
import { useAdminTheme, EmptyState } from '@/components/admin/AdminUI';
import { format } from 'date-fns';

function timeAgo(iso: string | null): string {
  if (!iso) return '';
  const diffMs = Date.now() - new Date(iso).getTime();
  const mins = Math.floor(diffMs / 60000);
  if (mins < 1)  return 'just now';
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24)  return `${hrs}h ago`;
  return `${Math.floor(hrs / 24)}d ago`;
}

function actionLabel(action: string): string {
  return action.replace(/[._]/g, ' ');
}

function StatPill({ up, value, suffix = '' }: { up: boolean; value: number; suffix?: string }) {
  return (
    <span className={`inline-flex items-center gap-0.5 text-xs font-semibold px-1.5 py-0.5 rounded-full
      ${up ? 'bg-green-100 text-green-700' : 'bg-red-100 text-red-600'}`}>
      {up ? <TrendingUp className="w-3 h-3" /> : <TrendingDown className="w-3 h-3" />}
      {Math.abs(value)}{suffix}
    </span>
  );
}

export default function AdminOverviewPage() {
  const { c, dark } = useAdminTheme();
  const { formatMoney } = useGeoStore();

  const { data, isLoading, refetch, isFetching } = useQuery({
    queryKey: ['admin', 'overview'],
    queryFn: adminApi.analytics.overview,
    refetchInterval: 60_000,
  });

  const kpis         = data?.kpis;
  const userGrowth   = data?.user_growth   ?? [];
  const clinicGrowth = data?.clinic_growth ?? [];
  const feed         = data?.activity_feed ?? [];

  const gridColor  = dark ? '#1e293b' : '#f1f5f9';
  const axisColor  = dark ? '#475569' : '#94a3b8';
  const tooltipBg  = dark ? '#1e293b' : '#ffffff';
  const tooltipBdr = dark ? '#334155' : '#e2e8f0';

  const customTooltip = {
    contentStyle: { background: tooltipBg, border: `1px solid ${tooltipBdr}`, borderRadius: 8, fontSize: 12 },
  };

  return (
    <div className={`min-h-screen ${c.page}`}>
      <div className="p-4 sm:p-6 space-y-5 max-w-7xl mx-auto">

        {/* ── Header ────────────────────────────────────────────────── */}
        <div className="flex items-start justify-between gap-3">
          <div>
            <p className="text-xs font-semibold uppercase tracking-widest text-teal-500 mb-0.5">
              {format(new Date(), 'EEEE, MMMM d, yyyy')}
            </p>
            <h1 className={`text-2xl sm:text-3xl font-bold leading-tight ${c.text}`}>
              Platform Overview
            </h1>
            <p className={`text-sm mt-0.5 ${c.textMuted}`}>Real-time health across all clinics</p>
          </div>
          <button
            onClick={() => refetch()}
            disabled={isFetching}
            className={`flex items-center gap-1.5 px-3 py-2 rounded-lg border text-sm font-medium transition-colors mt-1 ${c.border} ${c.text} ${c.panelHover}`}
          >
            <RefreshCw className={`w-3.5 h-3.5 ${isFetching ? 'animate-spin text-teal-500' : ''}`} />
            <span className="hidden sm:inline">Refresh</span>
          </button>
        </div>

        {/* ── KPI Cards ─────────────────────────────────────────────── */}
        <div className="grid grid-cols-2 xl:grid-cols-4 gap-3 sm:gap-4">
          {[
            {
              label: 'Total Users',
              value: isLoading ? null : kpis?.total_users.toLocaleString(),
              sub: 'All time',
              icon: Users,
              tint: { bg: dark ? 'bg-blue-500/10' : 'bg-blue-50', text: dark ? 'text-blue-400' : 'text-blue-600', ring: dark ? 'ring-blue-500/20' : 'ring-blue-100' },
              link: '/admin/users',
            },
            {
              label: 'Total Clinics',
              value: isLoading ? null : kpis?.total_clinics.toLocaleString(),
              sub: 'Registered',
              icon: Building2,
              tint: { bg: dark ? 'bg-teal-500/10' : 'bg-teal-50', text: dark ? 'text-teal-400' : 'text-teal-600', ring: dark ? 'ring-teal-500/20' : 'ring-teal-100' },
              link: '/admin/clinics',
            },
            {
              label: 'Active Subscriptions',
              value: isLoading ? null : kpis?.active_subscriptions.toLocaleString(),
              sub: kpis && kpis.total_clinics > 0
                ? `${Math.round((kpis.active_subscriptions / kpis.total_clinics) * 100)}% conversion`
                : 'Paying customers',
              icon: CreditCard,
              tint: { bg: dark ? 'bg-green-500/10' : 'bg-green-50', text: dark ? 'text-green-400' : 'text-green-600', ring: dark ? 'ring-green-500/20' : 'ring-green-100' },
              link: '/admin/subscriptions',
            },
            {
              label: 'Monthly Revenue',
              value: isLoading ? null : formatMoney(kpis?.monthly_revenue ?? 0),
              sub: 'This month',
              icon: null,
              tint: { bg: dark ? 'bg-amber-500/10' : 'bg-amber-50', text: dark ? 'text-amber-400' : 'text-amber-600', ring: dark ? 'ring-amber-500/20' : 'ring-amber-100' },
              link: '/admin/subscriptions',
            },
          ].map((k) => (
            <Link
              key={k.label}
              to={k.link}
              className={`group rounded-xl border p-4 sm:p-5 hover:shadow-md transition-all ${c.panel}`}
            >
              <div className="flex items-start justify-between mb-3">
                <div className={`w-9 h-9 rounded-lg flex items-center justify-center ${k.tint.bg} ring-4 ${k.tint.ring}`}>
                  {k.icon
                    ? <k.icon className={`w-4 h-4 ${k.tint.text}`} />
                    : <span className={`text-base font-bold ${k.tint.text}`}>₦</span>
                  }
                </div>
                <ArrowRight className={`w-3.5 h-3.5 ${c.textFaint} group-hover:text-teal-500 group-hover:translate-x-0.5 transition-all mt-1`} />
              </div>
              <p className={`text-xs font-medium truncate ${c.textMuted}`}>{k.label}</p>
              <p className={`text-2xl font-bold mt-0.5 leading-none ${c.text}`}>
                {k.value === null
                  ? <span className={`inline-block w-14 h-6 rounded animate-pulse ${dark ? 'bg-slate-800' : 'bg-slate-100'}`} />
                  : k.value
                }
              </p>
              <p className={`text-xs mt-1 ${c.textFaint}`}>{k.sub}</p>
            </Link>
          ))}
        </div>

        {/* ── Growth Charts ──────────────────────────────────────────── */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
          <div className={`rounded-xl border p-5 ${c.panel}`}>
            <div className="flex items-center justify-between mb-4">
              <div>
                <h2 className={`font-bold text-sm ${c.text}`}>User Growth</h2>
                <p className={`text-xs ${c.textFaint}`}>Last 6 months</p>
              </div>
              <TrendingUp className="w-4 h-4 text-teal-500" />
            </div>
            {userGrowth.length > 0 ? (
              <ResponsiveContainer width="100%" height={200}>
                <AreaChart data={userGrowth} margin={{ top: 0, right: 0, left: -20, bottom: 0 }}>
                  <defs>
                    <linearGradient id="userGrad" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="0%" stopColor="#0d9488" stopOpacity={0.3} />
                      <stop offset="100%" stopColor="#0d9488" stopOpacity={0} />
                    </linearGradient>
                  </defs>
                  <CartesianGrid strokeDasharray="3 3" stroke={gridColor} />
                  <XAxis dataKey="month" tick={{ fontSize: 11, fill: axisColor }} axisLine={false} tickLine={false} />
                  <YAxis tick={{ fontSize: 11, fill: axisColor }} axisLine={false} tickLine={false} allowDecimals={false} />
                  <Tooltip {...customTooltip} />
                  <Area type="monotone" dataKey="count" name="Users" stroke="#0d9488" fill="url(#userGrad)" strokeWidth={2.5} dot={false} />
                </AreaChart>
              </ResponsiveContainer>
            ) : <EmptyState message="No user data yet" />}
          </div>

          <div className={`rounded-xl border p-5 ${c.panel}`}>
            <div className="flex items-center justify-between mb-4">
              <div>
                <h2 className={`font-bold text-sm ${c.text}`}>Clinic Onboarding</h2>
                <p className={`text-xs ${c.textFaint}`}>Last 6 months</p>
              </div>
              <Building2 className="w-4 h-4 text-purple-500" />
            </div>
            {clinicGrowth.length > 0 ? (
              <ResponsiveContainer width="100%" height={200}>
                <BarChart data={clinicGrowth} margin={{ top: 0, right: 0, left: -20, bottom: 0 }}>
                  <defs>
                    <linearGradient id="clinicGrad" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="0%" stopColor="#7c3aed" stopOpacity={0.9} />
                      <stop offset="100%" stopColor="#7c3aed" stopOpacity={0.5} />
                    </linearGradient>
                  </defs>
                  <CartesianGrid strokeDasharray="3 3" stroke={gridColor} vertical={false} />
                  <XAxis dataKey="month" tick={{ fontSize: 11, fill: axisColor }} axisLine={false} tickLine={false} />
                  <YAxis tick={{ fontSize: 11, fill: axisColor }} axisLine={false} tickLine={false} allowDecimals={false} />
                  <Tooltip {...customTooltip} />
                  <Bar dataKey="count" name="Clinics" fill="url(#clinicGrad)" radius={[4, 4, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            ) : <EmptyState message="No clinic data yet" />}
          </div>
        </div>

        {/* ── Quick Nav + Activity ───────────────────────────────────── */}
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
          {/* Quick nav */}
          <div className={`rounded-xl border p-5 ${c.panel} space-y-2`}>
            <h2 className={`font-bold text-sm mb-3 ${c.text}`}>Quick Actions</h2>
            {[
              { to: '/admin/users',         label: 'Manage Users',         icon: Users,       sub: 'Accounts & roles'   },
              { to: '/admin/clinics',        label: 'Manage Clinics',       icon: Building2,   sub: 'Status & details'   },
              { to: '/admin/subscriptions',  label: 'Subscriptions',        icon: CreditCard,  sub: 'Plans & billing'    },
              { to: '/admin/audit-log',      label: 'Audit Log',            icon: ScrollText,  sub: 'Activity history'   },
            ].map((l) => (
              <Link
                key={l.to}
                to={l.to}
                className={`flex items-center gap-3 p-3 rounded-lg transition-colors ${c.panelHover} group`}
              >
                <div className={`w-8 h-8 rounded-lg flex items-center justify-center flex-shrink-0 ${dark ? 'bg-slate-800' : 'bg-slate-100'}`}>
                  <l.icon className={`w-4 h-4 ${c.textMuted}`} />
                </div>
                <div className="flex-1 min-w-0">
                  <p className={`text-sm font-semibold truncate ${c.text}`}>{l.label}</p>
                  <p className={`text-xs truncate ${c.textFaint}`}>{l.sub}</p>
                </div>
                <ArrowRight className={`w-3.5 h-3.5 ${c.textFaint} group-hover:text-teal-500 transition-colors flex-shrink-0`} />
              </Link>
            ))}
          </div>

          {/* Activity feed */}
          <div className={`lg:col-span-2 rounded-xl border overflow-hidden ${c.panel}`}>
            <div className={`flex items-center justify-between px-5 py-4 border-b ${c.border}`}>
              <div className="flex items-center gap-2">
                <Activity className="w-4 h-4 text-teal-500" />
                <h2 className={`font-bold text-sm ${c.text}`}>Recent Activity</h2>
              </div>
              <Link to="/admin/audit-log" className="text-teal-500 hover:text-teal-400 text-xs font-semibold flex items-center gap-1">
                Full log <ArrowRight className="w-3 h-3" />
              </Link>
            </div>
            {isLoading ? (
              <div className="divide-y divide-slate-100/10">
                {[1,2,3,4,5].map(i => (
                  <div key={i} className="flex items-center gap-3 px-5 py-3.5 animate-pulse">
                    <div className={`w-8 h-8 rounded-full flex-shrink-0 ${dark ? 'bg-slate-800' : 'bg-slate-100'}`} />
                    <div className="flex-1 space-y-1.5">
                      <div className={`h-3 rounded w-40 ${dark ? 'bg-slate-800' : 'bg-slate-100'}`} />
                      <div className={`h-2.5 rounded w-24 ${dark ? 'bg-slate-800' : 'bg-slate-100'}`} />
                    </div>
                  </div>
                ))}
              </div>
            ) : feed.length === 0 ? (
              <EmptyState message="No activity recorded yet" />
            ) : (
              <div className={`divide-y ${c.divide}`}>
                {feed.slice(0, 8).map((entry: any) => (
                  <div key={entry.id} className={`flex items-center gap-3 px-5 py-3 ${c.panelHover} transition-colors`}>
                    <div className={`w-8 h-8 rounded-full flex items-center justify-center flex-shrink-0 text-xs font-bold ${
                      dark ? 'bg-teal-500/10 text-teal-400' : 'bg-teal-50 text-teal-600'
                    }`}>
                      {entry.actor_name?.charAt(0)?.toUpperCase() ?? '?'}
                    </div>
                    <div className="flex-1 min-w-0">
                      <p className={`text-sm capitalize truncate font-medium ${c.text}`}>
                        {actionLabel(entry.action)}
                      </p>
                      <p className={`text-xs truncate ${c.textFaint}`}>{entry.actor_name}</p>
                    </div>
                    <div className="flex items-center gap-1 flex-shrink-0">
                      <Clock className={`w-3 h-3 ${c.textFaint}`} />
                      <span className={`text-xs ${c.textFaint}`}>{timeAgo(entry.created_at)}</span>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
