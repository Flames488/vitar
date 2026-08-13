/**
 * Vitar — Admin Dashboard: Payouts
 * Manual retry UI for POST /admin/payouts/{id}/send — payouts otherwise
 * only ever send automatically via the auto-send-pending-payouts beat job.
 * This exists for a payout that failed (or is stuck pending) and needs a
 * human to trigger a retry after fixing whatever blocked it (e.g. the
 * clinic adding/verifying a payout bank account).
 */
import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { Send } from 'lucide-react';
import { adminApi } from '@/lib/api/services';
import { getApiError } from '@/lib/api/client';
import {
  useAdminTheme, Select, Pagination, StatusBadge, EmptyState, LoadingState,
} from '@/components/admin/AdminUI';

function formatNaira(kobo: number): string {
  return `₦${(kobo / 100).toLocaleString()}`;
}

export default function PayoutsPage() {
  const { c } = useAdminTheme();
  const qc = useQueryClient();

  const [statusFilter, setStatusFilter] = useState('');
  const [page, setPage] = useState(1);

  const { data, isLoading } = useQuery({
    queryKey: ['admin', 'payouts', { statusFilter, page }],
    queryFn: () => adminApi.payouts.list({ status: statusFilter || undefined, page, limit: 20 }),
  });

  const sendMutation = useMutation({
    mutationFn: (payoutId: string) => adminApi.payouts.send(payoutId),
    onSuccess: () => {
      toast.success('Payout sent');
      qc.invalidateQueries({ queryKey: ['admin', 'payouts'] });
    },
    onError: (err) => toast.error(getApiError(err)),
  });

  const items = data?.items ?? [];

  return (
    <div className="p-6 space-y-4 max-w-6xl mx-auto">
      <div>
        <h1 className={`text-2xl font-bold ${c.text}`}>Payouts</h1>
        <p className={`text-sm mt-1 ${c.textMuted}`}>{data?.total ?? 0} payouts</p>
      </div>

      <Select value={statusFilter} onChange={(e) => { setStatusFilter(e.target.value); setPage(1); }} className="sm:w-48">
        <option value="">All statuses</option>
        <option value="pending_payout">Pending</option>
        <option value="sent">Sent</option>
        <option value="failed">Failed</option>
      </Select>

      <div className={`rounded-xl border overflow-hidden ${c.panel}`}>
        {isLoading ? (
          <LoadingState message="Loading payouts..." />
        ) : items.length === 0 ? (
          <EmptyState message="No payouts found" />
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className={`border-b ${c.border}`}>
                  <th className={`text-left px-4 py-3 font-medium ${c.textMuted}`}>Clinic</th>
                  <th className={`text-left px-4 py-3 font-medium ${c.textMuted}`}>Amount</th>
                  <th className={`text-left px-4 py-3 font-medium ${c.textMuted}`}>Status</th>
                  <th className={`text-left px-4 py-3 font-medium ${c.textMuted}`}>Created</th>
                  <th className={`text-left px-4 py-3 font-medium ${c.textMuted}`}>Sent</th>
                  <th className="px-4 py-3" />
                </tr>
              </thead>
              <tbody className={`divide-y ${c.divide}`}>
                {items.map((p: any) => (
                  <tr key={p.id} className={c.panelHover}>
                    <td className="px-4 py-3">
                      <p className={`font-medium ${c.text}`}>{p.hospital_name ?? '—'}</p>
                      <p className={`text-xs ${c.textFaint}`}>{p.appointment_reference ?? p.appointment_id}</p>
                    </td>
                    <td className={`px-4 py-3 font-medium ${c.text}`}>{formatNaira(p.amount)}</td>
                    <td className="px-4 py-3"><StatusBadge status={p.status} /></td>
                    <td className={`px-4 py-3 ${c.textMuted}`}>
                      {p.created_at ? new Date(p.created_at).toLocaleDateString() : '—'}
                    </td>
                    <td className={`px-4 py-3 ${c.textMuted}`}>
                      {p.sent_at ? new Date(p.sent_at).toLocaleDateString() : '—'}
                    </td>
                    <td className="px-4 py-3 text-right">
                      {p.status !== 'sent' && (
                        <button
                          onClick={() => {
                            if (window.confirm(`Send ${formatNaira(p.amount)} to ${p.hospital_name ?? 'this clinic'} now?`)) {
                              sendMutation.mutate(p.id);
                            }
                          }}
                          disabled={sendMutation.isPending}
                          className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium bg-teal-600 hover:bg-teal-700 disabled:opacity-50 text-white"
                        >
                          <Send className="w-3.5 h-3.5" /> Send
                        </button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {data && <Pagination page={page} setPage={setPage} total={data.total} limit={20} />}
    </div>
  );
}
