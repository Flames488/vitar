/**
 * Vitar v5 - Public Booking Page
 */
import { useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { useQuery, useMutation } from '@tanstack/react-query';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { z } from 'zod';
import { format, addDays } from 'date-fns';
import { Calendar, Clock, CheckCircle, Loader2, User, Banknote, Phone, MessageCircle, Mail } from 'lucide-react';
import { bookingApi, registrationsApi } from '@/lib/api/services';
import { getApiError } from '@/lib/api/client';
import { toast } from 'sonner';

const schema = z.object({
  full_name: z.string().min(2, 'Name required'),
  phone: z.string().min(7, 'Phone required'),
  email: z.string().email().optional().or(z.literal('')),
  reason: z.string().optional(),
});

// ── Main page ─────────────────────────────────────────────────────────────────

export default function PublicBookingPage() {
  const { slug } = useParams<{ slug: string }>();
  const [selectedDoctor, setSelectedDoctor] = useState<string | null>(null);
  const [selectedDate, setSelectedDate] = useState<string>(format(new Date(), 'yyyy-MM-dd'));
  const [selectedSlot, setSelectedSlot] = useState<string | null>(null);
  const [booked, setBooked] = useState<any>(null);

  const { data: clinicData, isLoading: clinicLoading, isError: clinicError } = useQuery({
    queryKey: ['booking-clinic', slug],
    queryFn: () => bookingApi.getClinic(slug!),
    enabled: !!slug,
    retry: 1,
  });

  const { data: slotsData, isLoading: slotsLoading, isError: slotsError } = useQuery({
    queryKey: ['available-slots', slug, selectedDoctor, selectedDate],
    queryFn: () => bookingApi.getAvailableSlots(slug!, selectedDoctor!, selectedDate),
    enabled: !!slug && !!selectedDoctor && !!selectedDate,
    retry: 1,
  });

  const { register, handleSubmit, formState: { errors, isSubmitting } } = useForm({
    resolver: zodResolver(schema),
  });

  const [redirecting, setRedirecting] = useState(false);

  const bookMutation = useMutation({
    mutationFn: (formData: any) => bookingApi.book(slug!, {
      ...formData,
      email: formData.email || undefined,
      doctor_id: selectedDoctor,
      // Slot times are clinic-local wall-clock (WAT); convert to a UTC ISO
      // string so the backend's naive-UTC normalization doesn't store the
      // local time as-is (which would be off by the clinic's UTC offset).
      scheduled_at: new Date(`${selectedDate}T${selectedSlot}:00`).toISOString(),
    }),
    onSuccess: (data) => {
      // If payment is required, the appointment is only tentatively held
      // (AWAITING_PAYMENT) until Paystack confirms it via webhook. Never show
      // a "confirmed" screen or accept payment as done until that happens —
      // send the patient straight to the real Paystack checkout.
      if (data.payment_required && data.payment_url) {
        setRedirecting(true);
        window.location.href = data.payment_url;
        return;
      }
      setBooked(data);
    },
    onError: (err) => toast.error(getApiError(err)),
  });

  if (clinicLoading) return (
    <div className="min-h-screen bg-slate-50 flex items-center justify-center">
      <Loader2 className="w-8 h-8 text-teal-600 animate-spin" />
    </div>
  );

  if (clinicError || !clinicData?.clinic) return (
    <div className="min-h-screen bg-slate-50 flex items-center justify-center px-4">
      <div className="max-w-sm text-center space-y-2">
        <h1 className="text-xl font-bold text-slate-900">Booking page not found</h1>
        <p className="text-slate-500 text-sm">
          This link may be mistyped, or the clinic has disabled online booking. Please check the link
          or contact the clinic directly.
        </p>
      </div>
    </div>
  );

  const clinic = clinicData?.clinic;
  const doctors = clinicData?.doctors ?? [];
  // Render every generated slot (free, booked, and past), not just free
  // ones — the empty state still keys off "zero free slots", not "zero
  // slots returned" (a fully-booked day still has slots, just none free).
  const allSlots = slotsData?.slots ?? [];
  const freeSlotsCount = allSlots.filter((s: any) => s.status === 'free').length;

  // Date options: next 14 days
  const dateOptions = Array.from({ length: 14 }, (_, i) => {
    const d = addDays(new Date(), i);
    return { value: format(d, 'yyyy-MM-dd'), label: format(d, i === 0 ? "'Today'" : i === 1 ? "'Tomorrow'" : 'EEE MMM d') };
  });

  if (booked) return (
    <div className="min-h-screen bg-slate-50">
      {/* Header */}
      <div className="bg-teal-700 text-white py-8 px-4">
        <div className="max-w-2xl mx-auto text-center">
          <h1 className="text-2xl font-bold">{clinic?.name}</h1>
        </div>
      </div>

      <div className="max-w-lg mx-auto px-4 py-8 space-y-4">
        {/* Confirmation card */}
        <div className="bg-white rounded-2xl shadow-sm border border-slate-200 p-8 text-center space-y-3">
          <div className="w-14 h-14 bg-teal-100 rounded-full flex items-center justify-center mx-auto">
            <CheckCircle className="w-7 h-7 text-teal-600" />
          </div>
          <h2 className="text-xl font-bold text-slate-900">Appointment Confirmed!</h2>
          <p className="text-slate-500 text-sm">
            You're booked with <strong>{clinic?.name}</strong> on{' '}
            <strong>{format(new Date(`${selectedDate}T${selectedSlot}`), "EEEE, MMMM d 'at' h:mm a")}</strong>
          </p>
          <p className="text-slate-400 text-xs">A confirmation will be sent to your phone/email.</p>
        </div>

        {booked.appointment_id && booked.confirmation_token && (
          <DoctorContactSection
            doctorName={doctors.find((d: any) => d.id === selectedDoctor)?.full_name}
            appointmentId={booked.appointment_id}
            token={booked.confirmation_token}
          />
        )}

        {slug && clinic?.id && booked.patient_id && (
          <RegistrationPrompt
            slug={slug}
            clinicId={clinic.id}
            patientId={booked.patient_id}
            appointmentId={booked.appointment_id}
          />
        )}
      </div>
    </div>
  );

  return (
    <div className="min-h-screen bg-slate-50">
      {/* Header */}
      <div className="bg-teal-700 text-white py-10 px-4">
        <div className="max-w-2xl mx-auto text-center">
          <h1 className="text-3xl font-bold">{clinic?.name}</h1>
          {clinic?.address && <p className="text-teal-200 mt-2">{clinic.address}</p>}
          {clinic?.phone && <p className="text-teal-200 text-sm">{clinic.phone}</p>}
        </div>
      </div>

      <div className="max-w-2xl mx-auto px-4 py-8 space-y-6">
        {/* Step 1: Doctor */}
        <div className="bg-white rounded-xl border border-slate-200 p-6">
          <h2 className="font-semibold text-slate-900 mb-4 flex items-center gap-2">
            <User className="w-4 h-4 text-teal-600" /> Select Doctor
          </h2>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            {doctors.map((d: any) => (
              <button key={d.id} onClick={() => setSelectedDoctor(d.id)}
                className={`text-left p-3 rounded-xl border-2 transition-all ${selectedDoctor === d.id ? 'border-teal-500 bg-teal-50' : 'border-slate-200 hover:border-teal-300'}`}>
                <p className="font-medium text-slate-900">Dr. {d.full_name}</p>
                <p className="text-slate-500 text-sm">{d.specialty}</p>
                {d.consultation_fee > 0 && (
                  <p className="text-teal-600 text-sm font-medium mt-1">
                    ₦{d.consultation_fee.toLocaleString()}
                  </p>
                )}
              </button>
            ))}
          </div>
        </div>

        {/* Step 2: Date */}
        {selectedDoctor && (
          <div className="bg-white rounded-xl border border-slate-200 p-6">
            <h2 className="font-semibold text-slate-900 mb-4 flex items-center gap-2">
              <Calendar className="w-4 h-4 text-teal-600" /> Select Date
            </h2>
            <div className="flex gap-2 overflow-x-auto pb-2">
              {dateOptions.map(({ value, label }) => (
                <button key={value} onClick={() => { setSelectedDate(value); setSelectedSlot(null); }}
                  className={`flex-shrink-0 px-4 py-2.5 rounded-xl border-2 text-sm font-medium transition-all ${selectedDate === value ? 'border-teal-500 bg-teal-50 text-teal-700' : 'border-slate-200 text-slate-600 hover:border-teal-300'}`}>
                  {label}
                </button>
              ))}
            </div>
          </div>
        )}

        {/* Step 3: Time Slot */}
        {selectedDoctor && selectedDate && (
          <div className="bg-white rounded-xl border border-slate-200 p-6">
            <h2 className="font-semibold text-slate-900 mb-4 flex items-center gap-2">
              <Clock className="w-4 h-4 text-teal-600" /> Select Time
            </h2>
            {slotsLoading ? (
              <div className="text-center py-4 text-slate-400 text-sm">Loading slots...</div>
            ) : slotsError ? (
              <p className="text-red-500 text-sm text-center py-4">
                Couldn't load availability. Please try a different date or refresh the page.
              </p>
            ) : freeSlotsCount === 0 ? (
              <p className="text-slate-500 text-sm text-center py-4">No available slots on this date</p>
            ) : (
              <div className="grid grid-cols-4 sm:grid-cols-6 gap-2">
                {allSlots.map((slot: any) => {
                  const isFree = slot.status === 'free';
                  const isBooked = slot.status === 'booked';
                  return (
                    <button
                      key={slot.time}
                      disabled={!isFree}
                      onClick={() => isFree && setSelectedSlot(slot.time)}
                      title={isBooked ? 'Already booked' : !isFree ? 'No longer available' : undefined}
                      className={`py-2 rounded-lg text-sm font-medium transition-all border flex flex-col items-center gap-0.5 ${
                        selectedSlot === slot.time
                          ? 'bg-teal-600 text-white border-teal-600'
                          : isBooked
                            ? 'bg-red-50 text-red-400 border-red-100 cursor-not-allowed'
                            : !isFree
                              ? 'bg-slate-50 text-slate-300 border-slate-100 cursor-not-allowed'
                              : 'border-slate-200 text-slate-700 hover:border-teal-400'
                      }`}
                    >
                      <span>{slot.time}</span>
                      {isBooked && <span className="text-[10px] font-normal">✕ Booked</span>}
                    </button>
                  );
                })}
              </div>
            )}
          </div>
        )}

        {/* Step 4: Patient Details */}
        {selectedSlot && (
          <div className="bg-white rounded-xl border border-slate-200 p-6">
            <h2 className="font-semibold text-slate-900 mb-4">Your Details</h2>
            <form onSubmit={handleSubmit(d => { if (!bookMutation.isPending) bookMutation.mutate(d) })} className="space-y-3">
              <div>
                <label className="block text-sm font-medium text-slate-700 mb-1">Full name *</label>
                <input {...register('full_name')} placeholder="Your full name"
                  className="w-full border border-slate-300 rounded-lg px-3 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-teal-500" />
                {errors.full_name && <p className="text-red-500 text-xs mt-1">{errors.full_name.message}</p>}
              </div>
              <div>
                <label className="block text-sm font-medium text-slate-700 mb-1">Phone number *</label>
                <input {...register('phone')} type="tel" placeholder="+234..."
                  className="w-full border border-slate-300 rounded-lg px-3 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-teal-500" />
                {errors.phone && <p className="text-red-500 text-xs mt-1">{errors.phone.message}</p>}
              </div>
              <div>
                <label className="block text-sm font-medium text-slate-700 mb-1">Email (optional)</label>
                <input {...register('email')} type="email" placeholder="you@email.com"
                  className="w-full border border-slate-300 rounded-lg px-3 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-teal-500" />
              </div>
              <div>
                <label className="block text-sm font-medium text-slate-700 mb-1">Reason for visit (optional)</label>
                <input {...register('reason')} placeholder="e.g. General checkup"
                  className="w-full border border-slate-300 rounded-lg px-3 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-teal-500" />
              </div>

              <div className="bg-slate-50 rounded-lg p-3 text-sm text-slate-700">
                <p className="font-medium">Booking Summary</p>
                <p className="mt-1 text-slate-500">{format(new Date(`${selectedDate}T${selectedSlot}`), "EEEE, MMMM d, yyyy 'at' h:mm a")}</p>
                {clinic?.patient_payment_enabled && (
                  <p className="mt-1 text-teal-700 text-xs font-medium flex items-center gap-1">
                    <Banknote className="w-3.5 h-3.5" /> You'll be redirected to secure payment (Paystack) after booking
                  </p>
                )}
              </div>

              <button type="submit" disabled={isSubmitting || bookMutation.isPending || redirecting}
                className="w-full bg-teal-600 hover:bg-teal-700 disabled:opacity-60 text-white font-semibold py-3 rounded-xl transition-colors flex items-center justify-center gap-2">
                {(isSubmitting || bookMutation.isPending || redirecting) && <Loader2 className="w-4 h-4 animate-spin" />}
                {redirecting ? 'Redirecting to payment…' : 'Confirm Appointment'}
              </button>
            </form>
          </div>
        )}
      </div>
    </div>
  );
}

// ── Post-booking Doctor Contact (Phase B redesign) ──────────────────────────
// Moved here from the pre-booking doctor-selection card. No patient login
// exists in Vitar, so confirmation_token (already in the booking response,
// same field /confirm/{token} uses) proves this is genuinely the patient's
// own appointment — server-side ownership + plan + doctor-opt-in checks all
// happen in get_appointment_doctor_contact. If any check fails (wrong plan,
// contact disabled, etc.) the endpoint 404s/402s and this silently renders
// nothing — a patient has no actionable use for "your clinic isn't on the
// right plan," so there's no separate prompt for that case, just no section.

function DoctorContactSection({ doctorName, appointmentId, token }: {
  doctorName?: string; appointmentId: string; token: string;
}) {
  const { data: contact } = useQuery({
    queryKey: ['appointment-doctor-contact', appointmentId],
    queryFn: () => bookingApi.getDoctorContact(appointmentId, token),
    retry: false,
  });

  if (!contact || (!contact.talk_with_doctor_url && !contact.call_url && !contact.email)) return null;

  return (
    <div className="bg-white rounded-2xl shadow-sm border border-slate-200 p-6 space-y-3">
      <p className="text-sm text-slate-700">
        Have a question before your visit? Reach {doctorName ? `Dr. ${doctorName}` : 'your doctor'} directly.
      </p>
      <div className="space-y-1.5 text-sm text-slate-600">
        {contact.phone && (
          <div className="flex items-center gap-1.5">
            <Phone className="w-4 h-4 text-slate-400" /> {contact.phone}
          </div>
        )}
        {contact.email && (
          <div className="flex items-center gap-1.5">
            <Mail className="w-4 h-4 text-slate-400" /> {contact.email}
          </div>
        )}
      </div>
      <div className="flex flex-wrap gap-2">
        {contact.talk_with_doctor_url && (
          <a
            href={contact.talk_with_doctor_url}
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex items-center gap-1.5 text-sm font-medium text-white bg-green-600 hover:bg-green-700 px-3 py-2 rounded-lg transition-colors"
          >
            <MessageCircle className="w-4 h-4" /> Chat on WhatsApp
          </a>
        )}
        {contact.call_url && (
          <a
            href={contact.call_url}
            className="inline-flex items-center gap-1.5 text-sm font-medium text-white bg-teal-600 hover:bg-teal-700 px-3 py-2 rounded-lg transition-colors"
          >
            <Phone className="w-4 h-4" /> Call Doctor
          </a>
        )}
      </div>
    </div>
  );
}

// ── Post-booking eRegistration prompt (Phase 3) ─────────────────────────────
// Additive to the existing confirmation screen — the confirmation card above
// always renders immediately; this fetches its own status/eligibility and
// only appears once both resolve, so it never delays the confirmation itself.

function RegistrationPrompt({
  slug, clinicId, patientId, appointmentId,
}: { slug: string; clinicId: string; patientId: string; appointmentId: string }) {
  const navigate = useNavigate();
  const dismissKey = `eregistration_dismissed_${appointmentId}`;
  const [dismissed, setDismissed] = useState(() => localStorage.getItem(dismissKey) === 'true');

  const { data: status } = useQuery({
    queryKey: ['registration-status', clinicId, patientId],
    queryFn: () => registrationsApi.getStatus({ clinic_id: clinicId, patient_id: patientId }),
    enabled: !dismissed,
  });
  const { data: eligibility } = useQuery({
    queryKey: ['registration-eligibility', clinicId],
    queryFn: () => registrationsApi.getEligibility(clinicId),
    enabled: !dismissed,
  });

  if (dismissed || !status || !eligibility) return null;
  if (status.registered) return null; // already registered — no prompt, no change to normal flow
  if (!eligibility.available) return null; // trial expired / no active subscription — behave as if this feature doesn't exist

  return (
    <div className="bg-white rounded-2xl shadow-sm border border-slate-200 p-6 space-y-3">
      <p className="text-sm text-slate-700">
        Completing your registration before your visit helps reduce waiting time at the clinic.
      </p>
      <div className="flex gap-2">
        <button
          onClick={() => navigate(`/book/${slug}/register?clinic_id=${clinicId}&patient_id=${patientId}`)}
          className="flex-1 bg-teal-600 hover:bg-teal-700 text-white font-semibold text-sm py-2.5 rounded-xl transition-colors"
        >
          Complete Registration
        </button>
        <button
          onClick={() => { localStorage.setItem(dismissKey, 'true'); setDismissed(true); }}
          className="flex-1 border border-slate-200 text-slate-600 hover:bg-slate-50 font-medium text-sm py-2.5 rounded-xl transition-colors"
        >
          Do It Later
        </button>
      </div>
    </div>
  );
}
