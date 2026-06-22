/**
 * Vitar — Admin Dashboard: Audit Log
 * Every action taken across Users, Clinics, and Subscriptions modules lands
 * here via app/services/audit_service.write_audit_log().
 */
import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { adminApi } from '@/lib/api/services';
import { useAdminTheme, SearchInput, Select, Pagination, EmptyState, LoadingState } from '@/components/admin/AdminUI';

export default function AdminAuditLogPage() {
  const { c } = useAdminTheme();
  const [action, setAction] = useState('');
  const [entityType, setEntityType] = useState('');
  const [page, setPage] = useState(1);

  const { data, isLoading } = useQuery({
    queryKey: ['admin', 'audit-logs', { action, entityType, page }],
    queryFn: () => adminApi.auditLogs.list({ action: action || undefined, entity_type: entityType || undefined, page, limit: 25 }),
  });

  const items = data?.items ?? [];

  return (
    <div className="p-6 space-y-4 max-w-7xl mx-auto">
      <div>
        <h1 className={`text-2xl font-bold ${c.text}`}>Audit Log</h1>
        <p className={`text-sm mt-1 ${c.textMuted}`}>{data?.total ?? 0} recorded administrative actions</p>
      </div>

      <div className="flex flex-col sm:flex-row gap-3">
        <div className="flex-1">
          <SearchInput value={action} onChange={(v) => { setAction(v); setPage(1); }} placeholder="Search by action (e.g. subscription.revoke)..." />
        </div>
        <Select value={entityType} onChange={(e) => { setEntityType(e.target.value); setPage(1); }} className="sm:w-44">
          <option value="">All entity types</option>
          <option value="user">User</option>
          <option value="clinic">Clinic</option>
          <option value="subscription">Subscription</option>
        </Select>
      </div>

      <div className={`rounded-xl border overflow-hidden ${c.panel}`}>
        {isLoading ? (
          <LoadingState message="Loading audit log..." />
        ) : items.length === 0 ? (
          <EmptyState message="No matching audit log entries" />
        ) : (
          <div className={`divide-y ${c.divide}`}>
            {items.map((entry: any) => (
              <div key={entry.id} className="px-5 py-4">
                <div className="flex items-start justify-between gap-3">
                  <div>
                    <p className={`text-sm font-medium capitalize ${c.text}`}>{entry.action.replace(/[._]/g, ' ')}</p>
                    <p className={`text-xs mt-0.5 ${c.textMuted}`}>
                      {entry.actor ? `${entry.actor.full_name} (${entry.actor.email})` : 'System'}
                      {entry.entity_type && ` · ${entry.entity_type}`}
                    </p>
                    {(entry.new_data?._reason || entry.new_data?._notes) && (
                      <p className={`text-xs mt-1 italic ${c.textFaint}`}>
                        {entry.new_data?._reason && <>“{entry.new_data._reason}”</>}
                        {entry.new_data?._notes && <> — {entry.new_data._notes}</>}
                      </p>
                    )}
                  </div>
                  <span className={`text-xs flex-shrink-0 ${c.textFaint}`}>
                    {entry.created_at ? new Date(entry.created_at).toLocaleString() : ''}
                  </span>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {data && <Pagination page={page} setPage={setPage} total={data.total} limit={25} />}
    </div>
  );
}
