/**
 * Vitar v5 - Doctor Detail Page
 * FIX: Removed deprecated onSuccess from useQuery (TanStack Query v5 removed it)
 * Use useEffect on data instead
 */
import { useParams } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { doctorsApi } from '@/lib/api/services';
import { toast } from 'sonner';
import { useState, useEffect, useRef } from 'react';
import DoctorDetailsSection, { type DoctorDetailsValue } from '@/components/shared/DoctorDetailsSection';

const DAYS = ['Monday','Tuesday','Wednesday','Thursday','Friday','Saturday','Sunday'];

export default function DoctorDetailPage() {
  const { id } = useParams<{ id: string }>();
  const qc = useQueryClient();
  const [selectedSlots, setSelectedSlots] = useState<number[]>([0,1,2,3,4]);
  const [details, setDetails] = useState<DoctorDetailsValue>({ email: '', phone: '', doctor_details_enabled: true });

  const { data: doctor, isLoading } = useQuery({
    queryKey: ['doctor', id],
    queryFn: () => doctorsApi.get(id!),
    enabled: !!id,
  });

  // Only sync local form state from the server ONCE per doctor id, not on
  // every refetch — otherwise saving either form (which invalidates and
  // refetches ['doctor', id]) re-runs this effect and clobbers whatever
  // unsaved edits the user has sitting in the *other* form.
  const initializedIdRef = useRef<string | null>(null);
  useEffect(() => {
    if (!doctor || initializedIdRef.current === doctor.id) return;
    if (doctor.availability?.length > 0) {
      setSelectedSlots(doctor.availability.map((a: any) => a.day_of_week));
    }
    setDetails({
      email: doctor.email || '',
      phone: doctor.phone || '',
      doctor_details_enabled: !!doctor.doctor_details_enabled,
    });
    initializedIdRef.current = doctor.id;
  }, [doctor]);

  const availMutation = useMutation({
    mutationFn: (slots: any[]) => doctorsApi.setAvailability(id!, slots),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['doctor', id] });
      toast.success('Availability saved');
    },
    onError: () => toast.error('Failed to save'),
  });

  const detailsMutation = useMutation({
    mutationFn: (next: DoctorDetailsValue) => doctorsApi.update(id!, next),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['doctor', id] });
      toast.success('Doctor Details saved');
    },
    onError: (err: any) => {
      const msg = err?.response?.data?.detail?.message || 'Failed to save Doctor Details';
      toast.error(msg);
      // Revert the optimistic toggle if the save was rejected (e.g. trial expired mid-edit)
      if (doctor) {
        setDetails({
          email: doctor.email || '',
          phone: doctor.phone || '',
          doctor_details_enabled: !!doctor.doctor_details_enabled,
        });
      }
    },
  });

  if (isLoading) return <div className="p-6 text-slate-400">Loading...</div>;
  if (!doctor) return <div className="p-6 text-slate-400">Doctor not found</div>;

  const toggleDay = (day: number) => {
    setSelectedSlots(prev =>
      prev.includes(day) ? prev.filter(d => d !== day) : [...prev, day]
    );
  };

  const saveAvailability = () => {
    const slots = selectedSlots.map(day => ({
      day_of_week: day, start_time: '09:00', end_time: '17:00',
      slot_duration_mins: 30, is_available: true,
    }));
    availMutation.mutate(slots);
  };

  return (
    <div className="p-6 max-w-3xl mx-auto space-y-6">
      <div className="bg-white rounded-xl border border-slate-200 p-6">
        <div className="flex items-center gap-4 mb-6">
          <div className="w-16 h-16 rounded-full bg-teal-100 text-teal-700 flex items-center justify-center font-bold text-2xl">
            {doctor.full_name?.charAt(0)}
          </div>
          <div>
            <h1 className="text-xl font-bold text-slate-900">Dr. {doctor.full_name}</h1>
            <p className="text-slate-500">{doctor.specialty ?? 'General Practitioner'}</p>
            {doctor.email && <p className="text-slate-400 text-sm">{doctor.email}</p>}
          </div>
        </div>

        <div className="mb-6">
          <DoctorDetailsSection
            value={details}
            onChange={setDetails}
          />
          <button
            onClick={() => detailsMutation.mutate(details)}
            disabled={detailsMutation.isPending}
            className="mt-3 bg-teal-600 hover:bg-teal-700 disabled:opacity-60 text-white font-medium px-6 py-2 rounded-lg text-sm transition-colors"
          >
            {detailsMutation.isPending ? 'Saving...' : 'Save Doctor Details'}
          </button>
        </div>

        <h3 className="font-semibold text-slate-900 mb-3">Working Days</h3>
        <div className="grid grid-cols-7 gap-2 mb-4">
          {DAYS.map((day, i) => (
            <button key={day} type="button" onClick={() => toggleDay(i)}
              className={`py-2 rounded-lg text-xs font-medium transition-colors ${
                selectedSlots.includes(i) ? 'bg-teal-600 text-white' : 'bg-slate-100 text-slate-600 hover:bg-slate-200'
              }`}>
              {day.slice(0,3)}
            </button>
          ))}
        </div>
        <button
          onClick={saveAvailability}
          disabled={availMutation.isPending}
          className="bg-teal-600 hover:bg-teal-700 disabled:opacity-60 text-white font-medium px-6 py-2 rounded-lg text-sm transition-colors"
        >
          {availMutation.isPending ? 'Saving...' : 'Save Availability'}
        </button>
      </div>
    </div>
  );
}
