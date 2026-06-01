/**
 * Vitar v5 - Dashboard Layout
 * Sidebar nav, trial banner, AI chatbot, mobile responsive
 */

import { useState } from 'react';
import { Outlet, NavLink, useNavigate } from 'react-router-dom';
import {
  LayoutDashboard, Calendar, Users, UserCheck, BarChart3,
  DollarSign, Settings, Brain, Clock, Bell, LogOut, Menu,
  X, ChevronRight, AlertTriangle, MessageSquare, ListOrdered, Key,
} from 'lucide-react';
import { useAuthStore } from '@/stores/authStore';
import { useGeoStore } from '@/stores/geoStore';
import AIChatbot from '@/components/ai/AIChatbot';
import TrialBanner from '@/components/shared/TrialBanner';

const NAV_ITEMS = [
  { to: '/dashboard',     label: 'Dashboard',     icon: LayoutDashboard },
  { to: '/appointments',  label: 'Appointments',  icon: Calendar },
  { to: '/doctors',       label: 'Doctors',       icon: UserCheck },
  { to: '/patients',      label: 'Patients',      icon: Users },
  { to: '/ai-risk',       label: 'AI Risk',       icon: Brain },
  { to: '/waiting-list',  label: 'Waiting List',  icon: ListOrdered },
  { to: '/analytics',     label: 'Analytics',     icon: BarChart3 },
  { to: '/earnings',      label: 'Earnings',      icon: DollarSign },
];

const SETTINGS_ITEMS = [
  { to: '/settings',               label: 'General',       icon: Settings },
  { to: '/settings/billing',       label: 'Billing',       icon: DollarSign },
  { to: '/settings/notifications', label: 'Notifications', icon: Bell },
  { to: '/settings/booking-page',  label: 'Booking Page',  icon: Clock },
  { to: '/settings/api-keys',      label: 'API Keys',      icon: Key },
];

export default function DashboardLayout() {
  const { user, clinic, logout } = useAuthStore();
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [chatOpen, setChatOpen] = useState(false);
  const navigate = useNavigate();

  const trial = clinic?.trial;
  const showTrialBanner = trial?.is_trial && (trial?.show_upgrade_nudge || (trial?.days_left ?? 99) <= 3);

  const handleLogout = () => {
    logout();
    navigate('/login');
  };

  const SidebarContent = () => (
    <div className="flex flex-col h-full">
      {/* Logo */}
      <div className="px-6 py-5 border-b border-slate-700">
        <div className="flex items-center gap-2">
          <div className="w-8 h-8 bg-teal-500 rounded-lg flex items-center justify-center">
            <span className="text-white font-bold text-sm">V</span>
          </div>
          <span className="text-white font-bold text-lg">Vitar</span>
        </div>
        {clinic && (
          <p className="text-slate-400 text-xs mt-1 truncate">{clinic.name}</p>
        )}
      </div>

      {/* Nav */}
      <nav className="flex-1 px-3 py-4 overflow-y-auto space-y-1">
        <p className="px-3 text-xs font-semibold text-slate-500 uppercase tracking-wider mb-2">Main</p>
        {NAV_ITEMS.map(({ to, label, icon: Icon }) => (
          <NavLink
            key={to}
            to={to}
            onClick={() => setSidebarOpen(false)}
            className={({ isActive }) =>
              `flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium transition-colors ${
                isActive
                  ? 'bg-teal-600 text-white'
                  : 'text-slate-300 hover:bg-slate-700 hover:text-white'
              }`
            }
          >
            <Icon className="w-4 h-4 flex-shrink-0" />
            {label}
          </NavLink>
        ))}

        <p className="px-3 text-xs font-semibold text-slate-500 uppercase tracking-wider mt-4 mb-2">Settings</p>
        {SETTINGS_ITEMS.map(({ to, label, icon: Icon }) => (
          <NavLink
            key={to}
            to={to}
            end
            onClick={() => setSidebarOpen(false)}
            className={({ isActive }) =>
              `flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium transition-colors ${
                isActive
                  ? 'bg-teal-600 text-white'
                  : 'text-slate-300 hover:bg-slate-700 hover:text-white'
              }`
            }
          >
            <Icon className="w-4 h-4 flex-shrink-0" />
            {label}
          </NavLink>
        ))}
      </nav>

      {/* Trial status in sidebar */}
      {trial?.is_trial && (
        <div className="px-3 pb-2">
          <div className="bg-amber-900/40 border border-amber-700/50 rounded-lg p-3">
            <div className="flex items-center gap-2 mb-1">
              <AlertTriangle className="w-3.5 h-3.5 text-amber-400" />
              <span className="text-amber-300 text-xs font-medium">Trial</span>
            </div>
            <p className="text-amber-200 text-xs">{trial.days_left} days left</p>
            <p className="text-amber-300/70 text-xs">{trial.bookings_used}/{trial.bookings_limit} bookings</p>
            <button
              onClick={() => { navigate('/settings/billing'); setSidebarOpen(false); }}
              className="mt-2 w-full bg-amber-600 hover:bg-amber-500 text-white text-xs font-medium py-1.5 rounded transition-colors"
            >
              Upgrade Now
            </button>
          </div>
        </div>
      )}

      {/* User */}
      <div className="px-3 py-4 border-t border-slate-700">
        <div className="flex items-center gap-3">
          <div className="w-8 h-8 rounded-full bg-teal-600 flex items-center justify-center text-white text-xs font-bold flex-shrink-0">
            {user?.full_name?.charAt(0).toUpperCase() ?? 'U'}
          </div>
          <div className="flex-1 min-w-0">
            <p className="text-white text-sm font-medium truncate">{user?.full_name}</p>
            <p className="text-slate-400 text-xs truncate">{user?.email}</p>
          </div>
          <button
            onClick={handleLogout}
            className="text-slate-400 hover:text-white transition-colors"
            title="Logout"
          >
            <LogOut className="w-4 h-4" />
          </button>
        </div>
      </div>
    </div>
  );

  return (
    <div className="flex h-screen bg-slate-50 overflow-hidden">
      {/* Desktop Sidebar */}
      <aside className="hidden lg:flex w-64 flex-col bg-slate-800 flex-shrink-0">
        <SidebarContent />
      </aside>

      {/* Mobile Sidebar Overlay */}
      {sidebarOpen && (
        <div className="fixed inset-0 z-50 lg:hidden">
          <div className="absolute inset-0 bg-black/60" onClick={() => setSidebarOpen(false)} />
          <aside className="relative w-64 h-full bg-slate-800 flex flex-col">
            <button
              onClick={() => setSidebarOpen(false)}
              className="absolute top-4 right-4 text-slate-400 hover:text-white"
            >
              <X className="w-5 h-5" />
            </button>
            <SidebarContent />
          </aside>
        </div>
      )}

      {/* Main content */}
      <div className="flex-1 flex flex-col overflow-hidden">
        {/* Top bar (mobile only) */}
        <header className="lg:hidden flex items-center justify-between px-4 h-14 bg-white border-b border-slate-200 flex-shrink-0">
          <button onClick={() => setSidebarOpen(true)} className="text-slate-600">
            <Menu className="w-5 h-5" />
          </button>
          <div className="flex items-center gap-2">
            <div className="w-6 h-6 bg-teal-500 rounded flex items-center justify-center">
              <span className="text-white font-bold text-xs">V</span>
            </div>
            <span className="font-bold text-slate-800">Vitar</span>
          </div>
          <div className="w-5" />
        </header>

        {/* Trial banner */}
        {showTrialBanner && trial && (
          <TrialBanner trial={trial} onUpgrade={() => navigate('/settings/billing')} />
        )}

        {/* Page content */}
        <main className="flex-1 overflow-y-auto">
          <Outlet />
        </main>
      </div>

      {/* AI Chatbot bubble */}
      <div className="fixed bottom-6 right-6 z-40">
        {chatOpen ? (
          <AIChatbot onClose={() => setChatOpen(false)} />
        ) : (
          <button
            onClick={() => setChatOpen(true)}
            className="w-14 h-14 bg-teal-600 hover:bg-teal-500 text-white rounded-full shadow-lg flex items-center justify-center transition-all hover:scale-105"
            title="AI Assistant"
          >
            <MessageSquare className="w-6 h-6" />
          </button>
        )}
      </div>
    </div>
  );
}
