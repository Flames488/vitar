/**
 * Vitar v5 - Appointment Detail Page
 */

import { useParams, useNavigate } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { format } from 'date-fns';
import { Brain, Bell, ArrowLeft, CheckCircle, XCircle, RefreshCw, UserX } from 'lucide-react';
import { appointmentsApi, aiApi } from '@/lib/api/services';
import { toast } from 'sonner';
import { getApiError } from '@/lib/api/client';

const RISK_COLORS: Record<string, string> = {
  low: 'text-green-600 bg-green-50', medium: 'text-yellow-600 bg-yellow-50',
  high: 'text-orange-600 bg-orange-50', critical: 'text-red-600 bg-red-50',
};

function getRiskCat(score: number) {
  if (score < 0.25) return 'low'; if (score < 0.5) return 'medium';
  if (score < 0.75) return 'high'; return 'critical';
}

export default function AppointmentDetailPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const qc = useQueryClient();

  const { data: apt, isLoading } = useQuery({
    queryKey: ['appointment', id],
    queryFn: () => appointmentsApi.get(id!),
    enabled: !!id,
  });

  const updateMutation = useMutation({
    mutationFn: (status: string) => appointmentsApi.update(id!, { status }),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['appointment', id] }); toast.success('Updated'); },
    onError: (err) => toast.error(getApiError(err)),
  });

  const predictMutation = useMutation({
    mutationFn: () => aiApi.predict(id!),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['appointment', id] }); toast.success('Risk score updated'); },
  });

  if (isLoading) return <div className="p-6 text-slate-400">Loading...</div>;
  if (!apt) return <div className="p-6 text-slate-400">Appointment not found</div>;

  const riskCat = getRiskCat(apt.no_show_risk_score ?? 0);
  const riskStyle = RISK_COLORS[riskCat];

  return (
    <div className="p-6 max-w-3xl mx-auto space-y-6">
      <button onClick={() => navigate(-1)} className="flex items-center gap-1.5 text-slate-500 hover:text-slate-700 text-sm">
        <ArrowLeft className="w-4 h-4" /> Back
      </button>

      <div className="bg-white rounded-xl border border-slate-200 p-6 space-y-6">
        {/* Header */}
        <div className="flex items-start justify-between">
          <div>
            <h1 className="text-xl font-bold text-slate-900">{apt.patient?.full_name}</h1>
            <p className="text-slate-500 text-sm mt-0.5">Dr. {apt.doctor?.full_name} · {apt.doctor?.specialty}</p>
            <p className="text-slate-500 text-sm">{format(new Date(apt.scheduled_at), 'EEEE, MMMM d yyyy · h:mm a')}</p>
          </div>
          <span className={`px-3 py-1 rounded-full text-sm font-medium capitalize
            ${apt.status === 'confirmed' ? 'bg-blue-100 text-blue-700' :
              apt.status === 'completed' ? 'bg-green-100 text-green-700' :
              apt.status === 'cancelled' ? 'bg-red-100 text-red-700' :
              apt.status === 'no_show'   ? 'bg-orange-100 text-orange-700' :
              'bg-slate-100 text-slate-600'}`}>
            {apt.status.replace('_', ' ')}
          </span>
        </div>

        {/* AI Risk */}
        <div className={`rounded-xl border p-4 ${riskStyle}`}>
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <Brain className="w-5 h-5" />
              <span className="font-semibold capitalize">AI Risk: {riskCat}</span>
              <span className="font-bold">{Math.round((apt.no_show_risk_score ?? 0) * 100)}%</span>
            </div>
            <button onClick={() => predictMutation.mutate()} disabled={predictMutation.isPending}
              className="flex items-center gap-1.5 text-xs font-medium px-2.5 py-1 rounded-full bg-white/60 hover:bg-white/80 transition-colors">
              <RefreshCw className={`w-3.5 h-3.5 ${predictMutation.isPending ? 'animate-spin' : ''}`} />
              Refresh
            </button>
          </div>
          {apt.risk_factors && Object.keys(apt.risk_factors).length > 0 && (
            <p className="text-xs mt-2 opacity-80">
              Reminders sent: {apt.reminder_count} ·
              Patient no-show rate: {Math.round((apt.patient?.no_show_rate ?? 0) * 100)}%
            </p>
          )}
        </div>

        {/* Notifications */}
        {apt.notifications && apt.notifications.length > 0 && (
          <div>
            <h3 className="font-semibold text-slate-900 mb-3 flex items-center gap-2">
              <Bell className="w-4 h-4" /> Notifications
            </h3>
            <div className="space-y-2">
              {apt.notifications.map((n: any) => (
                <div key={n.id} className="flex items-center justify-between text-sm p-2.5 bg-slate-50 rounded-lg">
                  <div className="flex items-center gap-2">
                    <span className="capitalize font-medium text-slate-700">{n.channel}</span>
                    <span className="text-slate-400">·</span>
                    <span className="text-slate-500 capitalize">{n.type}</span>
                  </div>
                  <div className="flex items-center gap-2">
                    <span className="text-slate-400 text-xs">{format(new Date(n.scheduled_for), 'MMM d h:mm a')}</span>
                    <span className={`text-xs font-medium capitalize ${
                      n.status === 'sent' || n.status === 'delivered' ? 'text-green-600' :
                      n.status === 'failed' ? 'text-red-600' : 'text-yellow-600'}`}>
                      {n.status}
                    </span>
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Actions */}
        {['confirmed', 'pending'].includes(apt.status) && (
          <div className="flex gap-3 pt-2 border-t border-slate-100">
            <button onClick={() => updateMutation.mutate('completed')} disabled={updateMutation.isPending}
              className="flex-1 flex items-center justify-center gap-2 bg-green-600 hover:bg-green-700 text-white font-medium py-2.5 rounded-lg text-sm transition-colors">
              <CheckCircle className="w-4 h-4" /> Mark Completed
            </button>
            <button onClick={() => updateMutation.mutate('no_show')} disabled={updateMutation.isPending}
              className="flex-1 flex items-center justify-center gap-2 bg-orange-500 hover:bg-orange-600 text-white font-medium py-2.5 rounded-lg text-sm transition-colors">
              <UserX className="w-4 h-4" /> No Show
            </button>
            <button onClick={() => { if(confirm('Cancel appointment?')) updateMutation.mutate('cancelled'); }}
              disabled={updateMutation.isPending}
              className="flex items-center justify-center gap-2 border border-red-300 text-red-600 hover:bg-red-50 font-medium py-2.5 px-4 rounded-lg text-sm transition-colors">
              <XCircle className="w-4 h-4" />
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
