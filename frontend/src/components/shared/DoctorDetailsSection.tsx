/**
 * Vitar — Doctor Details Section
 *
 * Lets a doctor publish an email, contact number, and direct patient
 * contact (WhatsApp / call) on the public booking page. This is a core
 * feature — not gated by subscription or trial status. Whether the
 * WhatsApp/call buttons actually show to patients is controlled at the
 * hospital level via Settings → Hospital Contact Settings.
 */
import { MessageCircle } from 'lucide-react';

export interface DoctorDetailsValue {
  email: string;
  phone: string;
  doctor_details_enabled: boolean;
  // Lets this satisfy Record<string, unknown> when passed straight into
  // doctorsApi.update()/create() without a cast at every call site.
  [key: string]: unknown;
}

interface DoctorDetailsSectionProps {
  value: DoctorDetailsValue;
  onChange: (next: DoctorDetailsValue) => void;
  /** Pass react-hook-form's register('email') / register('phone') to let RHF drive these inputs instead of `value`/`onChange`. */
  registerEmail?: Record<string, any>;
  registerPhone?: Record<string, any>;
}

export default function DoctorDetailsSection({
  value,
  onChange,
  registerEmail,
  registerPhone,
}: DoctorDetailsSectionProps) {
  return (
    <div className="rounded-xl border border-teal-200 bg-teal-50/40 p-4 relative">
      <div className="flex items-start justify-between gap-3 mb-3">
        <div>
          <h3 className="font-semibold text-slate-900">Doctor Details</h3>
          <p className="text-xs text-slate-500 mt-1">
            Let patients see this doctor's email and contact number, and reach them directly via
            WhatsApp or phone call — subject to your Hospital Contact Settings.
          </p>
        </div>
        <label className="inline-flex items-center cursor-pointer flex-shrink-0">
          <input
            type="checkbox"
            className="sr-only peer"
            checked={value.doctor_details_enabled}
            onChange={(e) => onChange({ ...value, doctor_details_enabled: e.target.checked })}
          />
          <div className="w-9 h-5 bg-slate-300 peer-checked:bg-teal-600 rounded-full transition-colors relative">
            <div className="absolute top-0.5 left-0.5 w-4 h-4 bg-white rounded-full transition-transform peer-checked:translate-x-4" />
          </div>
        </label>
      </div>

      <div className="space-y-3">
        <div className="grid grid-cols-2 gap-3">
          <div>
            <label className="block text-xs font-medium text-slate-700 mb-1">Email</label>
            {registerEmail ? (
              <input
                {...registerEmail}
                type="email"
                placeholder="doctor@clinic.com"
                className="w-full border border-slate-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-teal-500 bg-white"
              />
            ) : (
              <input
                type="email"
                value={value.email}
                onChange={(e) => onChange({ ...value, email: e.target.value })}
                placeholder="doctor@clinic.com"
                className="w-full border border-slate-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-teal-500 bg-white"
              />
            )}
          </div>
          <div>
            <label className="block text-xs font-medium text-slate-700 mb-1">Contact number</label>
            {registerPhone ? (
              <input
                {...registerPhone}
                placeholder="+2348012345678"
                className="w-full border border-slate-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-teal-500 bg-white"
              />
            ) : (
              <input
                value={value.phone}
                onChange={(e) => onChange({ ...value, phone: e.target.value })}
                placeholder="+2348012345678"
                className="w-full border border-slate-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-teal-500 bg-white"
              />
            )}
          </div>
        </div>

        {value.doctor_details_enabled && (
          <div className="flex items-center gap-2 text-xs text-teal-700 bg-white border border-teal-200 rounded-lg px-3 py-2">
            <MessageCircle className="w-3.5 h-3.5 flex-shrink-0" />
            <span>
              Patients will see <strong>"Chat on WhatsApp"</strong> and <strong>"Call Doctor"</strong> buttons
              on your booking page
              {value.phone ? ` for ${value.phone}` : ' once a contact number is added'}, as allowed by your
              Hospital Contact Settings.
            </span>
          </div>
        )}
      </div>
    </div>
  );
}
