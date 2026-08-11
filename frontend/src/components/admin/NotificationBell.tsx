/**
 * Vitar — Admin Notification Bell (AI Core)
 *
 * Reads from the shared agent_notifications table — the same source the
 * Telegram bot (Phase 7) independently reads from. This component never
 * creates a notification, only reads/marks-read ones agents already wrote
 * via app/services/notifications.py's notify().
 */
import { useState, useRef, useEffect } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import { Bell } from 'lucide-react';
import { adminApi } from '@/lib/api/services';
import { useAdminTheme } from '@/components/admin/AdminUI';

const AGENT_ICON: Record<string, string> = {
  lead_hunter: '🎯',
  sales_agent: '✍️',
  content_agent: '📝',
  customer_success: '⚠️',
};

function timeAgo(iso: string | null): string {
  if (!iso) return '';
  const diffMs = Date.now() - new Date(iso).getTime();
  const mins = Math.floor(diffMs / 60000);
  if (mins < 1) return 'just now';
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `${hrs}h ago`;
  return `${Math.floor(hrs / 24)}d ago`;
}

export default function NotificationBell() {
  const { c, dark } = useAdminTheme();
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  const navigate = useNavigate();
  const qc = useQueryClient();

  const { data: unreadData } = useQuery({
    queryKey: ['admin', 'notifications', 'unread-count'],
    queryFn: adminApi.notifications.unreadCount,
    refetchInterval: 20_000,
  });
  const unreadCount = unreadData?.count ?? 0;

  const { data: listData } = useQuery({
    queryKey: ['admin', 'notifications', 'list'],
    queryFn: () => adminApi.notifications.list({ limit: 20 }),
    enabled: open,
  });
  const notifications = listData?.notifications ?? [];

  useEffect(() => {
    function onClickOutside(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    }
    document.addEventListener('mousedown', onClickOutside);
    return () => document.removeEventListener('mousedown', onClickOutside);
  }, []);

  const invalidateNotifs = () => {
    qc.invalidateQueries({ queryKey: ['admin', 'notifications'] });
  };

  const handleClick = async (n: any) => {
    if (!n.is_read) {
      await adminApi.notifications.markRead(n.id);
      invalidateNotifs();
    }
    setOpen(false);
    if (n.link_path) navigate(n.link_path);
  };

  const handleMarkAllRead = async () => {
    await adminApi.notifications.markAllRead();
    invalidateNotifs();
  };

  return (
    <div className="relative" ref={ref}>
      <button
        onClick={() => setOpen((v) => !v)}
        className={`relative p-2 rounded-lg transition-colors ${c.panelHover} ${c.textMuted}`}
        title="Notifications"
      >
        <Bell className="w-4 h-4" />
        {unreadCount > 0 && (
          <span className="absolute -top-0.5 -right-0.5 min-w-[16px] h-4 px-1 rounded-full bg-red-500 text-white text-[10px] font-bold flex items-center justify-center">
            {unreadCount > 99 ? '99+' : unreadCount}
          </span>
        )}
      </button>

      {open && (
        <div className={`absolute right-0 mt-2 w-80 max-h-96 overflow-y-auto rounded-xl border shadow-xl z-50 ${c.panel}`}>
          <div className={`flex items-center justify-between px-4 py-3 border-b ${c.border}`}>
            <span className={`text-sm font-bold ${c.text}`}>Notifications</span>
            {unreadCount > 0 && (
              <button onClick={handleMarkAllRead} className="text-xs font-medium text-teal-500 hover:text-teal-400">
                Mark all read
              </button>
            )}
          </div>
          {notifications.length === 0 ? (
            <div className={`py-10 text-center text-sm ${c.textFaint}`}>No notifications yet</div>
          ) : (
            <div className={`divide-y ${c.divide}`}>
              {notifications.map((n: any) => (
                <button
                  key={n.id}
                  onClick={() => handleClick(n)}
                  className={`w-full text-left px-4 py-3 transition-colors ${c.panelHover} ${
                    !n.is_read ? (dark ? 'bg-teal-500/5' : 'bg-teal-50/50') : ''
                  }`}
                >
                  <div className="flex items-start gap-2.5">
                    <span className="text-base flex-shrink-0 mt-0.5">{AGENT_ICON[n.agent_name] ?? '🔔'}</span>
                    <div className="flex-1 min-w-0">
                      <p className={`text-sm leading-snug ${!n.is_read ? `font-semibold ${c.text}` : c.textMuted}`}>
                        {n.message}
                      </p>
                      <p className={`text-xs mt-0.5 ${c.textFaint}`}>{timeAgo(n.created_at)}</p>
                    </div>
                    {!n.is_read && <span className="w-2 h-2 rounded-full bg-teal-500 flex-shrink-0 mt-1.5" />}
                  </div>
                </button>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
