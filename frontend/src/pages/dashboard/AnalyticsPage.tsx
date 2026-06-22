/**
 * Vitar v5 - Analytics Page
 */
import { useQuery } from '@tanstack/react-query';
import { analyticsApi } from '@/lib/api/services';
import { useGeoStore } from '@/stores/geoStore';
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, LineChart, Line } from 'recharts';
import { TrendingDown, TrendingUp, Users } from 'lucide-react';

export default function AnalyticsPage() {
  const { data, isLoading } = useQuery({ queryKey: ['analytics', 'dashboard'], queryFn: analyticsApi.dashboard });
  const { formatMoney } = useGeoStore();

  if (isLoading) return <div className="p-6 text-slate-400">Loading analytics...</div>;

  const curr = data?.current_month ?? {};
  const prev = data?.previous_month ?? {};
  const reduction = data?.no_show_reduction_percent ?? 0;

  return (
    <div className="p-6 space-y-6 max-w-7xl mx-auto">
      <h1 className="text-2xl font-bold text-slate-900">Analytics</h1>

      {/* KPI cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-4 gap-4">
        {[
          { label: 'No-Show Rate (This Month)', value: `${curr.no_show_rate ?? 0}%`,
            sub: `${prev.no_show_rate ?? 0}% last month`,
            icon: TrendingDown, color: 'bg-red-50 text-red-600',
            trend: reduction > 0 ? 'better' : 'worse' },
          { label: 'No-Show Reduction', value: `${Math.abs(reduction)}%`,
            sub: reduction > 0 ? '↑ Improvement' : '↓ Needs attention',
            icon: TrendingUp, color: 'bg-green-50 text-green-600' },
          { label: 'Revenue Recovered', value: formatMoney(data?.revenue?.recovered_from_reminders ?? 0),
            sub: 'From reminder-influenced bookings',
            icon: null, nairaIcon: true, color: 'bg-teal-50 text-teal-600' },
          { label: 'Conversion Rate', value: `${data?.conversion_rate ?? 0}%`,
            sub: `${curr.total ?? 0} total · ${curr.completed ?? 0} completed`,
            icon: Users, color: 'bg-blue-50 text-blue-600' },
        ].map(({ label, value, sub, icon: Icon, color, nairaIcon }) => (
          <div key={label} className="bg-white rounded-xl border border-slate-200 p-5">
            <div className="flex items-start justify-between">
              <div>
                <p className="text-slate-500 text-sm">{label}</p>
                <p className="text-2xl font-bold text-slate-900 mt-1">{value}</p>
                <p className="text-slate-400 text-xs mt-1">{sub}</p>
              </div>
              <div className={`w-10 h-10 rounded-xl flex items-center justify-center ${color}`}>
                {nairaIcon ? <span className="text-lg font-bold">₦</span> : Icon ? <Icon className="w-5 h-5" /> : null}
              </div>
            </div>
          </div>
        ))}
      </div>

      {/* Weekly no-show trend */}
      {data?.weekly_trend?.length > 0 && (
        <div className="bg-white rounded-xl border border-slate-200 p-6">
          <h2 className="font-semibold text-slate-900 mb-4">Weekly No-Show Trend</h2>
          <ResponsiveContainer width="100%" height={220}>
            <LineChart data={data.weekly_trend}>
              <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" />
              <XAxis dataKey="week" tick={{ fontSize: 12 }} />
              <YAxis tick={{ fontSize: 12 }} unit="%" />
              <Tooltip formatter={(v: any) => [`${v}%`, 'No-Show Rate']} />
              <Line type="monotone" dataKey="rate" stroke="#0d9488" strokeWidth={2} dot={{ r: 3 }} />
            </LineChart>
          </ResponsiveContainer>
        </div>
      )}

      {/* Appointment status breakdown */}
      <div className="bg-white rounded-xl border border-slate-200 p-6">
        <h2 className="font-semibold text-slate-900 mb-4">This Month — Appointment Breakdown</h2>
        <div className="grid grid-cols-4 gap-4">
          {[
            { label: 'Total', value: curr.total ?? 0, color: 'bg-slate-100 text-slate-700' },
            { label: 'Completed', value: curr.completed ?? 0, color: 'bg-green-100 text-green-700' },
            { label: 'No Shows', value: curr.no_shows ?? 0, color: 'bg-orange-100 text-orange-700' },
            { label: 'Cancelled', value: curr.cancelled ?? 0, color: 'bg-red-100 text-red-700' },
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
