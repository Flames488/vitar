/**
 * Vitar — AI Core: Customer Success
 * Open health signals, grouped by clinic, with acknowledge/resolve actions.
 */
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { CheckCircle2, Eye } from 'lucide-react';
import { adminApi } from '@/lib/api/services';
import { getApiError } from '@/lib/api/client';
import { useAdminTheme, EmptyState, LoadingState, SecondaryButton, PrimaryButton } from '@/components/admin/AdminUI';

export default function CustomerSuccessPage() {
  const { c } = useAdminTheme();
  const qc = useQueryClient();

  const { data, isLoading } = useQuery({
    queryKey: ['admin', 'health-signals', 'open'],
    queryFn: () => adminApi.healthSignals.list('open'),
  });

  const updateMutation = useMutation({
    mutationFn: ({ id, status }: { id: string; status: 'acknowledged' | 'resolved' }) =>
      adminApi.healthSignals.update(id, status),
    onSuccess: () => {
      toast.success('Updated');
      qc.invalidateQueries({ queryKey: ['admin', 'health-signals'] });
      qc.invalidateQueries({ queryKey: ['admin', 'agents', 'overview'] });
    },
    onError: (err) => toast.error(getApiError(err)),
  });

  const signals = data?.signals ?? [];
  const byClinic: Record<string, any[]> = {};
  for (const s of signals) {
    const key = s.clinic_name ?? 'Unknown';
    (byClinic[key] ??= []).push(s);
  }

  return (
    <div className="p-6 space-y-5 max-w-4xl mx-auto">
      <div>
        <h1 className={`text-2xl font-bold ${c.text}`}>Customer Success</h1>
        <p className={`text-sm mt-1 ${c.textMuted}`}>{signals.length} open health signals</p>
      </div>

      {isLoading ? (
        <LoadingState />
      ) : signals.length === 0 ? (
        <div className={`rounded-xl border p-6 ${c.panel}`}><EmptyState message="No open health signals — everything looks healthy" /></div>
      ) : (
        Object.entries(byClinic).map(([clinicName, clinicSignals]) => (
          <div key={clinicName} className={`rounded-xl border overflow-hidden ${c.panel}`}>
            <div className={`px-5 py-3 border-b ${c.border}`}>
              <h2 className={`text-sm font-bold ${c.text}`}>{clinicName}</h2>
            </div>
            <div className={`divide-y ${c.divide}`}>
              {clinicSignals.map((s: any) => (
                <div key={s.id} className="flex items-center justify-between px-5 py-3 gap-3">
                  <div className="min-w-0">
                    <p className={`text-sm font-medium capitalize ${c.text}`}>{(s.signal_type ?? '').toLowerCase().replace(/_/g, ' ')}</p>
                    <p className={`text-xs mt-0.5 truncate ${c.textFaint}`}>{s.detail}</p>
                  </div>
                  <div className="flex gap-2 flex-shrink-0">
                    <SecondaryButton
                      onClick={() => updateMutation.mutate({ id: s.id, status: 'acknowledged' })}
                      disabled={updateMutation.isPending}
                      className="flex items-center gap-1.5 text-xs px-3 py-1.5"
                    >
                      <Eye className="w-3.5 h-3.5" /> Acknowledge
                    </SecondaryButton>
                    <PrimaryButton
                      onClick={() => updateMutation.mutate({ id: s.id, status: 'resolved' })}
                      disabled={updateMutation.isPending}
                      className="flex items-center gap-1.5 text-xs px-3 py-1.5"
                    >
                      <CheckCircle2 className="w-3.5 h-3.5" /> Resolve
                    </PrimaryButton>
                  </div>
                </div>
              ))}
            </div>
          </div>
        ))
      )}
    </div>
  );
}
