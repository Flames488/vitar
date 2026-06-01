/**
 * Vitar v5 - New Appointment Page
 */

import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { z } from 'zod';
import { useNavigate } from 'react-router-dom';
import { useQuery, useMutation } from '@tanstack/react-query';
import { Loader2 } from 'lucide-react';
import { doctorsApi, patientsApi, appointmentsApi } from '@/lib/api/services';
import { getApiError } from '@/lib/api/client';
import { toast } from 'sonner';

const schema = z.object({
  doctor_id: z.string().min(1, 'Select a doctor'),
  patient_id: z.string().min(1, 'Select a patient'),
  scheduled_at: z.string().min(1, 'Date/time required'),
  duration_mins: z.coerce.number().min(15).max(240).default(30),
  reason: z.string().optional(),
  notes: z.string().optional(),
  payment_required: z.boolean().default(false),
  payment_amount: z.coerce.number().optional(),
});

export default function NewAppointmentPage() {
  const navigate = useNavigate();
  const { data: doctorsData } = useQuery({ queryKey: ['doctors'], queryFn: doctorsApi.list });
  const { data: patientsData } = useQuery({ queryKey: ['patients'], queryFn: () => patientsApi.list({ limit: 100 }) });

  const { register, handleSubmit, watch, formState: { errors, isSubmitting } } = useForm({
    resolver: zodResolver(schema),
    defaultValues: { duration_mins: 30, payment_required: false },
  });

  const paymentRequired = watch('payment_required');

  const createMutation = useMutation({
    mutationFn: (data: any) => appointmentsApi.create({
      ...data,
      scheduled_at: new Date(data.scheduled_at).toISOString(),
    }),
    onSuccess: (apt) => {
      toast.success('Appointment created');
      navigate(`/appointments/${apt.id}`);
    },
    onError: (err) => toast.error(getApiError(err)),
  });

  return (
    <div className="p-6 max-w-2xl mx-auto">
      <h1 className="text-2xl font-bold text-slate-900 mb-6">New Appointment</h1>
      <form onSubmit={handleSubmit(d => createMutation.mutate(d))} className="space-y-4 bg-white rounded-xl border border-slate-200 p-6">
        <div>
          <label className="block text-sm font-medium text-slate-700 mb-1">Doctor</label>
          <select {...register('doctor_id')} className="w-full border border-slate-300 rounded-lg px-3 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-teal-500 bg-white">
            <option value="">Select doctor...</option>
            {(doctorsData?.doctors ?? []).map((d: any) => (
              <option key={d.id} value={d.id}>Dr. {d.full_name} {d.specialty ? `· ${d.specialty}` : ''}</option>
            ))}
          </select>
          {errors.doctor_id && <p className="text-red-500 text-xs mt-1">{errors.doctor_id.message}</p>}
        </div>

        <div>
          <label className="block text-sm font-medium text-slate-700 mb-1">Patient</label>
          <select {...register('patient_id')} className="w-full border border-slate-300 rounded-lg px-3 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-teal-500 bg-white">
            <option value="">Select patient...</option>
            {(patientsData?.items ?? []).map((p: any) => (
              <option key={p.id} value={p.id}>{p.full_name} · {p.phone}</option>
            ))}
          </select>
          {errors.patient_id && <p className="text-red-500 text-xs mt-1">{errors.patient_id.message}</p>}
        </div>

        <div className="grid grid-cols-2 gap-3">
          <div>
            <label className="block text-sm font-medium text-slate-700 mb-1">Date & Time</label>
            <input {...register('scheduled_at')} type="datetime-local"
              className="w-full border border-slate-300 rounded-lg px-3 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-teal-500" />
            {errors.scheduled_at && <p className="text-red-500 text-xs mt-1">{errors.scheduled_at.message}</p>}
          </div>
          <div>
            <label className="block text-sm font-medium text-slate-700 mb-1">Duration (mins)</label>
            <select {...register('duration_mins')} className="w-full border border-slate-300 rounded-lg px-3 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-teal-500 bg-white">
              {[15,20,30,45,60,90,120].map(m => <option key={m} value={m}>{m} mins</option>)}
            </select>
          </div>
        </div>

        <div>
          <label className="block text-sm font-medium text-slate-700 mb-1">Reason (optional)</label>
          <input {...register('reason')} placeholder="e.g. Follow-up consultation"
            className="w-full border border-slate-300 rounded-lg px-3 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-teal-500" />
        </div>

        <div>
          <label className="block text-sm font-medium text-slate-700 mb-1">Notes (optional)</label>
          <textarea {...register('notes')} rows={2} placeholder="Internal notes..."
            className="w-full border border-slate-300 rounded-lg px-3 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-teal-500 resize-none" />
        </div>

        <div className="flex items-center gap-3">
          <input {...register('payment_required')} type="checkbox" id="payment_required"
            className="w-4 h-4 text-teal-600 rounded" />
          <label htmlFor="payment_required" className="text-sm text-slate-700">Require patient payment</label>
        </div>

        {paymentRequired && (
          <div>
            <label className="block text-sm font-medium text-slate-700 mb-1">Payment amount</label>
            <input {...register('payment_amount')} type="number" placeholder="5000"
              className="w-full border border-slate-300 rounded-lg px-3 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-teal-500" />
          </div>
        )}

        <div className="flex gap-3 pt-2">
          <button type="button" onClick={() => navigate(-1)}
            className="flex-1 border border-slate-300 text-slate-700 hover:bg-slate-50 font-medium py-2.5 rounded-lg text-sm transition-colors">
            Cancel
          </button>
          <button type="submit" disabled={isSubmitting}
            className="flex-1 bg-teal-600 hover:bg-teal-700 disabled:opacity-60 text-white font-semibold py-2.5 rounded-lg text-sm transition-colors flex items-center justify-center gap-2">
            {isSubmitting && <Loader2 className="w-4 h-4 animate-spin" />}
            Create Appointment
          </button>
        </div>
      </form>
    </div>
  );
}
