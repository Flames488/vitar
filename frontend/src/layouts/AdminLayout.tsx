/**
 * Vitar — Admin Dashboard Layout
 *
 * Distinct shell from the clinic-facing DashboardLayout — deliberately so:
 * this is a platform control panel (Stripe/Linear/Vercel-style), not a
 * clinic's own dashboard. Superadmin route protection is handled one level
 * up by SuperadminRoute in App.tsx; this component is just chrome.
 */

import { useState } from 'react';
import { Outlet, NavLink, useNavigate, Link } from 'react-router-dom';
import {
  LayoutDashboard, Users, Building2, CreditCard, BarChart3,
  ScrollText, LogOut, Menu, X, Moon, Sun, ArrowLeft,
} from 'lucide-react';
import { useAuthStore } from '@/stores/authStore';
import VitarLogo from '@/components/shared/VitarLogo';
import { AdminThemeProvider, useAdminTheme } from '@/components/admin/AdminUI';

const NAV_ITEMS = [
  { to: '/admin/overview', label: 'Overview', icon: LayoutDashboard },
  { to: '/admin/users', label: 'Users', icon: Users },
  { to: '/admin/clinics', label: 'Clinics', icon: Building2 },
  { to: '/admin/subscriptions', label: 'Subscriptions', icon: CreditCard },
  { to: '/admin/analytics', label: 'Analytics', icon: BarChart3 },
  { to: '/admin/audit-log', label: 'Audit Log', icon: ScrollText },
];

function AdminShell() {
  const { user, logout } = useAuthStore();
  const { dark, toggle, c } = useAdminTheme();
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const navigate = useNavigate();

  const handleLogout = () => {
    logout();
    navigate('/login');
  };

  const SidebarContent = () => (
    <div className="flex flex-col h-full">
      <div className={`px-5 py-4 border-b ${dark ? 'border-slate-800' : 'border-slate-700'}`}>
        <div className="flex items-center gap-2.5">
          <VitarLogo size={32} />
          <div>
            <span className="text-white font-bold text-base leading-tight block">Vitar Admin</span>
            <span className="text-slate-400 text-xs leading-tight block">Control Panel</span>
          </div>
        </div>
      </div>

      <nav className="flex-1 px-3 py-4 overflow-y-auto space-y-1">
        {NAV_ITEMS.map(({ to, label, icon: Icon }) => (
          <NavLink
            key={to}
            to={to}
            onClick={() => setSidebarOpen(false)}
            className={({ isActive }) =>
              `flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium transition-colors ${
                isActive ? 'bg-teal-600 text-white' : 'text-slate-300 hover:bg-slate-700/60 hover:text-white'
              }`
            }
          >
            <Icon className="w-4 h-4 flex-shrink-0" />
            {label}
          </NavLink>
        ))}

        <div className={`pt-3 mt-3 border-t ${dark ? 'border-slate-800' : 'border-slate-700'}`}>
          <Link
            to="/dashboard"
            onClick={() => setSidebarOpen(false)}
            className="flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium text-slate-400 hover:bg-slate-700/60 hover:text-white transition-colors"
          >
            <ArrowLeft className="w-4 h-4 flex-shrink-0" />
            Exit to Clinic Dashboard
          </Link>
        </div>
      </nav>

      <div className={`px-3 py-4 border-t ${dark ? 'border-slate-800' : 'border-slate-700'}`}>
        <div className="flex items-center gap-3">
          <div className="w-8 h-8 rounded-full bg-purple-600 flex items-center justify-center text-white text-xs font-bold flex-shrink-0">
            {user?.full_name?.charAt(0).toUpperCase() ?? 'A'}
          </div>
          <div className="flex-1 min-w-0">
            <p className="text-white text-sm font-medium truncate">{user?.full_name}</p>
            <p className="text-slate-400 text-xs truncate">{user?.email}</p>
          </div>
          <button onClick={handleLogout} className="text-slate-400 hover:text-white transition-colors" title="Logout">
            <LogOut className="w-4 h-4" />
          </button>
        </div>
      </div>
    </div>
  );

  return (
    <div className={`flex h-screen overflow-hidden ${c.page}`}>
      <aside className={`hidden lg:flex w-64 flex-col flex-shrink-0 ${c.sidebarBg}`}>
        <SidebarContent />
      </aside>

      {sidebarOpen && (
        <div className="fixed inset-0 z-50 lg:hidden">
          <div className="absolute inset-0 bg-black/60" onClick={() => setSidebarOpen(false)} />
          <aside className={`relative w-64 h-full flex flex-col ${c.sidebarBg}`}>
            <button onClick={() => setSidebarOpen(false)} className="absolute top-4 right-4 text-slate-400 hover:text-white">
              <X className="w-5 h-5" />
            </button>
            <SidebarContent />
          </aside>
        </div>
      )}

      <div className="flex-1 flex flex-col overflow-hidden">
        <header className={`flex items-center justify-between px-4 lg:px-6 h-14 border-b flex-shrink-0 ${c.panel}`}>
          <button onClick={() => setSidebarOpen(true)} className={`lg:hidden ${c.textMuted}`}>
            <Menu className="w-5 h-5" />
          </button>
          <span className={`hidden lg:block text-sm font-medium ${c.textMuted}`}>
            Superadmin Control Panel
          </span>
          <button
            onClick={toggle}
            className={`flex items-center gap-2 px-3 py-1.5 rounded-lg text-xs font-medium border transition-colors ${c.border} ${c.textMuted} ${c.panelHover}`}
            title="Toggle dark mode"
          >
            {dark ? <Sun className="w-3.5 h-3.5" /> : <Moon className="w-3.5 h-3.5" />}
            {dark ? 'Light' : 'Dark'}
          </button>
        </header>

        <main className="flex-1 overflow-y-auto">
          <Outlet />
        </main>
      </div>
    </div>
  );
}

export default function AdminLayout() {
  return (
    <AdminThemeProvider>
      <AdminShell />
    </AdminThemeProvider>
  );
}
