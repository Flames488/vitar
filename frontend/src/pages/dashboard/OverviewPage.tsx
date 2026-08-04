/**
 * Vitar - Overview / Dashboard Page
 *
 * /dashboard used to just redirect straight to /appointments — the sidebar's
 * "Overview" > "Dashboard" link and "Appointments" link both landed on the
 * same page, which read as broken. This gives Dashboard its own real content:
 * a quick snapshot (today/this week/patients/no-show rate), this month's
 * appointment breakdown, and quick links into the pages someone lands here
 * to get to. Reuses the existing GET /analytics/dashboard and
 * GET /analytics/quick-summary endpoints — no new backend work.
 */
import { Link } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { analyticsApi } from '@/lib/api/services';
import { useAuthStore } from '@/stores/authStore';
import {
  Calendar, CalendarDays, Users, TrendingDown, TrendingUp, AlertTriangle,
  CalendarPlus, UserPlus, BarChart3,
} from 'lucide-react';

export default function OverviewPage() {
  const { clinic } = useAuthStore();
  const { data: dashboard, isLoading: dashboardLoading } = useQuery({
    queryKey: ['analytics', 'dashboard'],
    queryFn: analyticsApi.dashboard,
  });
  const { data: summary, isLoading: summaryLoading } = useQuery({
    queryKey: ['analytics', 'summary'],
    queryFn: analyticsApi.summary,
  });

  const appts = dashboard?.appointments ?? {};
  const momChange = appts.mom_change_pct ?? 0;

  if (dashboardLoading || summaryLoading) {
    return <div className="p-6 text-slate-400">Loading overview...</div>;
  }

  return (
    <div className="p-6 space-y-6 max-w-7xl mx-auto">
      <div>
        <h1 className="text-2xl font-bold text-slate-900">Overview</h1>
        {clinic?.name && <p className="text-slate-500 text-sm mt-0.5">Welcome back, {clinic.name}</p>}
      </div>

      {/* Snapshot cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-4 gap-4">
        <StatCard
          icon={Calendar} color="bg-teal-50 text-teal-600"
          label="Today's Appointments" value={summary?.today_appointments ?? 0}
        />
        <StatCard
          icon={CalendarDays} color="bg-blue-50 text-blue-600"
          label="This Week" value={summary?.week_appointments ?? 0}
        />
        <StatCard
          icon={Users} color="bg-slate-100 text-slate-700"
          label="Total Patients" value={dashboard?.patients?.total ?? 0}
        />
        <StatCard
          icon={appts.no_show_rate_pct > 0 ? TrendingDown : TrendingUp}
          color="bg-orange-50 text-orange-600"
          label="No-Show Rate (This Month)" value={`${appts.no_show_rate_pct ?? 0}%`}
        />
      </div>

      {summary?.high_risk_this_week > 0 && (
        <div className="flex items-center gap-3 bg-amber-50 border border-amber-200 rounded-xl p-4">
          <AlertTriangle className="w-5 h-5 text-amber-600 flex-shrink-0" />
          <p className="text-sm text-amber-800">
            <strong>{summary.high_risk_this_week}</strong> upcoming appointment{summary.high_risk_this_week === 1 ? '' : 's'} this week
            {' '}flagged as high no-show risk.{' '}
            <Link to="/ai-risk" className="font-semibold underline hover:no-underline">Review AI Risk</Link>
          </p>
        </div>
      )}

      {/* This month's breakdown */}
      <div className="bg-white rounded-xl border border-slate-200 p-6">
        <div className="flex items-center justify-between mb-4">
          <h2 className="font-semibold text-slate-900">This Month</h2>
          {momChange !== 0 && (
            <span className={`text-xs font-medium px-2 py-1 rounded-full ${momChange > 0 ? 'bg-green-50 text-green-700' : 'bg-red-50 text-red-700'}`}>
              {momChange > 0 ? '↑' : '↓'} {Math.abs(momChange)}% vs last month
            </span>
          )}
        </div>
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
          {[
            { label: 'Total Booked', value: appts.total_this_month ?? 0, color: 'bg-slate-100 text-slate-700' },
            { label: 'Completed', value: appts.completed ?? 0, color: 'bg-green-100 text-green-700' },
            { label: 'No Shows', value: appts.no_show ?? 0, color: 'bg-orange-100 text-orange-700' },
            { label: 'Cancelled', value: appts.cancelled ?? 0, color: 'bg-red-100 text-red-700' },
          ].map((s) => (
            <div key={s.label} className={`rounded-xl p-4 text-center ${s.color}`}>
              <p className="text-3xl font-bold">{s.value}</p>
              <p className="text-xs font-medium mt-1">{s.label}</p>
            </div>
          ))}
        </div>
      </div>

      {/* Quick links */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        <QuickLink to="/appointments/new" icon={CalendarPlus} label="New Appointment" />
        <QuickLink to="/patients" icon={UserPlus} label="View Patients" />
        <QuickLink to="/analytics" icon={BarChart3} label="Full Analytics" />
      </div>
    </div>
  );
}

function StatCard({ icon: Icon, color, label, value }: { icon: React.ElementType; color: string; label: string; value: string | number }) {
  return (
    <div className="bg-white rounded-xl border border-slate-200 p-5">
      <div className="flex items-start justify-between">
        <div>
          <p className="text-slate-500 text-sm">{label}</p>
          <p className="text-2xl font-bold text-slate-900 mt-1">{value}</p>
        </div>
        <div className={`w-10 h-10 rounded-xl flex items-center justify-center ${color}`}>
          <Icon className="w-5 h-5" />
        </div>
      </div>
    </div>
  );
}

function QuickLink({ to, icon: Icon, label }: { to: string; icon: React.ElementType; label: string }) {
  return (
    <Link
      to={to}
      className="flex items-center gap-3 bg-white rounded-xl border border-slate-200 p-4 hover:border-teal-300 hover:bg-teal-50/40 transition-colors"
    >
      <div className="w-9 h-9 rounded-lg bg-teal-50 text-teal-600 flex items-center justify-center flex-shrink-0">
        <Icon className="w-4.5 h-4.5" />
      </div>
      <span className="text-sm font-medium text-slate-700">{label}</span>
    </Link>
  );
}
