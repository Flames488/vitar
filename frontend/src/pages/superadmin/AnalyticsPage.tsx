/**
 * Vitar — Admin Dashboard: Analytics
 * Module 6 of the spec: active vs inactive users, subscription trends,
 * user/clinic growth, CSV export.
 */
import { useQuery } from '@tanstack/react-query';
import { Download } from 'lucide-react';
import {
  PieChart, Pie, Cell, BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip,
  ResponsiveContainer, Legend,
} from 'recharts';
import { adminApi } from '@/lib/api/services';
import { useAdminTheme, EmptyState, LoadingState } from '@/components/admin/AdminUI';

const PIE_COLORS = ['#0d9488', '#cbd5e1'];
const PLAN_COLORS: Record<string, string> = {
  trial: '#94a3b8', basic: '#3b82f6', pro: '#7c3aed', enterprise: '#0d9488',
};

export default function AdminAnalyticsPage() {
  const { c, dark } = useAdminTheme();
  const { data, isLoading } = useQuery({
    queryKey: ['admin', 'analytics', 'business'],
    queryFn: adminApi.analytics.business,
  });

  const handleExport = () => {
    window.open(adminApi.analytics.exportCsvUrl(), '_blank');
  };

  if (isLoading || !data) return <div className="p-6"><LoadingState message="Loading analytics..." /></div>;

  const activeVsInactive = [
    { name: 'Active', value: data.active_vs_inactive_users.active },
    { name: 'Inactive', value: data.active_vs_inactive_users.inactive },
  ];

  return (
    <div className="p-6 space-y-6 max-w-7xl mx-auto">
      <div className="flex items-center justify-between">
        <div>
          <h1 className={`text-2xl font-bold ${c.text}`}>Analytics</h1>
          <p className={`text-sm mt-1 ${c.textMuted}`}>Business-level reporting for the platform.</p>
        </div>
        <button
          onClick={handleExport}
          className="inline-flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium bg-teal-600 hover:bg-teal-700 text-white"
        >
          <Download className="w-4 h-4" /> Export CSV
        </button>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        {/* Active vs inactive */}
        <div className={`rounded-xl border p-6 ${c.panel}`}>
          <h2 className={`font-semibold mb-4 ${c.text}`}>Active vs Inactive Users</h2>
          <ResponsiveContainer width="100%" height={220}>
            <PieChart>
              <Pie data={activeVsInactive} dataKey="value" nameKey="name" cx="50%" cy="50%" outerRadius={80} label>
                {activeVsInactive.map((_, i) => <Cell key={i} fill={PIE_COLORS[i]} />)}
              </Pie>
              <Tooltip />
              <Legend />
            </PieChart>
          </ResponsiveContainer>
        </div>

        {/* Subscription plan breakdown */}
        <div className={`rounded-xl border p-6 ${c.panel}`}>
          <h2 className={`font-semibold mb-4 ${c.text}`}>Subscription Plan Breakdown</h2>
          {data.subscription_plan_breakdown.length > 0 ? (
            <ResponsiveContainer width="100%" height={220}>
              <BarChart data={data.subscription_plan_breakdown}>
                <CartesianGrid strokeDasharray="3 3" stroke={dark ? '#1e293b' : '#f1f5f9'} />
                <XAxis dataKey="plan" tick={{ fontSize: 12 }} className="capitalize" stroke={dark ? '#64748b' : '#94a3b8'} />
                <YAxis tick={{ fontSize: 12 }} allowDecimals={false} stroke={dark ? '#64748b' : '#94a3b8'} />
                <Tooltip />
                <Bar dataKey="count" radius={[6, 6, 0, 0]}>
                  {data.subscription_plan_breakdown.map((row: any, i: number) => (
                    <Cell key={i} fill={PLAN_COLORS[row.plan] ?? '#0d9488'} />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          ) : <EmptyState message="No subscription data yet" />}
        </div>

        {/* User growth */}
        <div className={`rounded-xl border p-6 ${c.panel}`}>
          <h2 className={`font-semibold mb-4 ${c.text}`}>User Growth (12 months)</h2>
          {data.user_growth.length > 0 ? (
            <ResponsiveContainer width="100%" height={220}>
              <BarChart data={data.user_growth}>
                <CartesianGrid strokeDasharray="3 3" stroke={dark ? '#1e293b' : '#f1f5f9'} />
                <XAxis dataKey="month" tick={{ fontSize: 11 }} stroke={dark ? '#64748b' : '#94a3b8'} />
                <YAxis tick={{ fontSize: 12 }} allowDecimals={false} stroke={dark ? '#64748b' : '#94a3b8'} />
                <Tooltip />
                <Bar dataKey="count" fill="#3b82f6" radius={[6, 6, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          ) : <EmptyState message="No data yet" />}
        </div>

        {/* Clinic growth */}
        <div className={`rounded-xl border p-6 ${c.panel}`}>
          <h2 className={`font-semibold mb-4 ${c.text}`}>Clinic Growth (12 months)</h2>
          {data.clinic_growth.length > 0 ? (
            <ResponsiveContainer width="100%" height={220}>
              <BarChart data={data.clinic_growth}>
                <CartesianGrid strokeDasharray="3 3" stroke={dark ? '#1e293b' : '#f1f5f9'} />
                <XAxis dataKey="month" tick={{ fontSize: 11 }} stroke={dark ? '#64748b' : '#94a3b8'} />
                <YAxis tick={{ fontSize: 12 }} allowDecimals={false} stroke={dark ? '#64748b' : '#94a3b8'} />
                <Tooltip />
                <Bar dataKey="count" fill="#0d9488" radius={[6, 6, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          ) : <EmptyState message="No data yet" />}
        </div>
      </div>
    </div>
  );
}
