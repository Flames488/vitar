// Patient Detail Page
import { useParams } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { patientsApi } from '@/lib/api/services';
import { format } from 'date-fns';
import { Brain } from 'lucide-react';

export function PatientDetailPage() {
  const { id } = useParams<{ id: string }>();
  const { data: patient, isLoading } = useQuery({
    queryKey: ['patient', id], queryFn: () => patientsApi.get(id!), enabled: !!id,
  });
  if (isLoading) return <div className="p-6 text-slate-400">Loading...</div>;
  if (!patient) return <div className="p-6 text-slate-400">Not found</div>;

  return (
    <div className="p-6 max-w-3xl mx-auto space-y-6">
      <div className="bg-white rounded-xl border border-slate-200 p-6">
        <div className="flex items-center gap-4 mb-6">
          <div className="w-16 h-16 rounded-full bg-purple-100 text-purple-700 flex items-center justify-center font-bold text-2xl">
            {patient.full_name.charAt(0)}
          </div>
          <div>
            <h1 className="text-xl font-bold text-slate-900">{patient.full_name}</h1>
            <p className="text-slate-500">{patient.phone}</p>
            {patient.email && <p className="text-slate-400 text-sm">{patient.email}</p>}
          </div>
        </div>

        <div className="grid grid-cols-3 gap-4 mb-6">
          {[
            { label: 'Total Visits', value: patient.total_appointments ?? 0 },
            { label: 'No-Shows', value: patient.total_no_shows ?? 0 },
            { label: 'No-Show Rate', value: `${Math.round((patient.historical_no_show_rate ?? 0) * 100)}%` },
          ].map(s => (
            <div key={s.label} className="bg-slate-50 rounded-xl p-4 text-center">
              <p className="text-2xl font-bold text-slate-900">{s.value}</p>
              <p className="text-slate-500 text-xs mt-0.5">{s.label}</p>
            </div>
          ))}
        </div>

        {patient.recent_appointments?.length > 0 && (
          <div>
            <h3 className="font-semibold text-slate-900 mb-3">Recent Appointments</h3>
            <div className="space-y-2">
              {patient.recent_appointments.map((a: any) => (
                <div key={a.id} className="flex items-center justify-between py-2 border-b border-slate-100 last:border-0">
                  <span className="text-sm text-slate-700">{format(new Date(a.scheduled_at), 'MMM d, yyyy h:mm a')}</span>
                  <span className={`text-xs font-medium px-2 py-0.5 rounded-full capitalize
                    ${a.status === 'completed' ? 'bg-green-100 text-green-700' :
                      a.status === 'no_show' ? 'bg-orange-100 text-orange-700' :
                      a.status === 'cancelled' ? 'bg-red-100 text-red-700' :
                      'bg-blue-100 text-blue-700'}`}>
                    {a.status.replace('_', ' ')}
                  </span>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
export default PatientDetailPage;
