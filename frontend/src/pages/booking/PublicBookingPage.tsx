/**
 * Vitar v5 - Public Booking Page
 */
import { useState } from 'react';
import { useParams } from 'react-router-dom';
import { useQuery, useMutation } from '@tanstack/react-query';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { z } from 'zod';
import { format, addDays } from 'date-fns';
import { Calendar, Clock, CheckCircle, Loader2, User, Banknote, Copy, Check } from 'lucide-react';
import { bookingApi, doctorsApi } from '@/lib/api/services';
import { getApiError } from '@/lib/api/client';
import { toast } from 'sonner';

const schema = z.object({
  full_name: z.string().min(2, 'Name required'),
  phone: z.string().min(7, 'Phone required'),
  email: z.string().email().optional().or(z.literal('')),
  reason: z.string().optional(),
});

// ── Bank Transfer instructions panel ─────────────────────────────────────────

function BankTransferCard({
  clinicName,
  bankName,
  accountNumber,
  amount,
}: {
  clinicName: string;
  bankName: string;
  accountNumber: string;
  amount: number;
}) {
  const [copiedAccount, setCopiedAccount] = useState(false);

  function copyAccount() {
    navigator.clipboard.writeText(accountNumber).then(() => {
      setCopiedAccount(true);
      setTimeout(() => setCopiedAccount(false), 2000);
    });
  }

  return (
    <div className="bg-teal-50 border border-teal-200 rounded-xl p-5 space-y-4">
      <div className="flex items-center gap-2">
        <Banknote className="w-5 h-5 text-teal-700" />
        <h3 className="font-semibold text-teal-900">Payment Required</h3>
      </div>

      <p className="text-sm text-teal-800">
        Please transfer your consultation fee to the account below before your appointment.
        Use your <strong>name</strong> as the payment description so it can be confirmed.
      </p>

      <div className="bg-white rounded-lg border border-teal-200 divide-y divide-teal-100">
        <div className="flex justify-between px-4 py-3 text-sm">
          <span className="text-slate-500">Bank</span>
          <span className="font-medium text-slate-900">{bankName}</span>
        </div>
        <div className="flex justify-between items-center px-4 py-3 text-sm">
          <span className="text-slate-500">Account number</span>
          <div className="flex items-center gap-2">
            <span className="font-mono font-semibold text-slate-900 tracking-wider">{accountNumber}</span>
            <button
              onClick={copyAccount}
              className="text-teal-600 hover:text-teal-800 transition-colors"
              title="Copy account number"
            >
              {copiedAccount ? <Check className="w-4 h-4" /> : <Copy className="w-4 h-4" />}
            </button>
          </div>
        </div>
        <div className="flex justify-between px-4 py-3 text-sm">
          <span className="text-slate-500">Account name</span>
          <span className="font-medium text-slate-900">{clinicName}</span>
        </div>
        {amount > 0 && (
          <div className="flex justify-between px-4 py-3 text-sm">
            <span className="text-slate-500">Amount</span>
            <span className="font-bold text-teal-700 text-base">₦{amount.toLocaleString()}</span>
          </div>
        )}
      </div>

      <p className="text-xs text-teal-700">
        Your appointment is confirmed. Payment can be made up to 30 minutes before your visit.
      </p>
    </div>
  );
}

// ── Main page ─────────────────────────────────────────────────────────────────

export default function PublicBookingPage() {
  const { slug } = useParams<{ slug: string }>();
  const [selectedDoctor, setSelectedDoctor] = useState<string | null>(null);
  const [selectedDate, setSelectedDate] = useState<string>(format(new Date(), 'yyyy-MM-dd'));
  const [selectedSlot, setSelectedSlot] = useState<string | null>(null);
  const [booked, setBooked] = useState<any>(null);
  const [bookedDoctor, setBookedDoctor] = useState<any>(null);

  const { data: clinicData, isLoading: clinicLoading } = useQuery({
    queryKey: ['public-clinic', slug],
    queryFn: () => bookingApi.getClinic(slug!),
    enabled: !!slug,
  });

  const { data: slotsData, isLoading: slotsLoading } = useQuery({
    queryKey: ['available-slots', selectedDoctor, selectedDate],
    queryFn: () => doctorsApi.getAvailableSlots(selectedDoctor!, selectedDate),
    enabled: !!selectedDoctor && !!selectedDate,
  });

  const { register, handleSubmit, formState: { errors, isSubmitting } } = useForm({
    resolver: zodResolver(schema),
  });

  const bookMutation = useMutation({
    mutationFn: (formData: any) => bookingApi.book(slug!, {
      ...formData,
      doctor_id: selectedDoctor,
      scheduled_at: `${selectedDate}T${selectedSlot}:00`,
    }),
    onSuccess: (data) => {
      setBooked(data);
      const doctors = clinicData?.doctors ?? [];
      setBookedDoctor(doctors.find((d: any) => d.id === selectedDoctor) ?? null);
    },
    onError: (err) => toast.error(getApiError(err)),
  });

  if (clinicLoading) return (
    <div className="min-h-screen bg-slate-50 flex items-center justify-center">
      <Loader2 className="w-8 h-8 text-teal-600 animate-spin" />
    </div>
  );

  const clinic = clinicData?.clinic;
  const doctors = clinicData?.doctors ?? [];
  const availableSlots = (slotsData?.slots ?? []).filter((s: any) => s.available);

  // Date options: next 14 days
  const dateOptions = Array.from({ length: 14 }, (_, i) => {
    const d = addDays(new Date(), i);
    return { value: format(d, 'yyyy-MM-dd'), label: format(d, i === 0 ? "'Today'" : i === 1 ? "'Tomorrow'" : 'EEE MMM d') };
  });

  // Determine payment amount: prefer doctor fee, then fall back to booked response amount
  const paymentAmount = bookedDoctor?.consultation_fee || booked?.payment_amount || 0;

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
            <strong>{format(new Date(`${selectedDate}T${selectedSlot}`), 'EEEE, MMMM d at h:mm a')}</strong>
          </p>
          <p className="text-slate-400 text-xs">A confirmation will be sent to your phone/email.</p>
        </div>

        {/* Bank transfer instructions */}
        {clinic?.patient_payment_enabled && clinic?.bank_name && clinic?.account_number && (
          <BankTransferCard
            clinicName={clinic.name}
            bankName={clinic.bank_name}
            accountNumber={clinic.account_number}
            amount={paymentAmount}
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
            ) : availableSlots.length === 0 ? (
              <p className="text-slate-500 text-sm text-center py-4">No available slots on this date</p>
            ) : (
              <div className="grid grid-cols-4 sm:grid-cols-6 gap-2">
                {availableSlots.map((slot: any) => (
                  <button key={slot.time} onClick={() => setSelectedSlot(slot.time)}
                    className={`py-2 rounded-lg text-sm font-medium transition-all border ${selectedSlot === slot.time ? 'bg-teal-600 text-white border-teal-600' : 'border-slate-200 text-slate-700 hover:border-teal-400'}`}>
                    {slot.time}
                  </button>
                ))}
              </div>
            )}
          </div>
        )}

        {/* Step 4: Patient Details */}
        {selectedSlot && (
          <div className="bg-white rounded-xl border border-slate-200 p-6">
            <h2 className="font-semibold text-slate-900 mb-4">Your Details</h2>
            <form onSubmit={handleSubmit(d => bookMutation.mutate(d))} className="space-y-3">
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
                <p className="mt-1 text-slate-500">{format(new Date(`${selectedDate}T${selectedSlot}`), 'EEEE, MMMM d, yyyy at h:mm a')}</p>
                {clinic?.patient_payment_enabled && (
                  <p className="mt-1 text-teal-700 text-xs font-medium flex items-center gap-1">
                    <Banknote className="w-3.5 h-3.5" /> Bank transfer payment required after booking
                  </p>
                )}
              </div>

              <button type="submit" disabled={isSubmitting}
                className="w-full bg-teal-600 hover:bg-teal-700 disabled:opacity-60 text-white font-semibold py-3 rounded-xl transition-colors flex items-center justify-center gap-2">
                {isSubmitting && <Loader2 className="w-4 h-4 animate-spin" />}
                Confirm Appointment
              </button>
            </form>
          </div>
        )}
      </div>
    </div>
  );
}
