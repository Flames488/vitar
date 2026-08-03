/**
 * Vitar - eRegistration Form (Phase 2)
 * 5-step patient registration: Personal → Address → Emergency Contact →
 * Health Info (optional) → Review & Consent. Same component handles both
 * first-time submission (autosave + restore-on-refresh) and editing an
 * already-submitted registration (no autosave, explicit Save Changes).
 *
 * No patient login exists in Vitar — identity/authorization here is a
 * registration_token in the URL (see backend registrations.py), the same
 * shape as the existing appointment confirmation_token/cancel_token.
 */
import { useEffect, useRef, useState } from 'react';
import { useParams, useSearchParams, useNavigate } from 'react-router-dom';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { z } from 'zod';
import {
  CheckCircle, ChevronRight, ChevronLeft, Loader2,
  User, MapPin, Phone, HeartPulse, ClipboardCheck,
} from 'lucide-react';
import { registrationsApi, bookingApi } from '@/lib/api/services';
import { getApiError } from '@/lib/api/client';
import { toast } from 'sonner';

const STEPS = [
  { id: 1, label: 'Personal', icon: User },
  { id: 2, label: 'Address', icon: MapPin },
  { id: 3, label: 'Emergency Contact', icon: Phone },
  { id: 4, label: 'Health Info', icon: HeartPulse },
  { id: 5, label: 'Review', icon: ClipboardCheck },
];

const STEP_FIELDS = {
  1: ['full_name', 'phone_number', 'date_of_birth', 'gender'],
  2: ['state', 'city', 'residential_address'],
  3: ['emergency_contact_name', 'emergency_contact_relationship', 'emergency_contact_phone'],
  4: ['blood_group', 'genotype', 'allergies', 'existing_conditions', 'current_medications'],
} as const;

const schema = z.object({
  full_name: z.string().min(2, 'Full name is required'),
  phone_number: z.string().min(7, 'Phone number is required'),
  date_of_birth: z.string().min(1, 'Date of birth is required'),
  gender: z.string().min(1, 'Gender is required'),

  state: z.string().min(2, 'State is required'),
  city: z.string().min(2, 'City is required'),
  residential_address: z.string().min(5, 'Residential address is required'),

  emergency_contact_name: z.string().min(2, 'Emergency contact name is required'),
  emergency_contact_relationship: z.string().min(2, 'Relationship is required'),
  emergency_contact_phone: z.string().min(7, 'Emergency contact phone is required'),

  blood_group: z.string().optional(),
  genotype: z.string().optional(),
  allergies: z.string().optional(),
  existing_conditions: z.string().optional(),
  current_medications: z.string().optional(),
});

type FormData = z.infer<typeof schema>;

const EMPTY: FormData = {
  full_name: '', phone_number: '', date_of_birth: '', gender: '',
  state: '', city: '', residential_address: '',
  emergency_contact_name: '', emergency_contact_relationship: '', emergency_contact_phone: '',
  blood_group: '', genotype: '', allergies: '', existing_conditions: '', current_medications: '',
};

export default function RegistrationFormPage() {
  const { slug } = useParams<{ slug: string }>();
  const [searchParams, setSearchParams] = useSearchParams();
  const navigate = useNavigate();

  const clinicId = searchParams.get('clinic_id') || '';
  const patientId = searchParams.get('patient_id');
  const urlToken = searchParams.get('token');
  // patient_id is dropped from the URL after the first autosave (replaced by
  // registration_token — see autosave()), but POST /registrations/draft still
  // needs it on every call, so capture the mount-time value once rather than
  // re-reading searchParams (which would go null after that replace).
  const bootstrapPatientId = useRef(patientId).current;

  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [unavailable, setUnavailable] = useState(false);
  const [step, setStep] = useState(1);
  const [editMode, setEditMode] = useState(false);
  const [registrationId, setRegistrationId] = useState<string | null>(null);
  const [token, setToken] = useState<string | null>(urlToken);
  const [submitted, setSubmitted] = useState(false);
  const [saving, setSaving] = useState(false);
  const [consentChecked, setConsentChecked] = useState(false);

  const { register, handleSubmit, trigger, watch, reset, getValues, formState: { errors } } = useForm<FormData>({
    resolver: zodResolver(schema),
    defaultValues: EMPTY,
  });

  const clinicName = useRef<string>('');

  // ── Load clinic + existing registration state ──────────────────────────
  useEffect(() => {
    if (!slug) return;
    let cancelled = false;

    (async () => {
      try {
        const clinicData = await bookingApi.getClinic(slug);
        if (cancelled) return;
        clinicName.current = clinicData?.clinic?.name || 'this clinic';
        const resolvedClinicId = clinicData?.clinic?.id || clinicId;

        if (!urlToken && !patientId) {
          setLoadError('This registration link is missing required information.');
          setLoading(false);
          return;
        }

        const status = urlToken
          ? await registrationsApi.getStatus({ clinic_id: resolvedClinicId, token: urlToken })
          : await registrationsApi.getStatus({ clinic_id: resolvedClinicId, patient_id: patientId! });
        if (cancelled) return;

        if (status.registered) {
          // Already submitted — edit mode, consent is not re-collected.
          setEditMode(true);
          setRegistrationId(status.id);
          setToken(status.registration_token);
          reset(fillDefaults(status));
          setSearchParams({ clinic_id: resolvedClinicId, token: status.registration_token }, { replace: true });
        } else {
          if (!status.draft) {
            // Nothing saved yet — eligibility only matters for a brand-new registration.
            const eligibility = await registrationsApi.getEligibility(resolvedClinicId);
            if (!eligibility.available) {
              setUnavailable(true);
              setLoading(false);
              return;
            }
          }
          const draft = status.draft;
          reset(fillDefaults(draft || status.prefill || {}));
          if (draft) {
            setRegistrationId(draft.id);
            setToken(draft.registration_token);
            setSearchParams({ clinic_id: resolvedClinicId, token: draft.registration_token }, { replace: true });
          }
        }
      } catch (err) {
        if (!cancelled) setLoadError(getApiError(err) || 'Could not load your registration.');
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();

    return () => { cancelled = true; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [slug]);

  // ── Debounced autosave (first-time flow only, not edit mode) ───────────
  const saveTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const watched = watch();

  useEffect(() => {
    if (editMode || submitted || loading || step === 5) return;
    if (saveTimer.current) clearTimeout(saveTimer.current);
    saveTimer.current = setTimeout(() => {
      autosave();
    }, 1200);
    return () => { if (saveTimer.current) clearTimeout(saveTimer.current); };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [JSON.stringify(STEP_FIELDS[step as 1 | 2 | 3 | 4]?.map(f => watched[f as keyof FormData])) , editMode, submitted, loading, step]);

  async function autosave() {
    if (!clinicId || !bootstrapPatientId) return;
    const fields = STEP_FIELDS[step as 1 | 2 | 3 | 4];
    if (!fields) return;
    const values = getValues();
    const payload: Record<string, unknown> = {};
    fields.forEach((f) => { payload[f] = values[f as keyof FormData] || undefined; });
    if (Object.values(payload).every((v) => !v)) return; // nothing worth saving yet

    try {
      const res = await registrationsApi.saveDraft({ clinic_id: clinicId, patient_id: bootstrapPatientId, ...payload });
      if (!token && res.registration_token) {
        setToken(res.registration_token);
        setRegistrationId(res.id);
        setSearchParams({ clinic_id: clinicId, token: res.registration_token }, { replace: true });
      }
    } catch {
      // Silent — autosave failures shouldn't interrupt the patient filling the form.
    }
  }

  function fillDefaults(data: Partial<FormData> & { date_of_birth?: string | null }): FormData {
    return {
      ...EMPTY,
      ...data,
      date_of_birth: data.date_of_birth ? data.date_of_birth.slice(0, 10) : '',
    } as FormData;
  }

  const goNext = async () => {
    const fields = STEP_FIELDS[step as 1 | 2 | 3 | 4];
    if (fields) {
      const valid = await trigger([...fields] as (keyof FormData)[]);
      if (!valid) return;
    }
    if (step < 5) {
      if (saveTimer.current) clearTimeout(saveTimer.current);
      await autosave();
      setStep((s) => s + 1);
    }
  };
  const goBack = () => setStep((s) => Math.max(1, s - 1));

  const skipHealthInfo = () => {
    reset({
      ...getValues(),
      blood_group: getValues('blood_group') || 'Unknown',
      genotype: getValues('genotype') || 'Unknown',
      allergies: getValues('allergies') || 'None',
      existing_conditions: getValues('existing_conditions') || 'None',
      current_medications: getValues('current_medications') || 'None',
    });
  };

  const onSubmit = async (data: FormData) => {
    if (!editMode && !consentChecked) return;
    setSaving(true);
    try {
      if (editMode) {
        await registrationsApi.update(registrationId!, { token, ...data });
        toast.success('Registration updated');
      } else {
        await registrationsApi.submit({ clinic_id: clinicId, token, consent_given: true, ...data });
        setSubmitted(true);
      }
    } catch (err) {
      toast.error(getApiError(err) || 'Something went wrong. Please try again.');
    } finally {
      setSaving(false);
    }
  };

  const values = watch();

  if (loading) return (
    <div className="min-h-screen bg-slate-50 flex items-center justify-center">
      <Loader2 className="w-8 h-8 text-teal-600 animate-spin" />
    </div>
  );

  if (loadError) return (
    <CenteredMessage title="Couldn't load registration" body={loadError} />
  );

  if (unavailable) return (
    <CenteredMessage
      title="Registration not available"
      body="Online registration isn't currently available for this clinic. Please contact the clinic directly, or complete registration in person at your visit."
    />
  );

  if (submitted) return (
    <CenteredMessage
      title="Registration Complete"
      body={`Thank you — your registration with ${clinicName.current} has been submitted.`}
      success
    />
  );

  return (
    <div className="min-h-screen bg-slate-50">
      <div className="bg-teal-700 text-white py-8 px-4">
        <div className="max-w-2xl mx-auto text-center">
          <h1 className="text-2xl font-bold">{editMode ? 'Edit Your Registration' : 'Patient Registration'}</h1>
          <p className="text-teal-200 text-sm mt-1">{clinicName.current}</p>
        </div>
      </div>

      <div className="max-w-2xl mx-auto px-4 py-8">
        {!editMode && (
          <div className="flex items-center justify-center gap-1.5 mb-6 flex-wrap">
            {STEPS.map((s, i) => {
              const done = step > s.id;
              const active = step === s.id;
              return (
                <div key={s.id} className="flex items-center gap-1.5">
                  <div className={`flex items-center gap-1.5 px-2.5 py-1.5 rounded-full text-xs font-medium transition-all ${
                    done ? 'bg-teal-600 text-white' : active ? 'bg-white text-slate-900 border-2 border-teal-500' : 'bg-slate-100 text-slate-400'
                  }`}>
                    {done ? <CheckCircle className="w-3.5 h-3.5" /> : <s.icon className="w-3.5 h-3.5" />}
                    <span className="hidden sm:inline">{s.label}</span>
                  </div>
                  {i < STEPS.length - 1 && <ChevronRight className="w-3 h-3 text-slate-300 flex-shrink-0" />}
                </div>
              );
            })}
          </div>
        )}

        <form onSubmit={handleSubmit(onSubmit)} className="bg-white rounded-2xl border border-slate-200 shadow-sm p-6 sm:p-8 space-y-4">
          {(editMode || step === 1) && (
            <StepBlock title="Personal Information">
              <Field label="Full name *" error={errors.full_name?.message}>
                <input {...register('full_name')} className={inputCls} />
              </Field>
              <Field label="Phone number *" error={errors.phone_number?.message}>
                <input {...register('phone_number')} type="tel" className={inputCls} />
              </Field>
              <div className="grid grid-cols-2 gap-3">
                <Field label="Date of birth *" error={errors.date_of_birth?.message}>
                  <input {...register('date_of_birth')} type="date" className={inputCls} />
                </Field>
                <Field label="Gender *" error={errors.gender?.message}>
                  <select {...register('gender')} className={inputCls}>
                    <option value="">Select</option>
                    <option value="Female">Female</option>
                    <option value="Male">Male</option>
                    <option value="Other">Other</option>
                  </select>
                </Field>
              </div>
            </StepBlock>
          )}

          {(editMode || step === 2) && (
            <StepBlock title="Address">
              <div className="grid grid-cols-2 gap-3">
                <Field label="State *" error={errors.state?.message}>
                  <input {...register('state')} className={inputCls} />
                </Field>
                <Field label="City *" error={errors.city?.message}>
                  <input {...register('city')} className={inputCls} />
                </Field>
              </div>
              <Field label="Residential address *" error={errors.residential_address?.message}>
                <input {...register('residential_address')} className={inputCls} />
              </Field>
            </StepBlock>
          )}

          {(editMode || step === 3) && (
            <StepBlock title="Emergency Contact">
              <Field label="Name *" error={errors.emergency_contact_name?.message}>
                <input {...register('emergency_contact_name')} className={inputCls} />
              </Field>
              <div className="grid grid-cols-2 gap-3">
                <Field label="Relationship *" error={errors.emergency_contact_relationship?.message}>
                  <input {...register('emergency_contact_relationship')} className={inputCls} />
                </Field>
                <Field label="Phone number *" error={errors.emergency_contact_phone?.message}>
                  <input {...register('emergency_contact_phone')} type="tel" className={inputCls} />
                </Field>
              </div>
            </StepBlock>
          )}

          {(editMode || step === 4) && (
            <StepBlock title="Additional Health Information" subtitle="Optional — helps the clinic prepare, but you can skip this entirely.">
              {!editMode && (
                <button type="button" onClick={skipHealthInfo}
                  className="text-xs font-medium text-teal-600 hover:text-teal-700 mb-1">
                  Skip this section (mark as Unknown/None)
                </button>
              )}
              <div className="grid grid-cols-2 gap-3">
                <Field label="Blood group">
                  <input {...register('blood_group')} placeholder="e.g. O+, or Unknown" className={inputCls} />
                </Field>
                <Field label="Genotype">
                  <input {...register('genotype')} placeholder="e.g. AA, or Unknown" className={inputCls} />
                </Field>
              </div>
              <Field label="Allergies">
                <input {...register('allergies')} placeholder="e.g. Penicillin, or None" className={inputCls} />
              </Field>
              <Field label="Existing medical conditions">
                <input {...register('existing_conditions')} placeholder="e.g. Asthma, or None" className={inputCls} />
              </Field>
              <Field label="Current medications">
                <input {...register('current_medications')} placeholder="e.g. Metformin, or None" className={inputCls} />
              </Field>
            </StepBlock>
          )}

          {!editMode && step === 5 && (
            <StepBlock title="Review & Consent">
              <ReviewSummary values={values} />
              <label className="flex items-start gap-2.5 mt-4 p-3 bg-slate-50 rounded-lg cursor-pointer">
                <input
                  type="checkbox"
                  checked={consentChecked}
                  onChange={(e) => setConsentChecked(e.target.checked)}
                  className="mt-0.5"
                />
                <span className="text-sm text-slate-700">
                  I consent to sharing this information with <strong>{clinicName.current}</strong> for the purpose of my care.
                </span>
              </label>
            </StepBlock>
          )}

          <div className="flex items-center justify-between pt-4 border-t border-slate-100">
            {!editMode && step > 1 ? (
              <button type="button" onClick={goBack}
                className="inline-flex items-center gap-1 text-sm font-medium text-slate-600 hover:text-slate-900">
                <ChevronLeft className="w-4 h-4" /> Back
              </button>
            ) : <span />}

            {editMode ? (
              <button type="submit" disabled={saving}
                className="inline-flex items-center gap-2 bg-teal-600 hover:bg-teal-700 disabled:opacity-60 text-white font-semibold px-5 py-2.5 rounded-xl transition-colors">
                {saving && <Loader2 className="w-4 h-4 animate-spin" />} Save Changes
              </button>
            ) : step < 5 ? (
              <button type="button" onClick={goNext}
                className="inline-flex items-center gap-1.5 bg-teal-600 hover:bg-teal-700 text-white font-semibold px-5 py-2.5 rounded-xl transition-colors">
                Next <ChevronRight className="w-4 h-4" />
              </button>
            ) : (
              <button type="submit" disabled={saving || !consentChecked}
                className="inline-flex items-center gap-2 bg-teal-600 hover:bg-teal-700 disabled:opacity-50 disabled:cursor-not-allowed text-white font-semibold px-5 py-2.5 rounded-xl transition-colors">
                {saving && <Loader2 className="w-4 h-4 animate-spin" />} Submit Registration
              </button>
            )}
          </div>
        </form>
      </div>
    </div>
  );
}

const inputCls = "w-full border border-slate-300 rounded-lg px-3 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-teal-500";

function StepBlock({ title, subtitle, children }: { title: string; subtitle?: string; children: React.ReactNode }) {
  return (
    <div className="space-y-3">
      <div>
        <h2 className="font-semibold text-slate-900">{title}</h2>
        {subtitle && <p className="text-xs text-slate-500 mt-0.5">{subtitle}</p>}
      </div>
      {children}
    </div>
  );
}

function Field({ label, error, children }: { label: string; error?: string; children: React.ReactNode }) {
  return (
    <div>
      <label className="block text-sm font-medium text-slate-700 mb-1">{label}</label>
      {children}
      {error && <p className="text-red-500 text-xs mt-1">{error}</p>}
    </div>
  );
}

function ReviewSummary({ values }: { values: FormData }) {
  const rows: [string, string][] = [
    ['Full name', values.full_name], ['Phone', values.phone_number],
    ['Date of birth', values.date_of_birth], ['Gender', values.gender],
    ['State', values.state], ['City', values.city], ['Address', values.residential_address],
    ['Emergency contact', values.emergency_contact_name],
    ['Relationship', values.emergency_contact_relationship],
    ['Emergency phone', values.emergency_contact_phone],
    ['Blood group', values.blood_group || '—'], ['Genotype', values.genotype || '—'],
    ['Allergies', values.allergies || '—'], ['Conditions', values.existing_conditions || '—'],
    ['Medications', values.current_medications || '—'],
  ];
  return (
    <div className="bg-slate-50 rounded-lg p-4 text-sm divide-y divide-slate-200">
      {rows.map(([label, value]) => (
        <div key={label} className="flex justify-between py-1.5 gap-4">
          <span className="text-slate-500">{label}</span>
          <span className="text-slate-900 font-medium text-right">{value || '—'}</span>
        </div>
      ))}
    </div>
  );
}

function CenteredMessage({ title, body, success }: { title: string; body: string; success?: boolean }) {
  return (
    <div className="min-h-screen bg-slate-50 flex items-center justify-center p-4">
      <div className="bg-white rounded-2xl shadow-lg p-8 max-w-md w-full text-center space-y-3">
        {success && <CheckCircle className="w-14 h-14 text-teal-500 mx-auto" />}
        <h2 className="text-xl font-bold text-slate-900">{title}</h2>
        <p className="text-slate-500 text-sm">{body}</p>
      </div>
    </div>
  );
}
