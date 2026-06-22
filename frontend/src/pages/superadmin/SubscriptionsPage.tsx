/**
 * Vitar — Admin Dashboard: Subscription & Billing Administration
 * Module 4 of the spec (marked high priority). Every override here writes
 * to the existing Subscription columns (no schema changes) and is recorded
 * in the audit trail — see admin_subscriptions.py.
 */
import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { Settings2 } from 'lucide-react';
import { adminApi } from '@/lib/api/services';
import { getApiError } from '@/lib/api/client';
import {
  useAdminTheme, SearchInput, Select, Pagination, StatusBadge,
  EmptyState, LoadingState, Modal, FormField, TextInput, TextArea, PrimaryButton, SecondaryButton,
} from '@/components/admin/AdminUI';

type OverrideAction = 'grant_free' | 'grant_temporary' | 'grant_lifetime' | 'extend' | 'set_expiration' | 'revoke';

const ACTION_OPTIONS: { value: OverrideAction; label: string }[] = [
  { value: 'grant_free', label: 'Grant Free Access' },
  { value: 'grant_temporary', label: 'Grant Temporary Access' },
  { value: 'grant_lifetime', label: 'Grant Lifetime Access' },
  { value: 'extend', label: 'Extend Subscription' },
  { value: 'set_expiration', label: 'Set Custom Expiration Date' },
  { value: 'revoke', label: 'Revoke Access Immediately' },
];

const PLAN_OPTIONS = ['trial', 'basic', 'pro', 'enterprise'];

export default function AdminSubscriptionsPage() {
  const { c } = useAdminTheme();
  const queryClient = useQueryClient();

  const [search, setSearch] = useState('');
  const [planFilter, setPlanFilter] = useState('');
  const [statusFilter, setStatusFilter] = useState('');
  const [page, setPage] = useState(1);

  const [target, setTarget] = useState<{ clinicId: string; clinicName: string } | null>(null);
  const [action, setAction] = useState<OverrideAction>('grant_temporary');
  const [plan, setPlan] = useState('');
  const [durationDays, setDurationDays] = useState('30');
  const [expirationDate, setExpirationDate] = useState('');
  const [notes, setNotes] = useState('');
  const [reason, setReason] = useState('');

  const { data, isLoading } = useQuery({
    queryKey: ['admin', 'subscriptions', { search, planFilter, statusFilter, page }],
    queryFn: () => adminApi.subscriptions.list({
      search: search || undefined, plan: planFilter || undefined, status: statusFilter || undefined, page, limit: 20,
    }),
  });

  const overrideMutation = useMutation({
    mutationFn: () => adminApi.subscriptions.override(target!.clinicId, {
      action,
      plan: plan || undefined,
      duration_days: ['grant_temporary', 'extend'].includes(action) ? Number(durationDays) : undefined,
      expiration_date: action === 'set_expiration' ? expirationDate : undefined,
      notes: notes || undefined,
      reason: reason || undefined,
    }),
    onSuccess: () => {
      toast.success('Subscription updated');
      queryClient.invalidateQueries({ queryKey: ['admin', 'subscriptions'] });
      closeModal();
    },
    onError: (err) => toast.error(getApiError(err)),
  });

  const closeModal = () => {
    setTarget(null); setNotes(''); setReason(''); setPlan('pro'); setExpirationDate(''); setDurationDays('30');
  };

  const openOverride = (clinicId: string, clinicName: string) => {
    setTarget({ clinicId, clinicName });
    setAction('grant_temporary');
    setPlan('pro'); // sensible default so admin doesn't have to pick every time
  };

  const items = data?.items ?? [];

  return (
    <div className="p-6 space-y-4 max-w-7xl mx-auto">
      <div>
        <h1 className={`text-2xl font-bold ${c.text}`}>Subscriptions</h1>
        <p className={`text-sm mt-1 ${c.textMuted}`}>{data?.total ?? 0} clinic subscriptions</p>
      </div>

      <div className="flex flex-col sm:flex-row gap-3">
        <div className="flex-1">
          <SearchInput value={search} onChange={(v) => { setSearch(v); setPage(1); }} placeholder="Search by clinic name..." />
        </div>
        <Select value={planFilter} onChange={(e) => { setPlanFilter(e.target.value); setPage(1); }} className="sm:w-40">
          <option value="">All plans</option>
          {PLAN_OPTIONS.map((p) => <option key={p} value={p} className="capitalize">{p}</option>)}
        </Select>
        <Select value={statusFilter} onChange={(e) => { setStatusFilter(e.target.value); setPage(1); }} className="sm:w-40">
          <option value="">All statuses</option>
          <option value="active">Active</option>
          <option value="trialing">Trialing</option>
          <option value="past_due">Past Due</option>
          <option value="cancelled">Cancelled</option>
          <option value="expired">Expired</option>
        </Select>
      </div>

      <div className={`rounded-xl border overflow-hidden ${c.panel}`}>
        {isLoading ? (
          <LoadingState message="Loading subscriptions..." />
        ) : items.length === 0 ? (
          <EmptyState message="No subscriptions found" />
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className={`border-b ${c.border}`}>
                  <th className={`text-left px-4 py-3 font-medium ${c.textMuted}`}>Clinic</th>
                  <th className={`text-left px-4 py-3 font-medium ${c.textMuted}`}>Plan</th>
                  <th className={`text-left px-4 py-3 font-medium ${c.textMuted}`}>Status</th>
                  <th className={`text-left px-4 py-3 font-medium ${c.textMuted}`}>Expires</th>
                  <th className={`text-left px-4 py-3 font-medium ${c.textMuted}`}>Last Override</th>
                  <th className="px-4 py-3" />
                </tr>
              </thead>
              <tbody className={`divide-y ${c.divide}`}>
                {items.map((sub: any) => (
                  <tr key={sub.clinic_id} className={c.panelHover}>
                    <td className="px-4 py-3">
                      <p className={`font-medium ${c.text}`}>{sub.clinic_name}</p>
                      <p className={`text-xs ${c.textFaint}`}>{sub.owner?.email}</p>
                    </td>
                    <td className={`px-4 py-3 capitalize ${c.text}`}>{sub.plan}</td>
                    <td className="px-4 py-3"><StatusBadge status={sub.status} /></td>
                    <td className={`px-4 py-3 ${c.textMuted}`}>
                      {sub.current_period_end ? new Date(sub.current_period_end).toLocaleDateString() : '—'}
                    </td>
                    <td className={`px-4 py-3 text-xs ${c.textFaint}`}>
                      {sub.admin_override ? (
                        <span title={sub.admin_override.reason ?? ''}>
                          {sub.admin_override.action.replace(/_/g, ' ')} · {new Date(sub.admin_override.granted_at).toLocaleDateString()}
                        </span>
                      ) : '—'}
                    </td>
                    <td className="px-4 py-3 text-right">
                      <button
                        onClick={() => openOverride(sub.clinic_id, sub.clinic_name)}
                        className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium bg-teal-600 hover:bg-teal-700 text-white"
                      >
                        <Settings2 className="w-3.5 h-3.5" /> Override
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {data && <Pagination page={page} setPage={setPage} total={data.total} limit={20} />}

      <Modal
        open={!!target}
        onClose={closeModal}
        title={target ? `Override — ${target.clinicName}` : 'Override'}
        footer={
          <>
            <SecondaryButton onClick={closeModal}>Cancel</SecondaryButton>
            <PrimaryButton
              onClick={() => overrideMutation.mutate()}
              disabled={
                overrideMutation.isPending
                || (['grant_temporary', 'extend'].includes(action) && !durationDays)
                || (action === 'set_expiration' && !expirationDate)
              }
            >
              {overrideMutation.isPending ? 'Applying...' : 'Apply Override'}
            </PrimaryButton>
          </>
        }
      >
        <FormField label="Action">
          <Select value={action} onChange={(e) => setAction(e.target.value as OverrideAction)}>
            {ACTION_OPTIONS.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
          </Select>
        </FormField>

        {['grant_free', 'grant_temporary', 'grant_lifetime'].includes(action) && (
          <FormField label="Plan (optional — keeps current plan if blank)">
            <Select value={plan} onChange={(e) => setPlan(e.target.value)}>
              <option value="">Keep current plan</option>
              {PLAN_OPTIONS.map((p) => <option key={p} value={p} className="capitalize">{p}</option>)}
            </Select>
          </FormField>
        )}

        {['grant_temporary', 'extend'].includes(action) && (
          <FormField label="Duration (days)">
            <TextInput type="number" min={1} value={durationDays} onChange={(e) => setDurationDays(e.target.value)} />
          </FormField>
        )}

        {action === 'set_expiration' && (
          <FormField label="New expiration date">
            <TextInput type="date" value={expirationDate} onChange={(e) => setExpirationDate(e.target.value)} />
          </FormField>
        )}

        {action === 'revoke' && (
          <p className="text-sm text-red-600">This immediately ends the clinic's access — appointments and booking will stop working until access is restored.</p>
        )}

        <FormField label="Administrative notes">
          <TextArea value={notes} onChange={(e) => setNotes(e.target.value)} placeholder="Internal context for other admins (optional)" rows={2} />
        </FormField>
        <FormField label="Override reason">
          <TextArea value={reason} onChange={(e) => setReason(e.target.value)} placeholder="Why is this override being made? (recorded in the audit log)" rows={2} />
        </FormField>
      </Modal>
    </div>
  );
}
