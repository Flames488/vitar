/**
 * Vitar v5 - Appointments Page
 */

import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { Link } from 'react-router-dom';
import { Plus, Search, Filter, Brain, Clock } from 'lucide-react';
import { appointmentsApi } from '@/lib/api/services';
import { format } from 'date-fns';
import { toast } from 'sonner';

const STATUS_STYLES: Record<string, string> = {
  confirmed: 'bg-blue-100 text-blue-700',
  completed: 'bg-green-100 text-green-700',
  cancelled: 'bg-red-100 text-red-700',
  no_show:   'bg-orange-100 text-orange-700',
  pending:   'bg-yellow-100 text-yellow-700',
};

export default function AppointmentsPage() {
  const [search, setSearch] = useState('');
  const [statusFilter, setStatusFilter] = useState('');
  const [page, setPage] = useState(1);
  const qc = useQueryClient();

  const { data, isLoading } = useQuery({
    queryKey: ['appointments', page, statusFilter],
    queryFn: () => appointmentsApi.list({ status: statusFilter || undefined, page, limit: 20 }),
  });

  const cancelMutation = useMutation({
    mutationFn: (id: string) => appointmentsApi.cancel(id, 'Cancelled by clinic'),
    onSuccess: () => {
      toast.success('Appointment cancelled');
      qc.invalidateQueries({ queryKey: ['appointments'] });
    },
    onError: () => toast.error('Failed to cancel'),
  });

  const appointments = (data?.items ?? []).filter((a: any) =>
    !search ||
    a.patient?.full_name?.toLowerCase().includes(search.toLowerCase()) ||
    a.doctor?.full_name?.toLowerCase().includes(search.toLowerCase())
  );

  return (
    <div className="p-6 space-y-4 max-w-7xl mx-auto">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold text-slate-900">Appointments</h1>
        <Link to="/appointments/new"
          className="flex items-center gap-2 bg-teal-600 hover:bg-teal-700 text-white px-4 py-2.5 rounded-lg text-sm font-medium transition-colors">
          <Plus className="w-4 h-4" /> New Appointment
        </Link>
      </div>

      {/* Filters */}
      <div className="flex items-center gap-3 flex-wrap">
        <div className="relative flex-1 min-w-48">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" />
          <input value={search} onChange={e => setSearch(e.target.value)}
            placeholder="Search patient or doctor..."
            className="w-full pl-9 pr-3 py-2 border border-slate-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-teal-500" />
        </div>
        <select value={statusFilter} onChange={e => { setStatusFilter(e.target.value); setPage(1); }}
          className="border border-slate-300 rounded-lg px-3 py-2 text-sm bg-white focus:outline-none focus:ring-2 focus:ring-teal-500">
          <option value="">All statuses</option>
          <option value="confirmed">Confirmed</option>
          <option value="completed">Completed</option>
          <option value="cancelled">Cancelled</option>
          <option value="no_show">No Show</option>
        </select>
      </div>

      {/* Table */}
      <div className="bg-white rounded-xl border border-slate-200 overflow-hidden">
        {isLoading ? (
          <div className="py-16 text-center text-slate-400 text-sm">Loading appointments...</div>
        ) : appointments.length === 0 ? (
          <div className="py-16 text-center text-slate-400 text-sm">No appointments found</div>
        ) : (
          <div className="divide-y divide-slate-100">
            {appointments.map((apt: any) => (
              <Link key={apt.id} to={`/appointments/${apt.id}`}
                className="flex items-center gap-4 px-6 py-4 hover:bg-slate-50 transition-colors">
                <div className="w-10 h-10 rounded-full bg-teal-100 text-teal-700 flex items-center justify-center font-bold text-sm flex-shrink-0">
                  {apt.patient?.full_name?.charAt(0) ?? '?'}
                </div>
                <div className="flex-1 min-w-0">
                  <p className="font-medium text-slate-900 truncate">{apt.patient?.full_name}</p>
                  <p className="text-slate-500 text-sm">Dr. {apt.doctor?.full_name} · {apt.doctor?.specialty}</p>
                </div>
                <div className="hidden sm:flex items-center gap-1.5 text-slate-500 text-sm">
                  <Clock className="w-3.5 h-3.5" />
                  {format(new Date(apt.scheduled_at), 'MMM d, h:mm a')}
                </div>
                {apt.no_show_risk_score >= 0.5 && (
                  <div className="hidden sm:flex items-center gap-1 text-xs font-medium text-orange-600">
                    <Brain className="w-3.5 h-3.5" />
                    {Math.round(apt.no_show_risk_score * 100)}%
                  </div>
                )}
                <span className={`px-2.5 py-0.5 rounded-full text-xs font-medium flex-shrink-0 ${STATUS_STYLES[apt.status] ?? 'bg-slate-100 text-slate-600'}`}>
                  {apt.status.replace('_', ' ')}
                </span>
              </Link>
            ))}
          </div>
        )}
      </div>

      {/* Pagination */}
      {data && data.pages > 1 && (
        <div className="flex justify-center gap-2">
          <button onClick={() => setPage(p => Math.max(1, p-1))} disabled={page === 1}
            className="px-3 py-1.5 border border-slate-300 rounded-lg text-sm disabled:opacity-40">← Prev</button>
          <span className="px-3 py-1.5 text-sm text-slate-600">Page {page} of {data.pages}</span>
          <button onClick={() => setPage(p => Math.min(data.pages, p+1))} disabled={page === data.pages}
            className="px-3 py-1.5 border border-slate-300 rounded-lg text-sm disabled:opacity-40">Next →</button>
        </div>
      )}
    </div>
  );
}
