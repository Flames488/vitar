/**
 * Vitar — AI Core: Lead Hunter
 * Leads table, "Run now" trigger, run history.
 */
import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { Play, Loader2 } from 'lucide-react';
import { adminApi } from '@/lib/api/services';
import { getApiError } from '@/lib/api/client';
import {
  useAdminTheme, Select, EmptyState, LoadingState, TextInput, PrimaryButton,
} from '@/components/admin/AdminUI';

const STATUS_TINT: Record<string, string> = {
  new: 'bg-blue-100 text-blue-700',
  contacted: 'bg-amber-100 text-amber-700',
  replied: 'bg-teal-100 text-teal-700',
  trial_started: 'bg-purple-100 text-purple-700',
  paid: 'bg-green-100 text-green-700',
  lost: 'bg-slate-200 text-slate-600',
};

const RUN_STATUS_TINT: Record<string, string> = {
  success: 'bg-green-100 text-green-700',
  failed: 'bg-red-100 text-red-700',
  partial: 'bg-amber-100 text-amber-700',
};

export default function LeadHunterPage() {
  const { c } = useAdminTheme();
  const qc = useQueryClient();

  const [statusFilter, setStatusFilter] = useState('');
  const [city, setCity] = useState('Lagos');
  const [query, setQuery] = useState('private clinic');

  const { data, isLoading } = useQuery({
    queryKey: ['admin', 'leads', { status: statusFilter }],
    queryFn: () => adminApi.leads.list({ status: statusFilter || undefined, sort_by: 'score' }),
  });

  const { data: runsData } = useQuery({
    queryKey: ['admin', 'agents', 'lead_hunter', 'runs'],
    queryFn: () => adminApi.agents.listRuns('lead_hunter', 10),
  });

  const runMutation = useMutation({
    mutationFn: () => adminApi.agents.runLeadHunter(city, query),
    onSuccess: () => {
      toast.success(`Lead Hunter queued for ${city}`);
      setTimeout(() => {
        qc.invalidateQueries({ queryKey: ['admin', 'leads'] });
        qc.invalidateQueries({ queryKey: ['admin', 'agents', 'lead_hunter', 'runs'] });
      }, 3000);
    },
    onError: (err) => toast.error(getApiError(err)),
  });

  const leads = data?.leads ?? [];
  const runs = runsData?.runs ?? [];

  return (
    <div className="p-6 space-y-5 max-w-6xl mx-auto">
      <div>
        <h1 className={`text-2xl font-bold ${c.text}`}>Lead Hunter</h1>
        <p className={`text-sm mt-1 ${c.textMuted}`}>{data?.total ?? 0} leads</p>
      </div>

      {/* Run now */}
      <div className={`rounded-xl border p-5 ${c.panel}`}>
        <h2 className={`text-sm font-bold mb-3 ${c.text}`}>Run now</h2>
        <div className="flex flex-col sm:flex-row gap-2">
          <TextInput value={city} onChange={(e) => setCity(e.target.value)} placeholder="City" className="sm:w-40" />
          <TextInput value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Search query" className="flex-1" />
          <PrimaryButton onClick={() => runMutation.mutate()} disabled={runMutation.isPending || !city} className="flex items-center gap-2 justify-center">
            {runMutation.isPending ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Play className="w-3.5 h-3.5" />}
            Run now
          </PrimaryButton>
        </div>
      </div>

      {/* Leads table */}
      <div className={`rounded-xl border overflow-hidden ${c.panel}`}>
        <div className={`flex items-center justify-between px-5 py-4 border-b ${c.border}`}>
          <h2 className={`text-sm font-bold ${c.text}`}>Leads</h2>
          <Select value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)} className="w-40">
            <option value="">All statuses</option>
            {Object.keys(STATUS_TINT).map((s) => <option key={s} value={s}>{s.replace(/_/g, ' ')}</option>)}
          </Select>
        </div>
        {isLoading ? <LoadingState /> : leads.length === 0 ? <EmptyState message="No leads yet" /> : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className={`text-left border-b ${c.border} ${c.textFaint}`}>
                  <th className="px-5 py-2.5 font-medium">Clinic</th>
                  <th className="px-5 py-2.5 font-medium">City</th>
                  <th className="px-5 py-2.5 font-medium">Source</th>
                  <th className="px-5 py-2.5 font-medium">Score</th>
                  <th className="px-5 py-2.5 font-medium">Status</th>
                  <th className="px-5 py-2.5 font-medium">Found</th>
                </tr>
              </thead>
              <tbody className={`divide-y ${c.divide}`}>
                {leads.map((l: any) => (
                  <tr key={l.id} className={c.panelHover}>
                    <td className={`px-5 py-3 font-medium ${c.text}`}>{l.clinic_name}</td>
                    <td className={`px-5 py-3 ${c.textMuted}`}>{l.city ?? '—'}</td>
                    <td className={`px-5 py-3 ${c.textMuted} capitalize`}>{(l.source ?? '').toLowerCase().replace(/_/g, ' ')}</td>
                    <td className={`px-5 py-3 font-semibold ${c.text}`}>{l.score}</td>
                    <td className="px-5 py-3">
                      <span className={`inline-flex px-2 py-0.5 rounded-full text-xs font-medium capitalize ${STATUS_TINT[(l.status ?? '').toLowerCase()] ?? 'bg-slate-100 text-slate-600'}`}>
                        {(l.status ?? '').toLowerCase().replace(/_/g, ' ')}
                      </span>
                    </td>
                    <td className={`px-5 py-3 ${c.textFaint}`}>{l.created_at ? new Date(l.created_at).toLocaleDateString() : '—'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Run history */}
      <div className={`rounded-xl border overflow-hidden ${c.panel}`}>
        <div className={`px-5 py-4 border-b ${c.border}`}>
          <h2 className={`text-sm font-bold ${c.text}`}>Run history</h2>
        </div>
        {runs.length === 0 ? <EmptyState message="No runs yet" /> : (
          <div className={`divide-y ${c.divide}`}>
            {runs.map((r: any) => (
              <div key={r.id} className="flex items-center justify-between px-5 py-3">
                <div>
                  <span className={`inline-flex px-2 py-0.5 rounded-full text-xs font-medium capitalize mr-2 ${RUN_STATUS_TINT[(r.status ?? '').toLowerCase()] ?? 'bg-slate-100 text-slate-600'}`}>
                    {(r.status ?? '').toLowerCase()}
                  </span>
                  <span className={`text-sm ${c.textMuted}`}>{r.items_processed} processed, {r.items_created} created</span>
                  {r.error_message && <p className="text-xs text-red-500 mt-1">{r.error_message}</p>}
                </div>
                <span className={`text-xs ${c.textFaint}`}>{r.started_at ? new Date(r.started_at).toLocaleString() : '—'}</span>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
