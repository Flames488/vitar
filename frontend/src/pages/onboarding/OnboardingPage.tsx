/**
 * Vitar v5 - Onboarding Wizard
 * 5-step guided setup: Profile → Doctor → Availability → Notifications → Test Booking
 */

import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { z } from 'zod';
import { CheckCircle, ChevronRight, Loader2, Building2, UserPlus, Clock, Bell, Rocket } from 'lucide-react';
import { clinicsApi, doctorsApi, onboardingApi } from '@/lib/api/services';
import { useAuthStore } from '@/stores/authStore';
import { getApiError } from '@/lib/api/client';
import { toast } from 'sonner';

const STEPS = [
  { id: 1, label: 'Clinic Profile',   icon: Building2 },
  { id: 2, label: 'Add Doctor',       icon: UserPlus },
  { id: 3, label: 'Set Availability', icon: Clock },
  { id: 4, label: 'Notifications',    icon: Bell },
  { id: 5, label: 'You\'re Live!',    icon: Rocket },
];

const DAYS = ['Mon','Tue','Wed','Thu','Fri','Sat','Sun'];

export default function OnboardingPage() {
  const [step, setStep] = useState(1);
  const [doctorId, setDoctorId] = useState<string | null>(null);
  const [selectedDays, setSelectedDays] = useState([0,1,2,3,4]);
  const { refreshClinic } = useAuthStore();
  const navigate = useNavigate();

  // Step 1: Clinic profile
  const profileForm = useForm({
    resolver: zodResolver(z.object({
      phone: z.string().min(7),
      city: z.string().min(2),
      address: z.string().optional(),
    })),
  });

  // Step 2: Doctor
  const doctorForm = useForm({
    resolver: zodResolver(z.object({
      full_name: z.string().min(2),
      specialty: z.string().optional(),
      phone: z.string().optional(),
      consultation_fee: z.coerce.number().optional(),
    })),
  });

  const advance = async (nextStep: number) => {
    await onboardingApi.completeStep(nextStep - 1);
    setStep(nextStep);
  };

  const handleProfileSubmit = async (data: any) => {
    try {
      await clinicsApi.update(data);
      await advance(2);
    } catch (err) { toast.error(getApiError(err)); }
  };

  const handleDoctorSubmit = async (data: any) => {
    try {
      const doc = await doctorsApi.create(data);
      setDoctorId(doc.id);
      await advance(3);
    } catch (err) { toast.error(getApiError(err)); }
  };

  const handleAvailabilitySubmit = async () => {
    if (!doctorId) { await advance(4); return; }
    try {
      const slots = selectedDays.map(day => ({
        day_of_week: day, start_time: '09:00', end_time: '17:00',
        slot_duration_mins: 30, is_available: true,
      }));
      await doctorsApi.setAvailability(doctorId, slots);
      await advance(4);
    } catch (err) { toast.error(getApiError(err)); }
  };

  const handleNotificationsSubmit = async () => {
    await advance(5);
  };

  const handleFinish = async () => {
    try {
      await onboardingApi.completeStep(5);
      await refreshClinic();
      navigate('/dashboard');
    } catch { navigate('/dashboard'); }
  };

  const completedSteps = step - 1;

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-900 via-slate-800 to-teal-900 flex items-center justify-center p-4">
      <div className="w-full max-w-2xl">
        {/* Logo */}
        <div className="text-center mb-8">
          <div className="inline-flex items-center gap-2">
            <div className="w-10 h-10 bg-teal-500 rounded-xl flex items-center justify-center">
              <span className="text-white font-bold text-lg">V</span>
            </div>
            <span className="text-white font-bold text-2xl">Vitar</span>
          </div>
          <p className="text-slate-400 text-sm mt-2">Let's set up your clinic in under 5 minutes</p>
        </div>

        {/* Step indicators */}
        <div className="flex items-center justify-center gap-2 mb-8">
          {STEPS.map((s, i) => {
            const done = step > s.id;
            const active = step === s.id;
            return (
              <div key={s.id} className="flex items-center gap-2">
                <div className={`flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs font-medium transition-all ${
                  done    ? 'bg-teal-500 text-white' :
                  active  ? 'bg-white text-slate-900' :
                  'bg-white/10 text-slate-400'
                }`}>
                  {done ? <CheckCircle className="w-3.5 h-3.5" /> : <s.icon className="w-3.5 h-3.5" />}
                  <span className="hidden sm:inline">{s.label}</span>
                </div>
                {i < STEPS.length - 1 && (
                  <ChevronRight className="w-3.5 h-3.5 text-slate-500 flex-shrink-0" />
                )}
              </div>
            );
          })}
        </div>

        {/* Step card */}
        <div className="bg-white rounded-2xl shadow-2xl p-8">

          {/* ── Step 1: Profile ─────────────────────────────────── */}
          {step === 1 && (
            <form onSubmit={profileForm.handleSubmit(handleProfileSubmit)} className="space-y-4">
              <div>
                <h2 className="text-xl font-bold text-slate-900">Complete your clinic profile</h2>
                <p className="text-slate-500 text-sm mt-1">This info appears on your public booking page</p>
              </div>
              <div>
                <label className="block text-sm font-medium text-slate-700 mb-1">Phone number</label>
                <input {...profileForm.register('phone')} placeholder="+234 801 234 5678"
                  className="w-full border border-slate-300 rounded-lg px-3 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-teal-500" />
              </div>
              <div>
                <label className="block text-sm font-medium text-slate-700 mb-1">City</label>
                <input {...profileForm.register('city')} placeholder="Lagos"
                  className="w-full border border-slate-300 rounded-lg px-3 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-teal-500" />
              </div>
              <div>
                <label className="block text-sm font-medium text-slate-700 mb-1">Address (optional)</label>
                <input {...profileForm.register('address')} placeholder="12 Victoria Island, Lagos"
                  className="w-full border border-slate-300 rounded-lg px-3 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-teal-500" />
              </div>
              <button type="submit" disabled={profileForm.formState.isSubmitting}
                className="w-full bg-teal-600 hover:bg-teal-700 text-white font-semibold py-2.5 rounded-lg flex items-center justify-center gap-2 transition-colors">
                {profileForm.formState.isSubmitting && <Loader2 className="w-4 h-4 animate-spin" />}
                Continue
              </button>
            </form>
          )}

          {/* ── Step 2: Doctor ──────────────────────────────────── */}
          {step === 2 && (
            <form onSubmit={doctorForm.handleSubmit(handleDoctorSubmit)} className="space-y-4">
              <div>
                <h2 className="text-xl font-bold text-slate-900">Add your first doctor</h2>
                <p className="text-slate-500 text-sm mt-1">You can add more doctors later</p>
              </div>
              <div>
                <label className="block text-sm font-medium text-slate-700 mb-1">Doctor's full name</label>
                <input {...doctorForm.register('full_name')} placeholder="Dr. Amaka Obi"
                  className="w-full border border-slate-300 rounded-lg px-3 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-teal-500" />
                {doctorForm.formState.errors.full_name && (
                  <p className="text-red-500 text-xs mt-1">{doctorForm.formState.errors.full_name.message}</p>
                )}
              </div>
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-sm font-medium text-slate-700 mb-1">Specialty</label>
                  <input {...doctorForm.register('specialty')} placeholder="General Practitioner"
                    className="w-full border border-slate-300 rounded-lg px-3 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-teal-500" />
                </div>
                <div>
                  <label className="block text-sm font-medium text-slate-700 mb-1">Consultation fee</label>
                  <input {...doctorForm.register('consultation_fee')} type="number" placeholder="5000"
                    className="w-full border border-slate-300 rounded-lg px-3 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-teal-500" />
                </div>
              </div>
              <button type="submit" disabled={doctorForm.formState.isSubmitting}
                className="w-full bg-teal-600 hover:bg-teal-700 text-white font-semibold py-2.5 rounded-lg flex items-center justify-center gap-2 transition-colors">
                {doctorForm.formState.isSubmitting && <Loader2 className="w-4 h-4 animate-spin" />}
                Continue
              </button>
              <button type="button" onClick={() => advance(3)}
                className="w-full text-slate-500 text-sm hover:text-slate-700">
                Skip for now
              </button>
            </form>
          )}

          {/* ── Step 3: Availability ───────────────────────────── */}
          {step === 3 && (
            <div className="space-y-4">
              <div>
                <h2 className="text-xl font-bold text-slate-900">Set working days</h2>
                <p className="text-slate-500 text-sm mt-1">Default hours: 9am – 5pm, 30-min slots</p>
              </div>
              <div className="grid grid-cols-7 gap-2">
                {DAYS.map((day, i) => (
                  <button key={day} type="button"
                    onClick={() => setSelectedDays(prev =>
                      prev.includes(i) ? prev.filter(d => d !== i) : [...prev, i]
                    )}
                    className={`py-2.5 rounded-lg text-sm font-medium transition-colors ${
                      selectedDays.includes(i)
                        ? 'bg-teal-600 text-white'
                        : 'bg-slate-100 text-slate-600 hover:bg-slate-200'
                    }`}
                  >
                    {day}
                  </button>
                ))}
              </div>
              <p className="text-xs text-slate-400">
                {selectedDays.length} days selected · You can customise hours per doctor later
              </p>
              <button onClick={handleAvailabilitySubmit}
                className="w-full bg-teal-600 hover:bg-teal-700 text-white font-semibold py-2.5 rounded-lg transition-colors">
                Continue
              </button>
            </div>
          )}

          {/* ── Step 4: Notifications ──────────────────────────── */}
          {step === 4 && (
            <div className="space-y-4">
              <div>
                <h2 className="text-xl font-bold text-slate-900">Smart reminder setup</h2>
                <p className="text-slate-500 text-sm mt-1">
                  Vitar AI will send reminders at the right time based on each patient's risk score
                </p>
              </div>
              <div className="space-y-3">
                {[
                  { label: 'SMS Reminders', desc: 'Sent 24h before appointment', enabled: true },
                  { label: 'Email Reminders', desc: 'Confirmation + reminder emails', enabled: true },
                  { label: 'AI Smart Reminders', desc: 'Extra reminders for high-risk patients', enabled: true },
                  { label: 'WhatsApp Reminders', desc: 'Requires WhatsApp Business setup', enabled: false },
                ].map((item) => (
                  <div key={item.label} className={`flex items-center justify-between p-3 rounded-xl border ${
                    item.enabled ? 'border-teal-200 bg-teal-50' : 'border-slate-200 bg-slate-50'
                  }`}>
                    <div>
                      <p className="font-medium text-sm text-slate-900">{item.label}</p>
                      <p className="text-xs text-slate-500">{item.desc}</p>
                    </div>
                    <span className={`text-xs font-medium px-2 py-0.5 rounded-full ${
                      item.enabled ? 'bg-teal-600 text-white' : 'bg-slate-200 text-slate-500'
                    }`}>
                      {item.enabled ? 'ON' : 'OFF'}
                    </span>
                  </div>
                ))}
              </div>
              <p className="text-xs text-slate-400">Customise channels in Settings → Notifications</p>
              <button onClick={handleNotificationsSubmit}
                className="w-full bg-teal-600 hover:bg-teal-700 text-white font-semibold py-2.5 rounded-lg transition-colors">
                Continue
              </button>
            </div>
          )}

          {/* ── Step 5: Done! ──────────────────────────────────── */}
          {step === 5 && (
            <div className="text-center space-y-4">
              <div className="w-16 h-16 bg-teal-100 rounded-full flex items-center justify-center mx-auto">
                <Rocket className="w-8 h-8 text-teal-600" />
              </div>
              <div>
                <h2 className="text-2xl font-bold text-slate-900">Your clinic is live! 🎉</h2>
                <p className="text-slate-500 text-sm mt-2">
                  Your booking page and AI reminders are ready. Start adding appointments!
                </p>
              </div>
              <div className="bg-slate-50 rounded-xl p-4 text-left space-y-2">
                {[
                  'Public booking page created',
                  'AI no-show prediction active',
                  'Smart reminders configured',
                  '14-day trial started',
                ].map((item) => (
                  <div key={item} className="flex items-center gap-2 text-sm text-slate-700">
                    <CheckCircle className="w-4 h-4 text-teal-500 flex-shrink-0" />
                    {item}
                  </div>
                ))}
              </div>
              <button onClick={handleFinish}
                className="w-full bg-teal-600 hover:bg-teal-700 text-white font-bold py-3 rounded-xl text-lg transition-colors">
                Go to Dashboard →
              </button>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
