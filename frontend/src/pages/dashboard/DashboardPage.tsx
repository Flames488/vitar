/**
 * Vitar v5 - Dashboard Page
 */

import { useQuery } from '@tanstack/react-query';
import { Link } from 'react-router-dom';
import { Calendar, Users, DollarSign, CalendarDays, ArrowRight, Brain, AlertTriangle, Plus, Clock } from 'lucide-react';
import { analyticsApi, appointmentsApi } from '@/lib/api/services';
import { useAuthStore } from '@/stores/authStore';
import { useGeoStore } from '@/stores/geoStore';
import { format } from 'date-fns';

const STATUS_COLORS: Record<string, string> = {
  confirmed: 'bg-blue-100 text-blue-700',
  completed: 'bg-green-100 text-green-700',
  cancelled: 'bg-red-100 text-red-700',
  no_show:   'bg-orange-100 text-orange-700',
  pending:   'bg-yellow-100 text-yellow-700',
};

const RISK_COLORS: Record<string, string> = {
  low:      'text-green-600',
  medium:   'text-yellow-600',
  high:     'text-orange-600',
  critical: 'text-red-600',
};

function getRiskCategory(score: number): string {
  if (score < 0.25) return 'low';
  if (score < 0.5)  return 'medium';
  if (score < 0.75) return 'high';
  return 'critical';
}

export default function DashboardPage() {
  const clinic = useAuthStore((s) => s.clinic);
  const { formatMoney } = useGeoStore();

  const { data: summary, isLoading: summaryLoading } = useQuery({
    queryKey: ['analytics', 'summary'],
    queryFn: analyticsApi.summary,
    refetchInterval: 60_000,
  });

  const { data: todayData } = useQuery({
    queryKey: ['appointments', 'today'],
    queryFn: () => appointmentsApi.list({
      date_from: new Date().toISOString().split('T')[0] + 'T00:00:00',
      date_to:   new Date().toISOString().split('T')[0] + 'T23:59:59',
      limit: 10,
    }),
  });

  const statCards = [
    {
      label: "Today's Appointments",
      value: summary?.today_appointments ?? 0,
      icon: Calendar,
      color: 'bg-blue-50 text-blue-600',
      link: '/appointments',
    },
    {
      label: 'This Week',
      value: summary?.week_appointments ?? 0,
      icon: CalendarDays,
      color: 'bg-teal-50 text-teal-600',
      link: '/appointments',
    },
    {
      label: 'Total Patients',
      value: summary?.total_patients ?? 0,
      icon: Users,
      color: 'bg-purple-50 text-purple-600',
      link: '/patients',
    },
    {
      label: 'This Month Revenue',
      value: formatMoney(summary?.month_revenue ?? 0),
      icon: DollarSign,
      color: 'bg-green-50 text-green-600',
      link: '/earnings',
    },
  ];

  const todayApts = todayData?.items ?? [];
  const highRiskCount = todayApts.filter((a: any) => a.no_show_risk_score >= 0.5).length;

  return (
    <div className="p-6 space-y-6 max-w-7xl mx-auto">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-slate-900">
            Good {getGreeting()}, {clinic?.name}
          </h1>
          <p className="text-slate-500 text-sm mt-1">
            {format(new Date(), 'EEEE, MMMM d, yyyy')}
          </p>
        </div>
        <Link
          to="/appointments/new"
          className="flex items-center gap-2 bg-teal-600 hover:bg-teal-700 text-white px-4 py-2.5 rounded-lg text-sm font-medium transition-colors"
        >
          <Plus className="w-4 h-4" />
          New Appointment
        </Link>
      </div>

      {/* High risk alert */}
      {highRiskCount > 0 && (
        <div className="bg-amber-50 border border-amber-200 rounded-xl p-4 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 bg-amber-100 rounded-full flex items-center justify-center">
              <AlertTriangle className="w-5 h-5 text-amber-600" />
            </div>
            <div>
              <p className="font-semibold text-amber-900">
                {highRiskCount} high-risk appointment{highRiskCount > 1 ? 's' : ''} today
              </p>
              <p className="text-amber-700 text-sm">AI detected patients likely to no-show</p>
            </div>
          </div>
          <Link
            to="/ai-risk"
            className="flex items-center gap-1.5 bg-amber-600 hover:bg-amber-700 text-white px-4 py-2 rounded-lg text-sm font-medium transition-colors"
          >
            <Brain className="w-4 h-4" />
            View AI Risk
          </Link>
        </div>
      )}

      {/* Stat cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-4 gap-4">
        {statCards.map((card) => {
          const Icon = card.icon;
          return (
            <Link
              key={card.label}
              to={card.link}
              className="bg-white rounded-xl border border-slate-200 p-5 hover:shadow-md transition-shadow group"
            >
              <div className="flex items-start justify-between">
                <div>
                  <p className="text-slate-500 text-sm">{card.label}</p>
                  <p className="text-2xl font-bold text-slate-900 mt-1">
                    {summaryLoading ? '—' : card.value}
                  </p>
                </div>
                <div className={`w-10 h-10 rounded-xl flex items-center justify-center ${card.color}`}>
                  <Icon className="w-5 h-5" />
                </div>
              </div>
              <div className="mt-3 flex items-center gap-1 text-teal-600 text-xs font-medium opacity-0 group-hover:opacity-100 transition-opacity">
                View details <ArrowRight className="w-3 h-3" />
              </div>
            </Link>
          );
        })}
      </div>

      {/* Today's appointments */}
      <div className="bg-white rounded-xl border border-slate-200">
        <div className="flex items-center justify-between px-6 py-4 border-b border-slate-100">
          <h2 className="font-semibold text-slate-900">Today's Appointments</h2>
          <Link to="/appointments" className="text-teal-600 text-sm hover:underline flex items-center gap-1">
            View all <ArrowRight className="w-3.5 h-3.5" />
          </Link>
        </div>

        {todayApts.length === 0 ? (
          <div className="px-6 py-12 text-center">
            <Calendar className="w-10 h-10 text-slate-300 mx-auto mb-3" />
            <p className="text-slate-500 text-sm">No appointments today</p>
            <Link to="/appointments/new" className="mt-3 inline-block text-teal-600 text-sm font-medium hover:underline">
              Schedule one now
            </Link>
          </div>
        ) : (
          <div className="divide-y divide-slate-100">
            {todayApts.map((apt: any) => {
              const riskCat = getRiskCategory(apt.no_show_risk_score ?? 0);
              return (
                <Link
                  key={apt.id}
                  to={`/appointments/${apt.id}`}
                  className="flex items-center gap-4 px-6 py-4 hover:bg-slate-50 transition-colors"
                >
                  <div className="w-10 h-10 rounded-full bg-teal-100 text-teal-700 flex items-center justify-center font-bold text-sm flex-shrink-0">
                    {apt.patient?.full_name?.charAt(0) ?? '?'}
                  </div>
                  <div className="flex-1 min-w-0">
                    <p className="font-medium text-slate-900 truncate">{apt.patient?.full_name}</p>
                    <p className="text-slate-500 text-sm truncate">Dr. {apt.doctor?.full_name}</p>
                  </div>
                  <div className="flex items-center gap-3 flex-shrink-0">
                    <div className="flex items-center gap-1 text-slate-500 text-sm">
                      <Clock className="w-3.5 h-3.5" />
                      {format(new Date(apt.scheduled_at), 'h:mm a')}
                    </div>
                    {apt.no_show_risk_score >= 0.5 && (
                      <div className={`flex items-center gap-1 text-xs font-medium ${RISK_COLORS[riskCat]}`}>
                        <Brain className="w-3.5 h-3.5" />
                        {Math.round(apt.no_show_risk_score * 100)}% risk
                      </div>
                    )}
                    <span className={`px-2 py-0.5 rounded-full text-xs font-medium ${STATUS_COLORS[apt.status] ?? 'bg-slate-100 text-slate-600'}`}>
                      {apt.status}
                    </span>
                  </div>
                </Link>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}

function getGreeting() {
  const h = new Date().getHours();
  if (h < 12) return 'morning';
  if (h < 17) return 'afternoon';
  return 'evening';
}
