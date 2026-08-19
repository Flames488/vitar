/**
 * Vitar — Admin Dashboard: Booking Payments
 * Every patient payment for a clinic appointment, platform-wide — read
 * only (mirrors PayoutsPage.tsx's layout, minus the send action since
 * there's nothing to trigger here; payouts derived from these are managed
 * on the Payouts page).
 */
import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Link } from 'react-router-dom';
import { ArrowRight } from 'lucide-react';
import { adminApi } from '@/lib/api/services';
import {
  useAdminTheme, Select, Pagination, StatusBadge, EmptyState, LoadingState,
} from '@/components/admin/AdminUI';

function formatNaira(amount: number): string {
  return `₦${amount.toLocaleString('en-NG', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

export default function BookingPaymentsPage() {
  const { c } = useAdminTheme();

  const [statusFilter, setStatusFilter] = useState('');
  const [page, setPage] = useState(1);

  const { data, isLoading } = useQuery({
    queryKey: ['admin', 'booking-payments', { statusFilter, page }],
    queryFn: () => adminApi.bookingPayments.list({ status: statusFilter || undefined, page, limit: 20 }),
  });

  const items = data?.items ?? [];

  return (
    <div className="p-6 space-y-4 max-w-6xl mx-auto">
      <div>
        <h1 className={`text-2xl font-bold ${c.text}`}>Booking Payments</h1>
        <p className={`text-sm mt-1 ${c.textMuted}`}>{data?.total ?? 0} payments</p>
      </div>

      <Select value={statusFilter} onChange={(e) => { setStatusFilter(e.target.value); setPage(1); }} className="sm:w-48">
        <option value="">All statuses</option>
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
                  <th className={`text-left px-4 py-3 font-medium ${c.textMuted}`}>Clinic Share</th>
                  <th className={`text-left px-4 py-3 font-medium ${c.textMuted}`}>Status</th>
                  <th className={`text-left px-4 py-3 font-medium ${c.textMuted}`}>Paid At</th>
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
                    <td className={`px-4 py-3 ${c.textMuted}`}>{formatNaira(p.clinic_share)}</td>
                    <td className="px-4 py-3"><StatusBadge status={p.status} /></td>
                    <td className={`px-4 py-3 ${c.textMuted}`}>
                      {p.paid_at ? new Date(p.paid_at).toLocaleString() : '—'}
                    </td>
                    <td className="px-4 py-3 text-right">
                      <Link
                        to={`/admin/payouts?appointment=${p.appointment_id}`}
                        className={`inline-flex items-center gap-1 text-xs font-medium text-teal-500 hover:text-teal-400`}
                      >
                        Payout <ArrowRight className="w-3 h-3" />
                      </Link>
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
