/**
 * Vitar v5 - Analytics Page
 */
import { useQuery } from '@tanstack/react-query';
import { analyticsApi } from '@/lib/api/services';
import { BarChart3, TrendingDown, TrendingUp, Users, Bell } from 'lucide-react';

export default function AnalyticsPage() {
  const { data, isLoading } = useQuery({ queryKey: ['analytics', 'dashboard'], queryFn: analyticsApi.dashboard });
  const { data: trendData } = useQuery({ queryKey: ['analytics', 'no-show-trends'], queryFn: () => analyticsApi.noShowTrends(30) });

  if (isLoading) return <div className="p-6 text-slate-400">Loading analytics...</div>;

  const appts = data?.appointments ?? {};
  const momChange = appts.mom_change_pct ?? 0;
  const trend = trendData?.trend ?? [];

  return (
    <div className="p-6 space-y-6 max-w-7xl mx-auto">
      <h1 className="text-2xl font-bold text-slate-900">Analytics</h1>

      {/* KPI cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-4 gap-4">
        {[
          { label: 'No-Show Rate (This Month)', value: `${appts.no_show_rate_pct ?? 0}%`,
            sub: `${appts.no_show ?? 0} of ${(appts.completed ?? 0) + (appts.no_show ?? 0)} tracked visits`,
            icon: TrendingDown, color: 'bg-red-50 text-red-600' },
          { label: 'Bookings vs Last Month', value: `${momChange > 0 ? '+' : ''}${momChange}%`,
            sub: momChange >= 0 ? '↑ Growing' : '↓ Slower than last month',
            icon: TrendingUp, color: 'bg-green-50 text-green-600' },
          { label: 'Total Patients', value: data?.patients?.total ?? 0,
            sub: 'All-time, this clinic',
            icon: Users, color: 'bg-blue-50 text-blue-600' },
          { label: 'Reminder Delivery Rate', value: `${data?.notifications?.delivery_rate_pct ?? 0}%`,
            sub: `${data?.notifications?.sent ?? 0} of ${data?.notifications?.total ?? 0} sent this month`,
            icon: Bell, color: 'bg-teal-50 text-teal-600' },
        ].map(({ label, value, sub, icon: Icon, color }) => (
          <div key={label} className="bg-white rounded-xl border border-slate-200 p-5">
            <div className="flex items-start justify-between">
              <div>
                <p className="text-slate-500 text-sm">{label}</p>
                <p className="text-2xl font-bold text-slate-900 mt-1">{value}</p>
                <p className="text-slate-400 text-xs mt-1">{sub}</p>
              </div>
              <div className={`w-10 h-10 rounded-xl flex items-center justify-center ${color}`}>
                <Icon className="w-5 h-5" />
              </div>
            </div>
          </div>
        ))}
      </div>

      {/* No-show trend, last 30 days */}
      {trend.length > 0 && (
        <div className="bg-white rounded-xl border border-slate-200 p-6">
          <h2 className="font-semibold text-slate-900 mb-4 flex items-center gap-2">
            <BarChart3 className="w-4 h-4 text-teal-600" /> No-Show Rate — Last 30 Days
          </h2>
          <div className="flex items-end gap-1 h-40">
            {trend.map((d: any) => (
              <div key={d.date} className="flex-1 flex flex-col items-center justify-end gap-1" title={`${d.date}: ${d.rate_pct}% (${d.no_shows}/${d.total})`}>
                <div
                  className="w-full bg-teal-500 rounded-t"
                  style={{ height: `${Math.max(d.rate_pct, d.total > 0 ? 2 : 0)}%` }}
                />
              </div>
            ))}
          </div>
          <p className="text-slate-400 text-xs mt-2 text-center">Hover a bar for the exact date and rate</p>
        </div>
      )}

      {/* Appointment status breakdown */}
      <div className="bg-white rounded-xl border border-slate-200 p-6">
        <h2 className="font-semibold text-slate-900 mb-4">This Month — Appointment Breakdown</h2>
        <div className="grid grid-cols-4 gap-4">
          {[
            { label: 'Total', value: appts.total_this_month ?? 0, color: 'bg-slate-100 text-slate-700' },
            { label: 'Completed', value: appts.completed ?? 0, color: 'bg-green-100 text-green-700' },
            { label: 'No Shows', value: appts.no_show ?? 0, color: 'bg-orange-100 text-orange-700' },
            { label: 'Cancelled', value: appts.cancelled ?? 0, color: 'bg-red-100 text-red-700' },
          ].map(s => (
            <div key={s.label} className={`rounded-xl p-4 text-center ${s.color}`}>
              <p className="text-3xl font-bold">{s.value}</p>
              <p className="text-xs font-medium mt-1">{s.label}</p>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
