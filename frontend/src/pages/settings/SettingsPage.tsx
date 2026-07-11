// General Settings Page
import { useState } from 'react';
import { useForm } from 'react-hook-form';
import { useMutation, useQuery } from '@tanstack/react-query';
import { clinicsApi, hospitalBankAccountApi } from '@/lib/api/services';
import { useAuthStore } from '@/stores/authStore';
import { getApiError } from '@/lib/api/client';
import { toast } from 'sonner';
import { Loader2, Copy, Check, Link2, Banknote, Info, Landmark, ShieldCheck } from 'lucide-react';

// ── Clinic ID copy panel ──────────────────────────────────────────────────────

function ClinicIdPanel({ clinicId }: { clinicId: string }) {
  const [copied, setCopied] = useState(false);

  function handleCopy() {
    navigator.clipboard.writeText(clinicId).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    });
  }

  return (
    <div className="bg-white rounded-xl border border-slate-200 p-6 space-y-3">
      <div className="flex items-center gap-2">
        <Link2 className="w-4 h-4 text-teal-600" />
        <h2 className="text-sm font-semibold text-slate-900">Wabizz Integration — Clinic ID</h2>
      </div>
      <p className="text-xs text-slate-500 leading-relaxed">
        Enter this ID in your{' '}
        <span className="font-medium text-slate-700">Wabizz dashboard → Niche Modules → Hospital → Vitar Clinic ID</span>.
        Without it, patients booked via WhatsApp will not appear in your Vitar dashboard.
      </p>
      <div className="flex items-center gap-2">
        <code className="flex-1 rounded-lg bg-slate-50 border border-slate-200 px-3 py-2 text-xs font-mono text-slate-700 select-all break-all">
          {clinicId}
        </code>
        <button
          onClick={handleCopy}
          title="Copy Clinic ID"
          className="shrink-0 inline-flex items-center gap-1.5 rounded-lg border border-slate-200 bg-white px-3 py-2 text-xs font-medium text-slate-700 hover:bg-slate-50 transition-colors"
        >
          {copied ? (
            <>
              <Check className="w-3.5 h-3.5 text-teal-600" />
              Copied
            </>
          ) : (
            <>
              <Copy className="w-3.5 h-3.5" />
              Copy
            </>
          )}
        </button>
      </div>
    </div>
  );
}

// ── Payment collection toggle ─────────────────────────────────────────────────
// Controls whether patients must pay before an appointment is confirmed. When
// on, the booking flow always collects payment through Paystack's checkout —
// there is no manual/unverified payment path, so patients can't claim they
// paid when they didn't; only a Paystack webhook can mark an appointment paid.

interface PaymentToggleFormValues {
  patient_payment_enabled: boolean;
}

function PaymentTogglePanel() {
  const { data, isLoading } = useQuery({
    queryKey: ['clinic-me'],
    queryFn: clinicsApi.getMe,
  });

  const { register, handleSubmit, formState: { isSubmitting } } = useForm<PaymentToggleFormValues>({
    values: {
      patient_payment_enabled: data?.patient_payment_enabled ?? false,
    },
  });

  const mutation = useMutation({
    mutationFn: (values: PaymentToggleFormValues) =>
      clinicsApi.update({ patient_payment_enabled: values.patient_payment_enabled }),
    onSuccess: () => toast.success('Payment settings saved'),
    onError: () => toast.error('Failed to save payment settings'),
  });

  if (isLoading) return null;

  return (
    <div className="bg-white rounded-xl border border-slate-200 p-6 space-y-4">
      <div className="flex items-center gap-2">
        <Banknote className="w-4 h-4 text-teal-600" />
        <h2 className="text-sm font-semibold text-slate-900">Patient Payment</h2>
      </div>

      <div className="flex items-start gap-3 rounded-lg bg-blue-50 border border-blue-100 p-3">
        <Info className="w-4 h-4 text-blue-500 mt-0.5 shrink-0" />
        <p className="text-xs text-blue-700 leading-relaxed">
          When enabled, patients pay their consultation fee through Paystack's secure checkout
          right after booking. The appointment only moves to confirmed once Paystack verifies
          the payment — there's no manual "I already paid" step, so there's nothing for a
          patient to dispute.
        </p>
      </div>

      <form onSubmit={handleSubmit(d => mutation.mutate(d))} className="space-y-4">
        <label className="flex items-center gap-3 cursor-pointer">
          <input
            type="checkbox"
            {...register('patient_payment_enabled')}
            className="w-4 h-4 rounded text-teal-600 focus:ring-teal-500 border-slate-300"
          />
          <span className="text-sm font-medium text-slate-700">Require payment before appointments</span>
        </label>

        <button
          type="submit"
          disabled={isSubmitting}
          className="w-full bg-teal-600 hover:bg-teal-700 disabled:opacity-60 text-white font-semibold py-2.5 rounded-lg text-sm transition-colors flex items-center justify-center gap-2"
        >
          {isSubmitting && <Loader2 className="w-4 h-4 animate-spin" />}
          Save Payment Settings
        </button>
      </form>
    </div>
  );
}

// ── Payout account panel ──────────────────────────────────────────────────────
// This is a different thing from the toggle above: it's where Vitar sends YOUR
// share of the money after Paystack collects it from patients (via the
// Transfers API). Same verified resolve+confirm flow used during onboarding.

function PayoutAccountPanel({ clinicId }: { clinicId: string }) {
  const { data: account, isLoading, refetch } = useQuery({
    queryKey: ['hospital-bank-account', clinicId],
    queryFn: async () => (await hospitalBankAccountApi.get(clinicId)).bank_account,
  });
  const { data: banksData } = useQuery({
    queryKey: ['payout-banks'],
    queryFn: hospitalBankAccountApi.getBanks,
  });
  const banks: { code: string; name: string }[] = banksData?.banks ?? [];

  const [editing, setEditing] = useState(false);
  const [bankCode, setBankCode] = useState('');
  const [accountNumber, setAccountNumber] = useState('');
  const [resolvedName, setResolvedName] = useState<string | null>(null);
  const [resolving, setResolving] = useState(false);
  const [saving, setSaving] = useState(false);

  async function handleResolve() {
    if (accountNumber.length !== 10 || !bankCode) return;
    setResolving(true);
    setResolvedName(null);
    try {
      const res = await hospitalBankAccountApi.resolve(clinicId, accountNumber, bankCode);
      setResolvedName(res.account_name || null);
      if (!res.account_name) toast.error('Could not verify this account. Double-check the number and bank.');
    } catch (err) {
      toast.error(getApiError(err) || 'Could not verify this account with Paystack');
    } finally {
      setResolving(false);
    }
  }

  async function handleSave() {
    if (!resolvedName) return;
    setSaving(true);
    try {
      if (account) {
        await hospitalBankAccountApi.replace(clinicId, accountNumber, bankCode);
      } else {
        await hospitalBankAccountApi.create(clinicId, accountNumber, bankCode);
      }
      toast.success('Payout account saved');
      setEditing(false);
      setAccountNumber('');
      setBankCode('');
      setResolvedName(null);
      refetch();
    } catch (err) {
      toast.error(getApiError(err) || 'Could not save payout account');
    } finally {
      setSaving(false);
    }
  }

  if (isLoading) return null;

  return (
    <div className="bg-white rounded-xl border border-slate-200 p-6 space-y-4">
      <div className="flex items-center gap-2">
        <Landmark className="w-4 h-4 text-teal-600" />
        <h2 className="text-sm font-semibold text-slate-900">Payout Account</h2>
      </div>
      <p className="text-xs text-slate-500 leading-relaxed">
        We send your share of each payment here after Paystack confirms it, via a verified
        bank transfer — not a raw account number typed into a settings form.
      </p>

      {account && !editing ? (
        <div className="rounded-lg border border-slate-200 divide-y divide-slate-100">
          <div className="flex justify-between px-4 py-3 text-sm">
            <span className="text-slate-500">Bank</span>
            <span className="font-medium text-slate-900">{account.bank_name}</span>
          </div>
          <div className="flex justify-between px-4 py-3 text-sm">
            <span className="text-slate-500">Account number</span>
            <span className="font-mono font-medium text-slate-900 tracking-wider">{account.account_number}</span>
          </div>
          <div className="flex justify-between px-4 py-3 text-sm">
            <span className="text-slate-500">Account name</span>
            <span className="font-medium text-slate-900">{account.account_name}</span>
          </div>
          <div className="flex justify-between items-center px-4 py-3 text-sm">
            <span className="text-slate-500">Status</span>
            <span className={`text-xs font-medium px-2 py-0.5 rounded-full ${account.verified ? 'bg-teal-100 text-teal-700' : 'bg-amber-100 text-amber-700'}`}>
              {account.verified ? 'Verified' : 'Unverified'}
            </span>
          </div>
        </div>
      ) : !editing ? (
        <p className="text-sm text-slate-400 italic">No payout account on file yet.</p>
      ) : null}

      {editing ? (
        <div className="space-y-3">
          <div>
            <label className="block text-xs font-medium text-slate-600 mb-1">Bank</label>
            <select
              value={bankCode}
              onChange={(e) => { setBankCode(e.target.value); setResolvedName(null); }}
              className="w-full border border-slate-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-teal-500 bg-white"
            >
              <option value="">Select your bank</option>
              {banks.map(b => <option key={b.code} value={b.code}>{b.name}</option>)}
            </select>
          </div>
          <div>
            <label className="block text-xs font-medium text-slate-600 mb-1">Account number</label>
            <input
              value={accountNumber}
              onChange={(e) => { setAccountNumber(e.target.value.replace(/\D/g, '').slice(0, 10)); setResolvedName(null); }}
              placeholder="10-digit NUBAN"
              maxLength={10}
              inputMode="numeric"
              className="w-full border border-slate-300 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-teal-500 font-mono tracking-wider"
            />
          </div>
          <button
            type="button"
            onClick={handleResolve}
            disabled={!bankCode || accountNumber.length !== 10 || resolving}
            className="w-full border border-teal-600 text-teal-700 hover:bg-teal-50 font-semibold py-2 rounded-lg text-sm flex items-center justify-center gap-2 disabled:opacity-50"
          >
            {resolving && <Loader2 className="w-4 h-4 animate-spin" />}
            Verify account
          </button>
          {resolvedName && (
            <div className="flex items-center gap-2 rounded-lg bg-teal-50 border border-teal-200 p-3">
              <ShieldCheck className="w-4 h-4 text-teal-600 flex-shrink-0" />
              <p className="text-sm text-teal-800">Verified: <span className="font-semibold">{resolvedName}</span></p>
            </div>
          )}
          <div className="flex gap-2">
            <button
              type="button"
              onClick={handleSave}
              disabled={!resolvedName || saving}
              className="flex-1 bg-teal-600 hover:bg-teal-700 disabled:opacity-50 text-white font-semibold py-2 rounded-lg text-sm flex items-center justify-center gap-2"
            >
              {saving && <Loader2 className="w-4 h-4 animate-spin" />}
              Save
            </button>
            <button type="button" onClick={() => { setEditing(false); setResolvedName(null); }}
              className="flex-1 text-slate-500 text-sm hover:text-slate-700">
              Cancel
            </button>
          </div>
        </div>
      ) : (
        <button
          type="button"
          onClick={() => setEditing(true)}
          className="w-full border border-slate-300 hover:bg-slate-50 text-slate-700 font-semibold py-2 rounded-lg text-sm transition-colors"
        >
          {account ? 'Replace payout account' : 'Add payout account'}
        </button>
      )}
    </div>
  );
}

// ── Settings form ─────────────────────────────────────────────────────────────

export function SettingsPage() {
  const { clinic, refreshClinic } = useAuthStore();
  const { register, handleSubmit, formState: { isSubmitting } } = useForm({
    defaultValues: {
      name: clinic?.name ?? '',
      phone: '',
      address: '',
      city: '',
      timezone: 'Africa/Lagos',
    },
  });

  const updateMutation = useMutation({
    mutationFn: clinicsApi.update,
    onSuccess: () => { refreshClinic(); toast.success('Settings saved'); },
    onError: () => toast.error('Failed to save'),
  });

  return (
    <div className="p-6 max-w-2xl mx-auto space-y-6">
      <h1 className="text-2xl font-bold text-slate-900">Clinic Settings</h1>

      {/* Clinic UUID panel — required for Wabizz integration */}
      {clinic?.id && <ClinicIdPanel clinicId={clinic.id} />}

      {/* Whether patients must pay (via Paystack checkout) before booking is confirmed */}
      {clinic?.id && <PaymentTogglePanel />}

      {/* Where Vitar sends the clinic's share after Paystack collects payment */}
      {clinic?.id && <PayoutAccountPanel clinicId={clinic.id} />}

      <form onSubmit={handleSubmit(d => updateMutation.mutate(d))} className="bg-white rounded-xl border border-slate-200 p-6 space-y-4">
        <h2 className="text-sm font-semibold text-slate-900">General Information</h2>
        <div>
          <label className="block text-sm font-medium text-slate-700 mb-1">Clinic Name</label>
          <input {...register('name')} className="w-full border border-slate-300 rounded-lg px-3 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-teal-500" />
        </div>
        <div>
          <label className="block text-sm font-medium text-slate-700 mb-1">Phone</label>
          <input {...register('phone')} placeholder="+234..."
            className="w-full border border-slate-300 rounded-lg px-3 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-teal-500" />
        </div>
        <div>
          <label className="block text-sm font-medium text-slate-700 mb-1">Address</label>
          <input {...register('address')} placeholder="Street address"
            className="w-full border border-slate-300 rounded-lg px-3 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-teal-500" />
        </div>
        <div>
          <label className="block text-sm font-medium text-slate-700 mb-1">City</label>
          <input {...register('city')} placeholder="Lagos"
            className="w-full border border-slate-300 rounded-lg px-3 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-teal-500" />
        </div>
        <div>
          <label className="block text-sm font-medium text-slate-700 mb-1">Timezone</label>
          <select {...register('timezone')} className="w-full border border-slate-300 rounded-lg px-3 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-teal-500 bg-white">
            <option value="Africa/Lagos">Africa/Lagos (WAT)</option>
            <option value="Africa/Nairobi">Africa/Nairobi (EAT)</option>
            <option value="UTC">UTC</option>
            <option value="America/New_York">America/New_York (ET)</option>
            <option value="Europe/London">Europe/London (GMT)</option>
          </select>
        </div>
        <button type="submit" disabled={isSubmitting}
          className="w-full bg-teal-600 hover:bg-teal-700 text-white font-semibold py-2.5 rounded-lg text-sm transition-colors flex items-center justify-center gap-2">
          {isSubmitting && <Loader2 className="w-4 h-4 animate-spin" />}
          Save Changes
        </button>
      </form>
    </div>
  );
}
export default SettingsPage;
