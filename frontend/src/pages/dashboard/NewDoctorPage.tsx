/**
 * Vitar v5 - New Doctor Page
 */
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { z } from 'zod';
import { useNavigate } from 'react-router-dom';
import { useMutation } from '@tanstack/react-query';
import { Loader2 } from 'lucide-react';
import { doctorsApi } from '@/lib/api/services';
import { getApiError } from '@/lib/api/client';
import { toast } from 'sonner';

const schema = z.object({
  full_name: z.string().min(2),
  specialty: z.string().optional(),
  email: z.string().email().optional().or(z.literal('')),
  phone: z.string().optional(),
  bio: z.string().optional(),
  consultation_fee: z.coerce.number().min(0).optional(),
});

export default function NewDoctorPage() {
  const navigate = useNavigate();
  const { register, handleSubmit, formState: { errors, isSubmitting } } = useForm({ resolver: zodResolver(schema) });

  const createMutation = useMutation({
    mutationFn: doctorsApi.create,
    onSuccess: (d) => { toast.success('Doctor added'); navigate(`/doctors/${d.id}`); },
    onError: (err) => toast.error(getApiError(err)),
  });

  return (
    <div className="p-6 max-w-2xl mx-auto">
      <h1 className="text-2xl font-bold text-slate-900 mb-6">Add New Doctor</h1>
      <form onSubmit={handleSubmit(d => createMutation.mutate(d))} className="bg-white rounded-xl border border-slate-200 p-6 space-y-4">
        <div>
          <label className="block text-sm font-medium text-slate-700 mb-1">Full name *</label>
          <input {...register('full_name')} placeholder="Dr. Amaka Obi"
            className="w-full border border-slate-300 rounded-lg px-3 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-teal-500" />
          {errors.full_name && <p className="text-red-500 text-xs mt-1">{errors.full_name.message}</p>}
        </div>
        <div className="grid grid-cols-2 gap-3">
          <div>
            <label className="block text-sm font-medium text-slate-700 mb-1">Specialty</label>
            <input {...register('specialty')} placeholder="General Practitioner"
              className="w-full border border-slate-300 rounded-lg px-3 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-teal-500" />
          </div>
          <div>
            <label className="block text-sm font-medium text-slate-700 mb-1">Consultation fee</label>
            <input {...register('consultation_fee')} type="number" placeholder="5000"
              className="w-full border border-slate-300 rounded-lg px-3 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-teal-500" />
          </div>
        </div>
        <div className="grid grid-cols-2 gap-3">
          <div>
            <label className="block text-sm font-medium text-slate-700 mb-1">Email</label>
            <input {...register('email')} type="email" placeholder="doctor@clinic.com"
              className="w-full border border-slate-300 rounded-lg px-3 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-teal-500" />
          </div>
          <div>
            <label className="block text-sm font-medium text-slate-700 mb-1">Phone</label>
            <input {...register('phone')} placeholder="+2348012345678"
              className="w-full border border-slate-300 rounded-lg px-3 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-teal-500" />
          </div>
        </div>
        <div>
          <label className="block text-sm font-medium text-slate-700 mb-1">Bio</label>
          <textarea {...register('bio')} rows={3} placeholder="Brief professional bio..."
            className="w-full border border-slate-300 rounded-lg px-3 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-teal-500 resize-none" />
        </div>
        <div className="flex gap-3 pt-2">
          <button type="button" onClick={() => navigate(-1)}
            className="flex-1 border border-slate-300 text-slate-700 hover:bg-slate-50 font-medium py-2.5 rounded-lg text-sm transition-colors">
            Cancel
          </button>
          <button type="submit" disabled={isSubmitting}
            className="flex-1 bg-teal-600 hover:bg-teal-700 disabled:opacity-60 text-white font-semibold py-2.5 rounded-lg text-sm transition-colors flex items-center justify-center gap-2">
            {isSubmitting && <Loader2 className="w-4 h-4 animate-spin" />}
            Add Doctor
          </button>
        </div>
      </form>
    </div>
  );
}
