/**
 * Vitar v5 - Register Page
 * Creates clinic + owner in one step, auto-starts 30-day trial
 */

import { useState } from 'react';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { z } from 'zod';
import { Link, useNavigate } from 'react-router-dom';
import { Eye, EyeOff, Loader2, CheckCircle } from 'lucide-react';
import { useAuthStore } from '@/stores/authStore';
import { getApiError } from '@/lib/api/client';
import { toast } from 'sonner';

const schema = z.object({
  full_name:   z.string().min(2, 'Full name required'),
  clinic_name: z.string().min(2, 'Clinic name required'),
  email:       z.string().email('Invalid email'),
  phone:       z.string().min(7, 'Phone number required'),
  city:        z.string().min(2, 'City required'),
  country:     z.string().min(2, 'Country required'),
  password:    z.string().min(8, 'At least 8 characters'),
});

type FormData = z.infer<typeof schema>;

const COUNTRIES = [
  { code: 'NG', label: 'Nigeria' },
  { code: 'GH', label: 'Ghana' },
  { code: 'KE', label: 'Kenya' },
  { code: 'ZA', label: 'South Africa' },
  { code: 'US', label: 'United States' },
  { code: 'GB', label: 'United Kingdom' },
  { code: 'CA', label: 'Canada' },
  { code: 'AU', label: 'Australia' },
  { code: 'OTHER', label: 'Other' },
];

const PERKS = [
  '30-day free trial, no credit card',
  'AI no-show prediction',
  'SMS, WhatsApp & Email reminders',
  'Public booking page',
];

export default function RegisterPage() {
  const { register: signup } = useAuthStore();
  const navigate = useNavigate();
  const [showPw, setShowPw] = useState(false);

  const { register, handleSubmit, formState: { errors, isSubmitting } } = useForm<FormData>({
    resolver: zodResolver(schema),
    defaultValues: { country: 'NG' },
  });

  const onSubmit = async (data: FormData) => {
    try {
      await signup(data);
      navigate('/onboarding');
    } catch (err) {
      toast.error(getApiError(err));
    }
  };

  return (
    <>
      <div className="mb-5">
        <h2 className="text-2xl font-bold text-slate-900">Create your clinic</h2>
        <p className="text-slate-500 text-sm mt-1">Start your 30-day free trial — no card required</p>
        <div className="mt-3 grid grid-cols-2 gap-1.5">
          {PERKS.map((p) => (
            <div key={p} className="flex items-center gap-1.5 text-xs text-slate-600">
              <CheckCircle className="w-3.5 h-3.5 text-teal-500 flex-shrink-0" />
              {p}
            </div>
          ))}
        </div>
      </div>

      <form onSubmit={handleSubmit(onSubmit)} className="space-y-3">
        <div className="grid grid-cols-2 gap-3">
          <div>
            <label className="block text-xs font-medium text-slate-700 mb-1">Your name</label>
            <input
              {...register('full_name')}
              placeholder="Dr. Amaka Obi"
              className="w-full border border-slate-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-teal-500"
            />
            {errors.full_name && <p className="text-red-500 text-xs mt-1">{errors.full_name.message}</p>}
          </div>
          <div>
            <label className="block text-xs font-medium text-slate-700 mb-1">Clinic name</label>
            <input
              {...register('clinic_name')}
              placeholder="HealthPlus Clinic"
              className="w-full border border-slate-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-teal-500"
            />
            {errors.clinic_name && <p className="text-red-500 text-xs mt-1">{errors.clinic_name.message}</p>}
          </div>
        </div>

        <div>
          <label className="block text-xs font-medium text-slate-700 mb-1">Work email</label>
          <input
            {...register('email')}
            type="email"
            placeholder="you@clinic.com"
            className="w-full border border-slate-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-teal-500"
          />
          {errors.email && <p className="text-red-500 text-xs mt-1">{errors.email.message}</p>}
        </div>

        <div className="grid grid-cols-2 gap-3">
          <div>
            <label className="block text-xs font-medium text-slate-700 mb-1">Phone</label>
            <input
              {...register('phone')}
              type="tel"
              placeholder="+2348012345678"
              className="w-full border border-slate-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-teal-500"
            />
            {errors.phone && <p className="text-red-500 text-xs mt-1">{errors.phone.message}</p>}
          </div>
          <div>
            <label className="block text-xs font-medium text-slate-700 mb-1">City</label>
            <input
              {...register('city')}
              placeholder="Lagos"
              className="w-full border border-slate-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-teal-500"
            />
            {errors.city && <p className="text-red-500 text-xs mt-1">{errors.city.message}</p>}
          </div>
        </div>

        <div>
          <label className="block text-xs font-medium text-slate-700 mb-1">Country</label>
          <select
            {...register('country')}
            className="w-full border border-slate-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-teal-500 bg-white"
          >
            {COUNTRIES.map((c) => (
              <option key={c.code} value={c.code}>{c.label}</option>
            ))}
          </select>
          {errors.country && <p className="text-red-500 text-xs mt-1">{errors.country.message}</p>}
        </div>

        <div>
          <label className="block text-xs font-medium text-slate-700 mb-1">Password</label>
          <div className="relative">
            <input
              {...register('password')}
              type={showPw ? 'text' : 'password'}
              placeholder="Minimum 8 characters"
              className="w-full border border-slate-300 rounded-lg px-3 py-2 pr-10 text-sm focus:outline-none focus:ring-2 focus:ring-teal-500"
            />
            <button
              type="button"
              onClick={() => setShowPw(v => !v)}
              className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-400"
            >
              {showPw ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
            </button>
          </div>
          {errors.password && <p className="text-red-500 text-xs mt-1">{errors.password.message}</p>}
        </div>

        <button
          type="submit"
          disabled={isSubmitting}
          className="w-full bg-teal-600 hover:bg-teal-700 disabled:opacity-60 text-white font-semibold py-2.5 rounded-lg transition-colors flex items-center justify-center gap-2 mt-2"
        >
          {isSubmitting && <Loader2 className="w-4 h-4 animate-spin" />}
          Create clinic & start trial
        </button>

        <p className="text-center text-xs text-slate-400">
          By registering you agree to our Terms of Service
        </p>
      </form>

      <p className="text-center text-sm text-slate-500 mt-4">
        Already have an account?{' '}
        <Link to="/login" className="text-teal-600 font-medium hover:underline">Sign in</Link>
      </p>
    </>
  );
}
