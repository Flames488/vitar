/**
 * Vitar v5 - AI Risk Page
 * No-show prediction dashboard, risk distribution, smart action list
 */

import { useQuery, useMutation } from '@tanstack/react-query';
import { Brain, AlertTriangle, TrendingDown, Users, RefreshCw, Phone, MessageSquare } from 'lucide-react';
import { aiApi } from '@/lib/api/services';
import { format } from 'date-fns';
import { toast } from 'sonner';

const RISK_CONFIG = {
  low:      { color: 'bg-green-100 text-green-700  border-green-200',  bar: 'bg-green-500',  label: 'Low' },
  medium:   { color: 'bg-yellow-100 text-yellow-700 border-yellow-200', bar: 'bg-yellow-500', label: 'Medium' },
  high:     { color: 'bg-orange-100 text-orange-700 border-orange-200', bar: 'bg-orange-500', label: 'High' },
  critical: { color: 'bg-red-100 text-red-700 border-red-200',          bar: 'bg-red-500',    label: 'Critical' },
};

export default function AIRiskPage() {
  const { data, isLoading, refetch } = useQuery({
    queryKey: ['ai', 'risk-dashboard'],
    queryFn: aiApi.riskDashboard,
    refetchInterval: 300_000, // 5 min
  });

  const { data: trends } = useQuery({
    queryKey: ['ai', 'no-show-trends'],
    queryFn: () => aiApi.noShowTrends(6),
  });

  const predictMutation = useMutation({
    mutationFn: (id: string) => aiApi.predict(id),
    onSuccess: (result) => {
      toast.success(`Risk updated: ${result.risk_category} (${Math.round(result.risk_score * 100)}%)`);
      refetch();
    },
    onError: () => toast.error('Failed to update risk score'),
  });

  const distribution = data?.risk_distribution ?? { low: 0, medium: 0, high: 0, critical: 0 };
  const total = Object.values(distribution).reduce((a, b) => (a as number) + (b as number), 0) as number;
  const highRisk = data?.high_risk_appointments ?? [];
  const stats = data?.clinic_stats ?? {};

  return (
    <div className="p-6 space-y-6 max-w-7xl mx-auto">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-slate-900 flex items-center gap-2">
            <Brain className="w-6 h-6 text-teal-600" />
            AI No-Show Risk Dashboard
          </h1>
          <p className="text-slate-500 text-sm mt-1">
            Powered by Vitar AI — targeting 40–70% reduction in no-shows
          </p>
        </div>
        <button
          onClick={() => refetch()}
          className="flex items-center gap-2 border border-slate-200 bg-white hover:bg-slate-50 px-4 py-2 rounded-lg text-sm text-slate-600 transition-colors"
        >
          <RefreshCw className="w-4 h-4" />
          Refresh
        </button>
      </div>

      {/* KPI row */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        <div className="bg-white rounded-xl border border-slate-200 p-5">
          <p className="text-slate-500 text-sm">Overall No-Show Rate</p>
          <p className="text-3xl font-bold text-slate-900 mt-1">{stats.no_show_rate_percent ?? 0}%</p>
          <p className="text-xs text-slate-400 mt-1">All time</p>
        </div>
        <div className="bg-teal-50 rounded-xl border border-teal-200 p-5">
          <p className="text-teal-700 text-sm font-medium">Est. Reduction with Vitar</p>
          <p className="text-3xl font-bold text-teal-800 mt-1">
            {Math.max(0, (stats.no_show_rate_percent ?? 0) * 0.5).toFixed(1)}%
          </p>
          <p className="text-xs text-teal-600 mt-1">~50% improvement target</p>
        </div>
        <div className="bg-white rounded-xl border border-slate-200 p-5">
          <p className="text-slate-500 text-sm">Upcoming Appointments</p>
          <p className="text-3xl font-bold text-slate-900 mt-1">{data?.upcoming_total ?? 0}</p>
          <p className="text-xs text-slate-400 mt-1">{highRisk.length} flagged high risk</p>
        </div>
      </div>

      {/* Risk distribution */}
      <div className="bg-white rounded-xl border border-slate-200 p-6">
        <h2 className="font-semibold text-slate-900 mb-4">Risk Distribution — Upcoming Appointments</h2>
        <div className="space-y-3">
          {(Object.keys(RISK_CONFIG) as Array<keyof typeof RISK_CONFIG>).map((cat) => {
            const count = distribution[cat] ?? 0;
            const pct = total > 0 ? Math.round(count / total * 100) : 0;
            const cfg = RISK_CONFIG[cat];
            return (
              <div key={cat} className="flex items-center gap-3">
                <span className={`w-20 text-xs font-medium px-2 py-0.5 rounded-full border ${cfg.color}`}>
                  {cfg.label}
                </span>
                <div className="flex-1 bg-slate-100 rounded-full h-2">
                  <div
                    className={`h-2 rounded-full ${cfg.bar} transition-all`}
                    style={{ width: `${pct}%` }}
                  />
                </div>
                <span className="text-sm text-slate-600 w-16 text-right">{count} ({pct}%)</span>
              </div>
            );
          })}
        </div>
      </div>

      {/* High risk list */}
      <div className="bg-white rounded-xl border border-slate-200">
        <div className="px-6 py-4 border-b border-slate-100 flex items-center gap-2">
          <AlertTriangle className="w-4 h-4 text-orange-500" />
          <h2 className="font-semibold text-slate-900">High Risk Patients — Action Required</h2>
          <span className="ml-auto bg-orange-100 text-orange-700 text-xs font-medium px-2 py-0.5 rounded-full">
            {highRisk.length} patients
          </span>
        </div>

        {isLoading ? (
          <div className="px-6 py-10 text-center text-slate-400 text-sm">Loading risk data...</div>
        ) : highRisk.length === 0 ? (
          <div className="px-6 py-10 text-center">
            <TrendingDown className="w-10 h-10 text-green-300 mx-auto mb-2" />
            <p className="text-slate-500 text-sm">No high-risk appointments — great work!</p>
          </div>
        ) : (
          <div className="divide-y divide-slate-100">
            {highRisk.map((apt: any) => {
              const cfg = RISK_CONFIG[apt.risk_category as keyof typeof RISK_CONFIG] ?? RISK_CONFIG.high;
              const topFactors = Object.entries(apt.risk_factors ?? {})
                .filter(([k]) => k.endsWith('_score') && !k.startsWith('final'))
                .sort(([, a], [, b]) => (b as number) - (a as number))
                .slice(0, 2)
                .map(([k]) => k.replace('_score', '').replace(/_/g, ' '));

              return (
                <div key={apt.id} className="px-6 py-4 flex items-start justify-between gap-4">
                  <div className="flex items-start gap-3 flex-1 min-w-0">
                    <div className="w-10 h-10 rounded-full bg-slate-100 flex items-center justify-center font-bold text-slate-600 flex-shrink-0">
                      {apt.patient.name.charAt(0)}
                    </div>
                    <div className="min-w-0">
                      <div className="flex items-center gap-2">
                        <p className="font-medium text-slate-900">{apt.patient.name}</p>
                        <span className={`text-xs px-2 py-0.5 rounded-full border font-medium ${cfg.color}`}>
                          {Math.round(apt.risk_score * 100)}% {cfg.label}
                        </span>
                      </div>
                      <p className="text-slate-500 text-sm mt-0.5">
                        {format(new Date(apt.scheduled_at), 'EEE MMM d, h:mm a')}
                      </p>
                      <p className="text-slate-400 text-xs mt-1">
                        Reminders sent: {apt.reminder_count} ·
                        Historical no-show rate: {Math.round((apt.patient.historical_no_show_rate ?? 0) * 100)}%
                      </p>
                      {topFactors.length > 0 && (
                        <p className="text-xs text-orange-600 mt-1">
                          Risk factors: {topFactors.join(', ')}
                        </p>
                      )}
                      <p className="text-xs text-blue-600 mt-1 font-medium">
                        → {apt.recommended_action ?? 'Send reminder now'}
                      </p>
                    </div>
                  </div>
                  <div className="flex items-center gap-2 flex-shrink-0">
                    <a
                      href={`tel:${apt.patient.phone}`}
                      className="flex items-center gap-1.5 border border-slate-200 hover:bg-slate-50 px-3 py-1.5 rounded-lg text-xs text-slate-600 transition-colors"
                      title="Call patient"
                    >
                      <Phone className="w-3.5 h-3.5" />
                      Call
                    </a>
                    <button
                      onClick={() => predictMutation.mutate(apt.id)}
                      disabled={predictMutation.isPending}
                      className="flex items-center gap-1.5 bg-teal-50 hover:bg-teal-100 border border-teal-200 px-3 py-1.5 rounded-lg text-xs text-teal-700 font-medium transition-colors"
                    >
                      <RefreshCw className={`w-3.5 h-3.5 ${predictMutation.isPending ? 'animate-spin' : ''}`} />
                      Re-score
                    </button>
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>

      {/* No-show trend */}
      {trends?.trends && (
        <div className="bg-white rounded-xl border border-slate-200 p-6">
          <h2 className="font-semibold text-slate-900 mb-4">No-Show Rate Trend (6 months)</h2>
          <div className="flex items-end gap-2 h-24">
            {trends.trends.map((t: any) => {
              const height = Math.max(t.rate, 2);
              return (
                <div key={t.month} className="flex-1 flex flex-col items-center gap-1">
                  <span className="text-xs text-slate-500">{t.rate}%</span>
                  <div
                    className="w-full bg-teal-500 rounded-t"
                    style={{ height: `${(height / 50) * 80}px` }}
                    title={`${t.month}: ${t.no_shows}/${t.total} no-shows`}
                  />
                  <span className="text-xs text-slate-400 truncate w-full text-center">{t.month.slice(5)}</span>
                </div>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}
