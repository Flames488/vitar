/**
 * Vitar v5 - Doctors Page
 */
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { Link } from 'react-router-dom';
import { Plus, Stethoscope, Pencil, ToggleLeft } from 'lucide-react';
import { doctorsApi } from '@/lib/api/services';
import { toast } from 'sonner';
import { useGeoStore } from '@/stores/geoStore';

export function DoctorsPage() {
  const qc = useQueryClient();
  const { formatMoney } = useGeoStore();
  const { data, isLoading } = useQuery({ queryKey: ['doctors'], queryFn: doctorsApi.list });

  const deactivateMutation = useMutation({
    mutationFn: (id: string) => doctorsApi.delete(id),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['doctors'] }); toast.success('Doctor deactivated'); },
  });

  const doctors = data?.doctors ?? [];

  return (
    <div className="p-6 space-y-4 max-w-5xl mx-auto">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold text-slate-900">Doctors</h1>
        <Link to="/doctors/new" className="flex items-center gap-2 bg-teal-600 hover:bg-teal-700 text-white px-4 py-2.5 rounded-lg text-sm font-medium transition-colors">
          <Plus className="w-4 h-4" /> Add Doctor
        </Link>
      </div>
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
        {isLoading && <p className="text-slate-400 text-sm col-span-3">Loading...</p>}
        {doctors.map((d: any) => (
          <div key={d.id} className="bg-white rounded-xl border border-slate-200 p-5 space-y-3">
            <div className="flex items-start justify-between">
              <div className="flex items-center gap-3">
                <div className="w-12 h-12 rounded-full bg-teal-100 text-teal-700 flex items-center justify-center font-bold text-lg flex-shrink-0">
                  {d.full_name.charAt(0)}
                </div>
                <div>
                  <p className="font-semibold text-slate-900">Dr. {d.full_name}</p>
                  <p className="text-slate-500 text-xs">{d.specialty ?? 'General'}</p>
                </div>
              </div>
            </div>
            {d.consultation_fee > 0 && (
              <p className="text-sm text-slate-600">Fee: <span className="font-medium">{formatMoney(d.consultation_fee)}</span></p>
            )}
            <div className="flex gap-2">
              <Link to={`/doctors/${d.id}`} className="flex-1 flex items-center justify-center gap-1.5 border border-slate-300 hover:bg-slate-50 text-slate-700 py-2 rounded-lg text-sm transition-colors">
                <Pencil className="w-3.5 h-3.5" /> Manage
              </Link>
              <button onClick={() => { if(confirm('Deactivate doctor?')) deactivateMutation.mutate(d.id); }}
                className="flex items-center gap-1.5 border border-red-200 hover:bg-red-50 text-red-600 px-3 py-2 rounded-lg text-sm transition-colors">
                <ToggleLeft className="w-3.5 h-3.5" />
              </button>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
export default DoctorsPage;
