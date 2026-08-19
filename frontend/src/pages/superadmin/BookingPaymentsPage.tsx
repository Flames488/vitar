/**
 * Vitar — Admin Dashboard: Booking Payments
 * Every patient payment for a clinic appointment, platform-wide — merged
 * with its payout status and send action. Used to be split across this
 * page and a separate Payouts page, which meant seeing "paid" here and
 * "pending payout" there for the exact same booking with no way to tell
 * from either page that they described two legs of one transaction. One
 * row now tells the whole story.
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

function formatNaira(amount: number): string {
  return `₦${amount.toLocaleString('en-NG', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

function formatKobo(kobo: number): string {
  return formatNaira(kobo / 100);
}

export default function BookingPaymentsPage() {
  const { c } = useAdminTheme();
  const qc = useQueryClient();

  const [statusFilter, setStatusFilter] = useState('');
  const [page, setPage] = useState(1);

  const { data, isLoading } = useQuery({
    queryKey: ['admin', 'booking-payments', { statusFilter, page }],
    queryFn: () => adminApi.bookingPayments.list({ status: statusFilter || undefined, page, limit: 20 }),
  });

  const sendMutation = useMutation({
    mutationFn: (payoutId: string) => adminApi.payouts.send(payoutId),
    onSuccess: () => {
      toast.success('Payout sent');
      qc.invalidateQueries({ queryKey: ['admin', 'booking-payments'] });
    },
    onError: (err) => toast.error(getApiError(err)),
  });

  const items = data?.items ?? [];

  return (
    <div className="p-6 space-y-4 max-w-6xl mx-auto">
      <div>
        <h1 className={`text-2xl font-bold ${c.text}`}>Booking Payments</h1>
        <p className={`text-sm mt-1 ${c.textMuted}`}>{data?.total ?? 0} payments — patient payment and clinic payout, together</p>
      </div>

      <Select value={statusFilter} onChange={(e) => { setStatusFilter(e.target.value); setPage(1); }} className="sm:w-48">
        <option value="">All payment statuses</option>
        <option value="paid">Paid</option>
        <option value="pending">Pending</option>
        <option value="failed">Failed</option>
        <option value="refunded">Refunded</option>
      </Select>

      <div className={`rounded-xl border overflow-hidden ${c.panel}`}>
        {isLoading ? (
          <LoadingState message="Loading booking payments..." />
        ) : items.length === 0 ? (
          <EmptyState message="No booking payments found" />
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className={`border-b ${c.border}`}>
                  <th className={`text-left px-4 py-3 font-medium ${c.textMuted}`}>Clinic</th>
                  <th className={`text-left px-4 py-3 font-medium ${c.textMuted}`}>Patient</th>
                  <th className={`text-left px-4 py-3 font-medium ${c.textMuted}`}>Total Paid</th>
                  <th className={`text-left px-4 py-3 font-medium ${c.textMuted}`}>Patient Payment</th>
                  <th className={`text-left px-4 py-3 font-medium ${c.textMuted}`}>Clinic Share</th>
                  <th className={`text-left px-4 py-3 font-medium ${c.textMuted}`}>Payout Status</th>
                  <th className="px-4 py-3" />
                </tr>
              </thead>
              <tbody className={`divide-y ${c.divide}`}>
                {items.map((p: any) => (
                  <tr key={p.id} className={c.panelHover}>
                    <td className="px-4 py-3">
                      <p className={`font-medium ${c.text}`}>{p.clinic_name ?? '—'}</p>
                      <p className={`text-xs ${c.textFaint}`}>{p.provider_reference}</p>
                    </td>
                    <td className={`px-4 py-3 ${c.text}`}>{p.patient_name ?? '—'}</td>
                    <td className={`px-4 py-3 font-medium ${c.text}`}>{formatNaira(p.total_amount)}</td>
                    <td className="px-4 py-3"><StatusBadge status={p.status} /></td>
                    <td className={`px-4 py-3 ${c.textMuted}`}>
                      {p.payout ? formatKobo(p.payout.amount) : formatNaira(p.clinic_share)}
                    </td>
                    <td className="px-4 py-3">
                      {p.payout
                        ? <StatusBadge status={p.payout.status} />
                        : <span className={`text-xs ${c.textFaint}`}>No payout yet</span>}
                      {p.payout?.sent_at && (
                        <p className={`text-xs mt-0.5 ${c.textFaint}`}>
                          {new Date(p.payout.sent_at).toLocaleDateString()}
                        </p>
                      )}
                    </td>
                    <td className="px-4 py-3 text-right">
                      {p.payout && p.payout.status !== 'sent' && (
                        <button
                          onClick={() => {
                            if (window.confirm(`Send ${formatKobo(p.payout.amount)} to ${p.clinic_name ?? 'this clinic'} now?`)) {
                              sendMutation.mutate(p.payout.id);
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
