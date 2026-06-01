// Earnings Page
import { useQuery } from '@tanstack/react-query';
import { analyticsApi } from '@/lib/api/services';
import { useGeoStore } from '@/stores/geoStore';
import { DollarSign } from 'lucide-react';

export function EarningsPage() {
  const { data } = useQuery({ queryKey: ['analytics', 'dashboard'], queryFn: analyticsApi.dashboard });
  const { formatMoney } = useGeoStore();
  return (
    <div className="p-6 max-w-3xl mx-auto space-y-6">
      <h1 className="text-2xl font-bold text-slate-900">Earnings</h1>
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
        <div className="bg-white rounded-xl border border-slate-200 p-6 flex items-center gap-4">
          <div className="w-12 h-12 bg-green-100 rounded-xl flex items-center justify-center">
            <DollarSign className="w-6 h-6 text-green-600" />
          </div>
          <div>
            <p className="text-slate-500 text-sm">This Month Revenue</p>
            <p className="text-2xl font-bold text-slate-900">{formatMoney(data?.revenue?.month_total ?? 0)}</p>
          </div>
        </div>
        <div className="bg-white rounded-xl border border-slate-200 p-6 flex items-center gap-4">
          <div className="w-12 h-12 bg-teal-100 rounded-xl flex items-center justify-center">
            <DollarSign className="w-6 h-6 text-teal-600" />
          </div>
          <div>
            <p className="text-slate-500 text-sm">Revenue Recovered by AI</p>
            <p className="text-2xl font-bold text-slate-900">{formatMoney(data?.revenue?.recovered_from_reminders ?? 0)}</p>
            <p className="text-slate-400 text-xs">From reminder-influenced attendances</p>
          </div>
        </div>
      </div>
    </div>
  );
}
export default EarningsPage;
