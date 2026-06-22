/**
 * Vitar — Admin Dashboard: User Management
 * Module 2 of the spec: table, search/filter/sort/paginate, role + status actions.
 *
 * Note on roles: the schema has one boolean (User.is_superadmin), not a
 * three-tier system, so Promote/Demote and Grant/Revoke Superadmin are the
 * same action here — see admin_users.py for the reasoning.
 */
import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { ArrowUpDown, Eye, ShieldCheck, ShieldOff, Ban, CheckCircle2, Gift } from 'lucide-react';
import { adminApi } from '@/lib/api/services';
import { getApiError } from '@/lib/api/client';
import {
  useAdminTheme, SearchInput, Select, Pagination, StatusBadge,
  EmptyState, LoadingState, Modal, TextArea, PrimaryButton, DangerButton, SecondaryButton,
} from '@/components/admin/AdminUI';

type RoleAction = { userId: string; userName: string; nextValue: boolean; kind: 'role' };
type StatusAction = { userId: string; userName: string; nextValue: boolean; kind: 'status' };
type FreeAccessAction = { userId: string; userName: string; clinicId: string | null; kind: 'free_access' };
type PendingAction = RoleAction | StatusAction | FreeAccessAction | null;

export default function AdminUsersPage() {
  const { c } = useAdminTheme();
  const queryClient = useQueryClient();

  const [search, setSearch] = useState('');
  const [role, setRole] = useState('');
  const [status, setStatus] = useState('');
  const [sortBy, setSortBy] = useState('created_at');
  const [sortDir, setSortDir] = useState<'asc' | 'desc'>('desc');
  const [page, setPage] = useState(1);
  const [detailUserId, setDetailUserId] = useState<string | null>(null);
  const [pending, setPending] = useState<PendingAction>(null);
  const [reason, setReason] = useState('');
  const [freeAccessPlan, setFreeAccessPlan] = useState('pro');

  const { data, isLoading } = useQuery({
    queryKey: ['admin', 'users', { search, role, status, sortBy, sortDir, page }],
    queryFn: () => adminApi.users.list({
      search: search || undefined, role: role || undefined, status: status || undefined,
      sort_by: sortBy, sort_dir: sortDir, page, limit: 20,
    }),
  });

  const { data: detail } = useQuery({
    queryKey: ['admin', 'user', detailUserId],
    queryFn: () => adminApi.users.get(detailUserId!),
    enabled: !!detailUserId,
  });

  const roleMutation = useMutation({
    mutationFn: ({ userId, nextValue }: { userId: string; nextValue: boolean }) =>
      adminApi.users.updateRole(userId, nextValue, reason || undefined),
    onSuccess: () => {
      toast.success('Role updated');
      queryClient.invalidateQueries({ queryKey: ['admin', 'users'] });
      setPending(null); setReason('');
    },
    onError: (err) => toast.error(getApiError(err)),
  });

  const statusMutation = useMutation({
    mutationFn: ({ userId, nextValue }: { userId: string; nextValue: boolean }) =>
      adminApi.users.updateStatus(userId, nextValue, reason || undefined),
    onSuccess: () => {
      toast.success('Status updated');
      queryClient.invalidateQueries({ queryKey: ['admin', 'users'] });
      setPending(null); setReason('');
    },
    onError: (err) => toast.error(getApiError(err)),
  });

  const freeAccessMutation = useMutation({
    mutationFn: ({ userId }: { userId: string }) =>
      adminApi.users.grantFreeAccess(userId, freeAccessPlan, reason || 'Admin granted free access'),
    onSuccess: () => {
      toast.success('Free access granted — subscription is now active');
      queryClient.invalidateQueries({ queryKey: ['admin', 'users'] });
      queryClient.invalidateQueries({ queryKey: ['admin', 'subscriptions'] });
      setPending(null); setReason(''); setFreeAccessPlan('pro');
    },
    onError: (err) => toast.error(getApiError(err)),
  });

  const items = data?.items ?? [];

  const toggleSort = (col: string) => {
    if (sortBy === col) setSortDir((d) => (d === 'asc' ? 'desc' : 'asc'));
    else { setSortBy(col); setSortDir('desc'); }
  };

  const confirmAction = () => {
    if (!pending) return;
    if (pending.kind === 'role') roleMutation.mutate({ userId: pending.userId, nextValue: pending.nextValue });
    else if (pending.kind === 'status') statusMutation.mutate({ userId: pending.userId, nextValue: pending.nextValue });
    else if (pending.kind === 'free_access') freeAccessMutation.mutate({ userId: pending.userId });
  };

  const COLUMNS: { key: string; label: string; sortable?: boolean }[] = [
    { key: 'full_name', label: 'Name', sortable: true },
    { key: 'email', label: 'Email', sortable: true },
    { key: 'role', label: 'Role' },
    { key: 'subscription_status', label: 'Subscription' },
    { key: 'created_at', label: 'Registered', sortable: true },
    { key: 'actions', label: '' },
  ];

  return (
    <div className="p-6 space-y-4 max-w-7xl mx-auto">
      <div>
        <h1 className={`text-2xl font-bold ${c.text}`}>Users</h1>
        <p className={`text-sm mt-1 ${c.textMuted}`}>
          {data?.total ?? 0} registered accounts
          {data?.items && (
            <span className="ml-2 inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium bg-teal-100 text-teal-800">
              {data.items.filter((u: any) => u.is_active).length} active on this page
            </span>
          )}
        </p>
      </div>

      <div className="flex flex-col sm:flex-row gap-3">
        <div className="flex-1">
          <SearchInput value={search} onChange={(v) => { setSearch(v); setPage(1); }} placeholder="Search by name or email..." />
        </div>
        <Select value={role} onChange={(e) => { setRole(e.target.value); setPage(1); }} className="sm:w-40">
          <option value="">All roles</option>
          <option value="user">User</option>
          <option value="superadmin">Superadmin</option>
        </Select>
        <Select value={status} onChange={(e) => { setStatus(e.target.value); setPage(1); }} className="sm:w-40">
          <option value="">All statuses</option>
          <option value="active">Active</option>
          <option value="suspended">Suspended</option>
        </Select>
      </div>

      <div className={`rounded-xl border overflow-hidden ${c.panel}`}>
        {isLoading ? (
          <LoadingState message="Loading users..." />
        ) : items.length === 0 ? (
          <EmptyState message="No users found" />
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className={`border-b ${c.border}`}>
                  {COLUMNS.map((col) => (
                    <th key={col.key} className={`text-left px-4 py-3 font-medium ${c.textMuted}`}>
                      {col.sortable ? (
                        <button onClick={() => toggleSort(col.key)} className="flex items-center gap-1 hover:text-teal-600">
                          {col.label} <ArrowUpDown className="w-3 h-3" />
                        </button>
                      ) : col.label}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody className={`divide-y ${c.divide}`}>
                {items.map((u: any) => (
                  <tr key={u.id} className={c.panelHover}>
                    <td className={`px-4 py-3 font-medium ${c.text}`}>{u.full_name}</td>
                    <td className={`px-4 py-3 ${c.textMuted}`}>{u.email}</td>
                    <td className="px-4 py-3"><StatusBadge status={u.role} /></td>
                    <td className="px-4 py-3">
                      {u.subscription_status ? <StatusBadge status={u.subscription_status} /> : <span className={c.textFaint}>—</span>}
                    </td>
                    <td className={`px-4 py-3 ${c.textMuted}`}>
                      {u.registered_at ? new Date(u.registered_at).toLocaleString() : '—'}
                    </td>
                    <td className="px-4 py-3">
                      <div className="flex items-center gap-2 justify-end">
                        <button onClick={() => setDetailUserId(u.id)} title="View details" className="text-slate-400 hover:text-teal-600">
                          <Eye className="w-4 h-4" />
                        </button>
                        <button
                          onClick={() => setPending({ kind: 'free_access', userId: u.id, userName: u.full_name, clinicId: u.clinic_id ?? null })}
                          title="Grant free access"
                          className="text-slate-400 hover:text-green-600"
                        >
                          <Gift className="w-4 h-4" />
                        </button>
                        <button
                          onClick={() => setPending({ kind: 'role', userId: u.id, userName: u.full_name, nextValue: !u.is_superadmin })}
                          title={u.is_superadmin ? 'Revoke superadmin' : 'Grant superadmin'}
                          className={u.is_superadmin ? 'text-purple-600 hover:text-purple-800' : 'text-slate-400 hover:text-purple-600'}
                        >
                          {u.is_superadmin ? <ShieldOff className="w-4 h-4" /> : <ShieldCheck className="w-4 h-4" />}
                        </button>
                        <button
                          onClick={() => setPending({ kind: 'status', userId: u.id, userName: u.full_name, nextValue: !u.is_active })}
                          title={u.is_active ? 'Suspend' : 'Reactivate'}
                          className={u.is_active ? 'text-slate-400 hover:text-red-600' : 'text-green-600 hover:text-green-800'}
                        >
                          {u.is_active ? <Ban className="w-4 h-4" /> : <CheckCircle2 className="w-4 h-4" />}
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {data && <Pagination page={page} setPage={setPage} total={data.total} limit={20} />}

      {/* Confirm role/status/free-access change */}
      <Modal
        open={!!pending}
        onClose={() => { setPending(null); setReason(''); setFreeAccessPlan('pro'); }}
        title={
          pending?.kind === 'role'
            ? (pending.nextValue ? 'Grant superadmin access?' : 'Revoke superadmin access?')
            : pending?.kind === 'free_access'
            ? 'Grant Free Access'
            : (pending?.nextValue ? 'Reactivate account?' : 'Suspend account?')
        }
        danger={pending?.kind === 'status' && (pending as StatusAction).nextValue === false}
        footer={
          <>
            <SecondaryButton onClick={() => { setPending(null); setReason(''); setFreeAccessPlan('pro'); }}>Cancel</SecondaryButton>
            {pending?.kind === 'status' && (pending as StatusAction).nextValue === false ? (
              <DangerButton onClick={confirmAction} disabled={roleMutation.isPending || statusMutation.isPending}>
                Suspend
              </DangerButton>
            ) : (
              <PrimaryButton onClick={confirmAction} disabled={roleMutation.isPending || statusMutation.isPending || freeAccessMutation.isPending}>
                {freeAccessMutation.isPending ? 'Granting...' : 'Confirm'}
              </PrimaryButton>
            )}
          </>
        }
      >
        {pending?.kind === 'free_access' ? (
          <div className="space-y-3">
            <p className={`text-sm ${c.textMuted}`}>
              Grant <span className={`font-medium ${c.text}`}>{pending.userName}</span> free access with no billing required.
              This sets their subscription to <strong>Active</strong> with ₦0 amount.
            </p>
            {!pending.clinicId && (
              <p className="text-sm text-amber-600 bg-amber-50 rounded-lg px-3 py-2">
                ⚠️ This user has no clinic yet. They need to complete registration first.
              </p>
            )}
            <div>
              <label className={`block text-xs font-medium mb-1 ${c.textMuted}`}>Plan to grant</label>
              <select
                value={freeAccessPlan}
                onChange={(e) => setFreeAccessPlan(e.target.value)}
                className={`w-full px-3 py-2 rounded-lg border text-sm ${c.border} ${c.panel} ${c.text}`}
              >
                <option value="basic">Starter (Basic)</option>
                <option value="pro">Pro</option>
                <option value="enterprise">Enterprise</option>
              </select>
            </div>
            <TextArea
              value={reason}
              onChange={(e) => setReason(e.target.value)}
              placeholder="Reason for free access (recorded in audit log)"
              rows={2}
            />
          </div>
        ) : (
          <>
            <p className={`text-sm ${c.textMuted}`}>
              {pending && <>This applies to <span className={`font-medium ${c.text}`}>{pending.userName}</span>. The action is logged to the audit trail.</>}
            </p>
            <TextArea
              value={reason}
              onChange={(e) => setReason(e.target.value)}
              placeholder="Reason (optional, recorded in the audit log)"
              rows={2}
            />
          </>
        )}
      </Modal>

      {/* User detail */}
      <Modal open={!!detailUserId} onClose={() => setDetailUserId(null)} title="User Details">
        {!detail ? (
          <LoadingState />
        ) : (
          <div className="space-y-3 text-sm">
            <div className="flex justify-between"><span className={c.textMuted}>Name</span><span className={c.text}>{detail.full_name}</span></div>
            <div className="flex justify-between"><span className={c.textMuted}>Email</span><span className={c.text}>{detail.email}</span></div>
            <div className="flex justify-between"><span className={c.textMuted}>Role</span><StatusBadge status={detail.role} /></div>
            <div className="flex justify-between"><span className={c.textMuted}>Status</span><StatusBadge status={detail.is_active ? 'active' : 'suspended'} /></div>
            <div className="flex justify-between"><span className={c.textMuted}>Clinic</span><span className={c.text}>{detail.clinic?.name ?? '—'}</span></div>
            {detail.subscription && (
              <>
                <div className="flex justify-between"><span className={c.textMuted}>Plan</span><span className={`capitalize ${c.text}`}>{detail.subscription.plan}</span></div>
                <div className="flex justify-between"><span className={c.textMuted}>Subscription</span><StatusBadge status={detail.subscription.status} /></div>
                <div className="flex justify-between"><span className={c.textMuted}>Expires</span><span className={c.text}>{detail.subscription.current_period_end ? new Date(detail.subscription.current_period_end).toLocaleDateString() : '—'}</span></div>
              </>
            )}
            <div className="flex justify-between"><span className={c.textMuted}>Last login</span><span className={c.text}>{detail.last_login_at ? new Date(detail.last_login_at).toLocaleString() : 'Never'}</span></div>
          </div>
        )}
      </Modal>
    </div>
  );
}
