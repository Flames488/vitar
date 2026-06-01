/**
 * Vitar v5 - Patients Page
 */
import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Link } from 'react-router-dom';
import { Search, Plus, Brain } from 'lucide-react';
import { patientsApi } from '@/lib/api/services';

export default function PatientsPage() {
  const [search, setSearch] = useState('');
  const [page, setPage] = useState(1);

  const { data, isLoading } = useQuery({
    queryKey: ['patients', page, search],
    queryFn: () => patientsApi.list({ search: search || undefined, page, limit: 20 }),
  });

  const patients = data?.items ?? [];

  return (
    <div className="p-6 space-y-4 max-w-5xl mx-auto">
      <h1 className="text-2xl font-bold text-slate-900">Patients</h1>
      <div className="relative">
        <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" />
        <input value={search} onChange={e => { setSearch(e.target.value); setPage(1); }}
          placeholder="Search by name, phone, or email..."
          className="w-full pl-9 pr-3 py-2.5 border border-slate-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-teal-500" />
      </div>

      <div className="bg-white rounded-xl border border-slate-200 overflow-hidden">
        {isLoading ? (
          <div className="py-12 text-center text-slate-400 text-sm">Loading patients...</div>
        ) : patients.length === 0 ? (
          <div className="py-12 text-center text-slate-400 text-sm">No patients found</div>
        ) : (
          <div className="divide-y divide-slate-100">
            {patients.map((p: any) => (
              <Link key={p.id} to={`/patients/${p.id}`}
                className="flex items-center gap-4 px-6 py-4 hover:bg-slate-50 transition-colors">
                <div className="w-10 h-10 rounded-full bg-purple-100 text-purple-700 flex items-center justify-center font-bold text-sm flex-shrink-0">
                  {p.full_name.charAt(0)}
                </div>
                <div className="flex-1 min-w-0">
                  <p className="font-medium text-slate-900 truncate">{p.full_name}</p>
                  <p className="text-slate-500 text-sm">{p.phone} {p.email ? `· ${p.email}` : ''}</p>
                </div>
                <div className="text-right hidden sm:block">
                  <p className="text-sm text-slate-600">{p.total_appointments ?? 0} visits</p>
                  {(p.historical_no_show_rate ?? 0) > 0.3 && (
                    <div className="flex items-center gap-1 justify-end text-orange-600 text-xs font-medium">
                      <Brain className="w-3 h-3" />
                      {Math.round(p.historical_no_show_rate * 100)}% no-show
                    </div>
                  )}
                </div>
              </Link>
            ))}
          </div>
        )}
      </div>

      {data && data.total > 20 && (
        <div className="flex justify-center gap-2">
          <button onClick={() => setPage(p => Math.max(1, p-1))} disabled={page === 1}
            className="px-3 py-1.5 border border-slate-300 rounded-lg text-sm disabled:opacity-40">← Prev</button>
          <span className="px-3 py-1.5 text-sm text-slate-600">{page}</span>
          <button onClick={() => setPage(p => p+1)} disabled={patients.length < 20}
            className="px-3 py-1.5 border border-slate-300 rounded-lg text-sm disabled:opacity-40">Next →</button>
        </div>
      )}
    </div>
  );
}
