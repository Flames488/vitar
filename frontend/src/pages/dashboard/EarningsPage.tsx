// Earnings Page — revenue totals + where the money actually is right now
import { useQuery } from '@tanstack/react-query';
import { analyticsApi, clinicPayoutsApi } from '@/lib/api/services';
import { useGeoStore } from '@/stores/geoStore';

function StatusBadge({ status }: { status: string }) {
  const map: Record<string, string> = {
    pending_payout: 'bg-amber-100 text-amber-700',
    sent: 'bg-green-100 text-green-700',
    failed: 'bg-red-100 text-red-700',
  };
  const label: Record<string, string> = {
    pending_payout: 'On the way',
    sent: 'Sent to your bank',
    failed: 'Failed — retrying',
  };
  return (
    <span className={`text-xs font-medium px-2 py-1 rounded-full ${map[status] ?? 'bg-slate-100 text-slate-600'}`}>
      {label[status] ?? status}
    </span>
  );
}

export function EarningsPage() {
  const { data } = useQuery({ queryKey: ['analytics', 'dashboard'], queryFn: analyticsApi.dashboard });
  const { data: summary } = useQuery({ queryKey: ['payouts', 'summary'], queryFn: clinicPayoutsApi.getSummary });
  const { data: history } = useQuery({ queryKey: ['payouts', 'history'], queryFn: () => clinicPayoutsApi.getHistory({ limit: 15 }) });
  const { formatMoney } = useGeoStore();

  return (
    <div className="p-6 max-w-3xl mx-auto space-y-6">
      <h1 className="text-2xl font-bold text-slate-900">Earnings</h1>

      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
        <div className="bg-white rounded-xl border border-slate-200 p-6 flex items-center gap-4">
          <div className="w-12 h-12 bg-green-100 rounded-xl flex items-center justify-center">
            <span className="text-xl font-bold text-green-600">₦</span>
          </div>
          <div>
            <p className="text-slate-500 text-sm">This Month Revenue</p>
            <p className="text-2xl font-bold text-slate-900">{formatMoney(data?.revenue?.month_total ?? 0)}</p>
          </div>
        </div>
        <div className="bg-white rounded-xl border border-slate-200 p-6 flex items-center gap-4">
          <div className="w-12 h-12 bg-teal-100 rounded-xl flex items-center justify-center">
            <span className="text-xl font-bold text-teal-600">₦</span>
          </div>
          <div>
            <p className="text-slate-500 text-sm">Revenue Recovered by AI</p>
            <p className="text-2xl font-bold text-slate-900">{formatMoney(data?.revenue?.recovered_from_reminders ?? 0)}</p>
            <p className="text-slate-400 text-xs">From reminder-influenced attendances</p>
          </div>
        </div>
      </div>

      {/* Payout status — this is the "where's my money" section */}
      <div className="bg-white rounded-xl border border-slate-200 p-6 space-y-4">
        <div className="flex items-center justify-between">
          <h2 className="text-lg font-semibold text-slate-900">Payouts to your bank account</h2>
          {summary?.bank_account ? (
            <span className="text-xs text-slate-500">
              {summary.bank_account.bank_name} · {summary.bank_account.account_number_masked}
            </span>
          ) : (
            <a href="/settings" className="text-xs text-teal-600 font-medium">Add a bank account →</a>
          )}
        </div>

        <div className="grid grid-cols-2 gap-4">
          <div>
            <p className="text-slate-500 text-sm">On the way to you</p>
            <p className="text-xl font-bold text-amber-600">{formatMoney(summary?.pending_amount ?? 0)}</p>
          </div>
          <div>
            <p className="text-slate-500 text-sm">Sent so far</p>
            <p className="text-xl font-bold text-green-600">{formatMoney(summary?.sent_total ?? 0)}</p>
          </div>
        </div>

        <p className="text-xs text-slate-400 border-t border-slate-100 pt-3">
          Patient payments are sent to your bank account automatically — no action needed.
          Money is transferred within {summary?.auto_send_after_minutes ?? 15} minutes of a patient paying.
          {summary?.platform_fee_pct ? ` A ${(summary.platform_fee_pct * 100).toFixed(0)}% processing fee covers payment gateway costs.` : ''}
        </p>

        {!!history?.items?.length && (
          <div className="pt-2 divide-y divide-slate-100">
            {history.items.map((item: any) => (
              <div key={item.id} className="flex items-center justify-between py-3">
                <div>
                  <p className="text-sm font-medium text-slate-900">{formatMoney(item.amount_to_clinic)}</p>
                  <p className="text-xs text-slate-400">
                    {item.sent_at ? `Sent ${new Date(item.sent_at).toLocaleDateString()}` : `Received ${new Date(item.created_at).toLocaleDateString()}`}
                  </p>
                </div>
                <StatusBadge status={item.status} />
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
export default EarningsPage;
