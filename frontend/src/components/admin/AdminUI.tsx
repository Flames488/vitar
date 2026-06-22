/**
 * Vitar — Admin Dashboard: Shared UI Building Blocks
 *
 * Dark/light mode here is implemented with plain conditional class strings
 * (not Tailwind's `dark:` variant) because tailwind.config.js wasn't part
 * of the audited codebase, so we can't assume `darkMode: 'class'` is set.
 * If it already is, these can be simplified later — functionally identical
 * either way.
 *
 * Persisted to localStorage under 'vitar_admin_theme' (admin-section only,
 * separate from the rest of the app which has no dark mode).
 */

import { createContext, useContext, useEffect, useState, type ReactNode } from 'react';
import { Search, X } from 'lucide-react';

// ── Theme ────────────────────────────────────────────────────────────────────

interface AdminTheme {
  dark: boolean;
  toggle: () => void;
  c: {
    page: string;
    panel: string;
    panelHover: string;
    text: string;
    textMuted: string;
    textFaint: string;
    border: string;
    divide: string;
    input: string;
    sidebarBg: string;
  };
}

const AdminThemeContext = createContext<AdminTheme | null>(null);

function buildClasses(dark: boolean): AdminTheme['c'] {
  return {
    page: dark ? 'bg-slate-950 text-slate-100' : 'bg-slate-50 text-slate-900',
    panel: dark ? 'bg-slate-900 border-slate-800' : 'bg-white border-slate-200',
    panelHover: dark ? 'hover:bg-slate-800/60' : 'hover:bg-slate-50',
    text: dark ? 'text-slate-100' : 'text-slate-900',
    textMuted: dark ? 'text-slate-400' : 'text-slate-500',
    textFaint: dark ? 'text-slate-500' : 'text-slate-400',
    border: dark ? 'border-slate-800' : 'border-slate-200',
    divide: dark ? 'divide-slate-800' : 'divide-slate-100',
    input: dark
      ? 'bg-slate-900 border-slate-700 text-slate-100 placeholder:text-slate-500'
      : 'bg-white border-slate-300 text-slate-900 placeholder:text-slate-400',
    sidebarBg: dark ? 'bg-black' : 'bg-slate-800',
  };
}

export function AdminThemeProvider({ children }: { children: ReactNode }) {
  const [dark, setDark] = useState<boolean>(() => {
    try {
      return localStorage.getItem('vitar_admin_theme') === 'dark';
    } catch {
      return false;
    }
  });

  useEffect(() => {
    try {
      localStorage.setItem('vitar_admin_theme', dark ? 'dark' : 'light');
    } catch {
      // ignore (private browsing etc.)
    }
  }, [dark]);

  const value: AdminTheme = {
    dark,
    toggle: () => setDark((d) => !d),
    c: buildClasses(dark),
  };

  return <AdminThemeContext.Provider value={value}>{children}</AdminThemeContext.Provider>;
}

export function useAdminTheme(): AdminTheme {
  const ctx = useContext(AdminThemeContext);
  if (!ctx) throw new Error('useAdminTheme must be used within AdminThemeProvider');
  return ctx;
}

// ── KPI Card ─────────────────────────────────────────────────────────────────

const TINTS: Record<string, { light: string; dark: string }> = {
  teal: { light: 'bg-teal-50 text-teal-600', dark: 'bg-teal-500/10 text-teal-400' },
  blue: { light: 'bg-blue-50 text-blue-600', dark: 'bg-blue-500/10 text-blue-400' },
  green: { light: 'bg-green-50 text-green-600', dark: 'bg-green-500/10 text-green-400' },
  amber: { light: 'bg-amber-50 text-amber-600', dark: 'bg-amber-500/10 text-amber-400' },
  red: { light: 'bg-red-50 text-red-600', dark: 'bg-red-500/10 text-red-400' },
  purple: { light: 'bg-purple-50 text-purple-600', dark: 'bg-purple-500/10 text-purple-400' },
};

export function KpiCard({
  label, value, sub, icon: Icon, tint = 'teal', nairaIcon,
}: {
  label: string; value: string | number; sub?: string;
  icon: React.ComponentType<{ className?: string }> | null; tint?: keyof typeof TINTS;
  nairaIcon?: boolean;
}) {
  const { dark, c } = useAdminTheme();
  const tintClass = dark ? TINTS[tint].dark : TINTS[tint].light;
  return (
    <div className={`rounded-xl border p-5 ${c.panel}`}>
      <div className="flex items-start justify-between">
        <div>
          <p className={`text-sm ${c.textMuted}`}>{label}</p>
          <p className={`text-2xl font-bold mt-1 ${c.text}`}>{value}</p>
          {sub && <p className={`text-xs mt-1 ${c.textFaint}`}>{sub}</p>}
        </div>
        <div className={`w-10 h-10 rounded-xl flex items-center justify-center flex-shrink-0 ${tintClass}`}>
          {(nairaIcon || !Icon) ? <span className="text-lg font-bold">₦</span> : <Icon className="w-5 h-5" />}
        </div>
      </div>
    </div>
  );
}

export function KpiCardSkeleton() {
  const { c } = useAdminTheme();
  return (
    <div className={`rounded-xl border p-5 animate-pulse ${c.panel}`}>
      <div className={`h-3 w-24 rounded ${c.border} bg-current opacity-10`} />
      <div className={`h-7 w-16 rounded mt-3 ${c.border} bg-current opacity-10`} />
      <div className={`h-2.5 w-20 rounded mt-3 ${c.border} bg-current opacity-10`} />
    </div>
  );
}

// ── Status Badge ─────────────────────────────────────────────────────────────

const STATUS_TINTS: Record<string, string> = {
  active: 'bg-green-100 text-green-700',
  trialing: 'bg-blue-100 text-blue-700',
  past_due: 'bg-amber-100 text-amber-700',
  cancelled: 'bg-red-100 text-red-700',
  expired: 'bg-slate-200 text-slate-600',
  suspended: 'bg-red-100 text-red-700',
  superadmin: 'bg-purple-100 text-purple-700',
  user: 'bg-slate-100 text-slate-600',
  disabled: 'bg-red-100 text-red-700',
};

export function StatusBadge({ status }: { status: string }) {
  const tint = STATUS_TINTS[status] ?? 'bg-slate-100 text-slate-600';
  return (
    <span className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium capitalize ${tint}`}>
      {status.replace(/_/g, ' ')}
    </span>
  );
}

// ── Toggle Switch ────────────────────────────────────────────────────────────

export function ToggleSwitch({
  checked, onChange, disabled,
}: { checked: boolean; onChange: () => void; disabled?: boolean }) {
  return (
    <button
      type="button"
      onClick={onChange}
      disabled={disabled}
      className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors flex-shrink-0 disabled:opacity-50 ${
        checked ? 'bg-teal-600' : 'bg-slate-300'
      }`}
    >
      <span
        className={`inline-block h-4 w-4 transform rounded-full bg-white transition-transform shadow ${
          checked ? 'translate-x-6' : 'translate-x-1'
        }`}
      />
    </button>
  );
}

// ── Search Input ─────────────────────────────────────────────────────────────

export function SearchInput({
  value, onChange, placeholder = 'Search...',
}: { value: string; onChange: (v: string) => void; placeholder?: string }) {
  const { c } = useAdminTheme();
  return (
    <div className="relative">
      <Search className={`absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 ${c.textFaint}`} />
      <input
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        className={`w-full pl-9 pr-3 py-2.5 border rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-teal-500 ${c.input}`}
      />
    </div>
  );
}

// ── Pagination ───────────────────────────────────────────────────────────────

export function Pagination({
  page, setPage, total, limit,
}: { page: number; setPage: (p: number) => void; total: number; limit: number }) {
  const totalPages = Math.max(1, Math.ceil(total / limit));
  if (totalPages <= 1) return null;
  return (
    <div className="flex items-center justify-center gap-2">
      <button
        onClick={() => setPage(Math.max(1, page - 1))}
        disabled={page === 1}
        className="px-3 py-1.5 border border-slate-300 rounded-lg text-sm disabled:opacity-40"
      >
        ← Prev
      </button>
      <span className="px-3 py-1.5 text-sm text-slate-500">
        Page {page} of {totalPages} · {total} total
      </span>
      <button
        onClick={() => setPage(Math.min(totalPages, page + 1))}
        disabled={page >= totalPages}
        className="px-3 py-1.5 border border-slate-300 rounded-lg text-sm disabled:opacity-40"
      >
        Next →
      </button>
    </div>
  );
}

// ── Empty State ──────────────────────────────────────────────────────────────

export function EmptyState({ message }: { message: string }) {
  const { c } = useAdminTheme();
  return <div className={`py-12 text-center text-sm ${c.textFaint}`}>{message}</div>;
}

export function LoadingState({ message = 'Loading...' }: { message?: string }) {
  const { c } = useAdminTheme();
  return <div className={`py-12 text-center text-sm ${c.textFaint}`}>{message}</div>;
}

// ── Modal ────────────────────────────────────────────────────────────────────

export function Modal({
  open, onClose, title, children, footer, danger,
}: {
  open: boolean; onClose: () => void; title: string;
  children: ReactNode; footer?: ReactNode; danger?: boolean;
}) {
  const { c } = useAdminTheme();
  if (!open) return null;
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center px-4">
      <div className="absolute inset-0 bg-black/50" onClick={onClose} />
      <div className={`relative w-full max-w-md rounded-xl border shadow-xl ${c.panel}`}>
        <div className={`flex items-center justify-between px-5 py-4 border-b ${c.border}`}>
          <h3 className={`font-semibold ${danger ? 'text-red-600' : c.text}`}>{title}</h3>
          <button onClick={onClose} className={c.textFaint}>
            <X className="w-4 h-4" />
          </button>
        </div>
        <div className="px-5 py-4 space-y-4">{children}</div>
        {footer && <div className={`flex justify-end gap-2 px-5 py-4 border-t ${c.border}`}>{footer}</div>}
      </div>
    </div>
  );
}

// ── Form bits used inside modals ────────────────────────────────────────────

export function FormField({
  label, children,
}: { label: string; children: ReactNode }) {
  const { c } = useAdminTheme();
  return (
    <div>
      <label className={`block text-sm font-medium mb-1 ${c.text}`}>{label}</label>
      {children}
    </div>
  );
}

export function TextInput(props: React.InputHTMLAttributes<HTMLInputElement>) {
  const { c } = useAdminTheme();
  return (
    <input
      {...props}
      className={`w-full px-3 py-2 border rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-teal-500 ${c.input} ${props.className ?? ''}`}
    />
  );
}

export function TextArea(props: React.TextareaHTMLAttributes<HTMLTextAreaElement>) {
  const { c } = useAdminTheme();
  return (
    <textarea
      {...props}
      className={`w-full px-3 py-2 border rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-teal-500 ${c.input} ${props.className ?? ''}`}
    />
  );
}

export function Select(props: React.SelectHTMLAttributes<HTMLSelectElement>) {
  const { c } = useAdminTheme();
  return (
    <select
      {...props}
      className={`w-full px-3 py-2 border rounded-lg text-sm bg-white focus:outline-none focus:ring-2 focus:ring-teal-500 ${c.input} ${props.className ?? ''}`}
    />
  );
}

export function PrimaryButton(props: React.ButtonHTMLAttributes<HTMLButtonElement>) {
  return (
    <button
      {...props}
      className={`px-4 py-2 rounded-lg text-sm font-semibold transition-colors bg-teal-600 hover:bg-teal-700 text-white disabled:opacity-50 ${props.className ?? ''}`}
    />
  );
}

export function DangerButton(props: React.ButtonHTMLAttributes<HTMLButtonElement>) {
  return (
    <button
      {...props}
      className={`px-4 py-2 rounded-lg text-sm font-semibold transition-colors bg-red-600 hover:bg-red-700 text-white disabled:opacity-50 ${props.className ?? ''}`}
    />
  );
}

export function SecondaryButton(props: React.ButtonHTMLAttributes<HTMLButtonElement>) {
  const { c } = useAdminTheme();
  return (
    <button
      {...props}
      className={`px-4 py-2 rounded-lg text-sm font-medium transition-colors border ${c.border} ${c.text} ${c.panelHover} disabled:opacity-50 ${props.className ?? ''}`}
    />
  );
}
