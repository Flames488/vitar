/**
 * Vitar v5 - Dashboard Layout
 * Advanced professional sidebar — dark navy + teal, grouped nav, micro-interactions
 */

import { useState } from 'react';
import { Outlet, NavLink, useNavigate } from 'react-router-dom';
import {
  LayoutDashboard, Calendar, Users, UserCheck, BarChart3,
  Banknote, Settings, Brain, Clock, Bell, LogOut, Menu,
  X, AlertTriangle, MessageSquare, ListOrdered, Key, QrCode,
  ChevronRight, Sparkles,
} from 'lucide-react';
import { useAuthStore } from '@/stores/authStore';
import { useGeoStore } from '@/stores/geoStore';
import AIChatbot from '@/components/ai/AIChatbot';
import TrialBanner from '@/components/shared/TrialBanner';
import VitarLogo from '@/components/shared/VitarLogo';

const NAV_GROUPS = [
  {
    label: 'Overview',
    items: [
      { to: '/dashboard',    label: 'Dashboard',    icon: LayoutDashboard, badge: null },
      { to: '/appointments', label: 'Appointments', icon: Calendar,        badge: null },
    ],
  },
  {
    label: 'Clinic',
    items: [
      { to: '/doctors',               label: 'Doctors',      icon: UserCheck, badge: null },
      { to: '/patients',              label: 'Patients',     icon: Users,     badge: null },
      { to: '/settings/booking-page', label: 'Booking Page', icon: Clock,     badge: 'NEW' },
      { to: '/settings/qr-code',      label: 'QR Code',      icon: QrCode,    badge: null },
      { to: '/earnings',              label: 'Earnings',     icon: Banknote,  badge: null },
    ],
  },
  {
    label: 'Intelligence',
    items: [
      { to: '/waiting-list', label: 'Waiting List', icon: ListOrdered, badge: null },
      { to: '/analytics',    label: 'Analytics',    icon: BarChart3,   badge: null },
      { to: '/ai-risk',      label: 'AI Risk',      icon: Brain,       badge: 'AI' },
    ],
  },
];

const SETTINGS_ITEMS = [
  { to: '/settings',                label: 'General',       icon: Settings },
  { to: '/settings/billing',        label: 'Billing',       icon: Banknote },
  { to: '/settings/notifications',  label: 'Notifications', icon: Bell },
  { to: '/settings/api-keys',       label: 'API Keys',      icon: Key },
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
    <div className="flex flex-col h-full" style={{ background: 'linear-gradient(180deg, #0f1623 0%, #111827 100%)' }}>

      {/* ── Logo / Brand ── */}
      <div className="px-5 pt-6 pb-5" style={{ borderBottom: '1px solid rgba(255,255,255,0.06)' }}>
        <div className="flex items-center gap-3">
          <div
            className="flex items-center justify-center w-9 h-9 rounded-xl flex-shrink-0"
            style={{ background: 'linear-gradient(135deg, #0d9488 0%, #0891b2 100%)', boxShadow: '0 0 20px rgba(13,148,136,0.35)' }}
          >
            <VitarLogo size={20} />
          </div>
          <div>
            <span className="text-white font-bold text-base tracking-tight">Vitar</span>
            {clinic && (
              <p className="text-xs truncate max-w-[140px]" style={{ color: 'rgba(148,163,184,0.7)' }}>
                {clinic.name}
              </p>
            )}
          </div>
        </div>
      </div>

      {/* ── Navigation ── */}
      <nav className="flex-1 px-3 py-4 overflow-y-auto" style={{ scrollbarWidth: 'none' }}>
        {NAV_GROUPS.map((group) => (
          <div key={group.label} className="mb-5">
            <p
              className="px-3 mb-1.5 text-[10px] font-bold uppercase tracking-[0.12em]"
              style={{ color: 'rgba(100,116,139,0.8)' }}
            >
              {group.label}
            </p>
            <div className="space-y-0.5">
              {group.items.map(({ to, label, icon: Icon, badge }) => (
                <NavLink
                  key={to}
                  to={to}
                  onClick={() => setSidebarOpen(false)}
                  className={({ isActive }) =>
                    `group relative flex items-center gap-3 px-3 py-2.5 rounded-xl text-sm font-medium transition-all duration-150 ${
                      isActive ? 'active-nav-item' : 'inactive-nav-item'
                    }`
                  }
                  style={({ isActive }) => isActive ? {
                    background: 'linear-gradient(90deg, rgba(13,148,136,0.2) 0%, rgba(8,145,178,0.1) 100%)',
                    color: '#2dd4bf',
                    boxShadow: 'inset 2px 0 0 #0d9488',
                  } : {
                    color: 'rgba(148,163,184,0.85)',
                  }}
                >
                  {({ isActive }) => (
                    <>
                      <Icon
                        className="w-4 h-4 flex-shrink-0 transition-colors"
                        style={{ color: isActive ? '#2dd4bf' : 'rgba(100,116,139,0.9)' }}
                      />
                      <span className="flex-1">{label}</span>
                      {badge && (
                        <span
                          className="text-[9px] font-bold px-1.5 py-0.5 rounded-full"
                          style={{ background: 'rgba(13,148,136,0.25)', color: '#2dd4bf', border: '1px solid rgba(13,148,136,0.3)' }}
                        >
                          {badge}
                        </span>
                      )}
                      {isActive && (
                        <ChevronRight className="w-3 h-3 opacity-60" style={{ color: '#2dd4bf' }} />
                      )}
                    </>
                  )}
                </NavLink>
              ))}
            </div>
          </div>
        ))}

        {/* Settings Group */}
        <div className="mb-5">
          <p
            className="px-3 mb-1.5 text-[10px] font-bold uppercase tracking-[0.12em]"
            style={{ color: 'rgba(100,116,139,0.8)' }}
          >
            Settings
          </p>
          <div className="space-y-0.5">
            {SETTINGS_ITEMS.map(({ to, label, icon: Icon }) => (
              <NavLink
                key={to}
                to={to}
                end
                onClick={() => setSidebarOpen(false)}
                style={({ isActive }) => isActive ? {
                  display: 'flex', alignItems: 'center', gap: '0.75rem',
                  padding: '0.625rem 0.75rem', borderRadius: '0.75rem',
                  fontSize: '0.875rem', fontWeight: 500,
                  background: 'linear-gradient(90deg, rgba(13,148,136,0.2) 0%, rgba(8,145,178,0.1) 100%)',
                  color: '#2dd4bf',
                  boxShadow: 'inset 2px 0 0 #0d9488',
                  textDecoration: 'none', transition: 'all 150ms',
                } : {
                  display: 'flex', alignItems: 'center', gap: '0.75rem',
                  padding: '0.625rem 0.75rem', borderRadius: '0.75rem',
                  fontSize: '0.875rem', fontWeight: 500,
                  color: 'rgba(148,163,184,0.85)',
                  textDecoration: 'none', transition: 'all 150ms',
                }}
              >
                {({ isActive }) => (
                  <>
                    <Icon
                      className="w-4 h-4 flex-shrink-0"
                      style={{ color: isActive ? '#2dd4bf' : 'rgba(100,116,139,0.9)' }}
                    />
                    <span className="flex-1">{label}</span>
                    {isActive && (
                      <ChevronRight className="w-3 h-3 opacity-60" style={{ color: '#2dd4bf' }} />
                    )}
                  </>
                )}
              </NavLink>
            ))}
          </div>
        </div>
      </nav>



      {/* ── User Profile ── */}
      <div
        className="px-3 py-4"
        style={{ borderTop: '1px solid rgba(255,255,255,0.06)' }}
      >
        <div
          className="flex items-center gap-3 px-3 py-2.5 rounded-xl transition-all cursor-default"
          style={{ background: 'rgba(255,255,255,0.03)' }}
        >
          <div
            className="w-8 h-8 rounded-full flex items-center justify-center text-white text-xs font-bold flex-shrink-0"
            style={{
              background: 'linear-gradient(135deg, #0d9488, #0891b2)',
              boxShadow: '0 0 12px rgba(13,148,136,0.4)',
            }}
          >
            {user?.full_name?.charAt(0).toUpperCase() ?? 'U'}
          </div>
          <div className="flex-1 min-w-0">
            <p className="text-white text-xs font-semibold truncate">{user?.full_name}</p>
            <p className="text-[10px] truncate" style={{ color: 'rgba(100,116,139,0.8)' }}>{user?.email}</p>
          </div>
          <button
            onClick={handleLogout}
            className="p-1.5 rounded-lg transition-all hover:bg-white/5"
            style={{ color: 'rgba(100,116,139,0.8)' }}
            title="Sign out"
          >
            <LogOut className="w-3.5 h-3.5" />
          </button>
        </div>
      </div>
    </div>
  );

  return (
    <div className="flex h-screen overflow-hidden" style={{ background: '#f8fafc' }}>

      {/* Desktop Sidebar */}
      <aside className="hidden lg:flex w-[220px] flex-col flex-shrink-0" style={{ boxShadow: '1px 0 0 rgba(0,0,0,0.08)' }}>
        <SidebarContent />
      </aside>

      {/* Mobile Sidebar Overlay */}
      {sidebarOpen && (
        <div className="fixed inset-0 z-50 lg:hidden">
          <div
            className="absolute inset-0 backdrop-blur-sm"
            style={{ background: 'rgba(0,0,0,0.5)' }}
            onClick={() => setSidebarOpen(false)}
          />
          <aside
            className="relative w-[220px] h-full flex flex-col"
            style={{
              background: 'linear-gradient(180deg, #0f1623 0%, #111827 100%)',
              boxShadow: '4px 0 24px rgba(0,0,0,0.4)',
            }}
          >
            <button
              onClick={() => setSidebarOpen(false)}
              className="absolute top-4 right-4 p-1.5 rounded-lg transition-colors"
              style={{ color: 'rgba(100,116,139,0.8)' }}
            >
              <X className="w-4 h-4" />
            </button>
            <SidebarContent />
          </aside>
        </div>
      )}

      {/* Main content */}
      <div className="flex-1 flex flex-col overflow-hidden">

        {/* Mobile topbar */}
        <header
          className="lg:hidden flex items-center justify-between px-4 h-14 flex-shrink-0"
          style={{ background: '#fff', borderBottom: '1px solid rgba(0,0,0,0.06)', boxShadow: '0 1px 4px rgba(0,0,0,0.04)' }}
        >
          <button
            onClick={() => setSidebarOpen(true)}
            className="p-2 rounded-lg transition-colors"
            style={{ color: '#475569' }}
          >
            <Menu className="w-5 h-5" />
          </button>
          <div className="flex items-center gap-2.5">
            <div
              className="flex items-center justify-center w-7 h-7 rounded-lg"
              style={{ background: 'linear-gradient(135deg, #0d9488, #0891b2)' }}
            >
              <VitarLogo size={16} />
            </div>
            <span className="font-bold text-slate-800 text-sm">Vitar</span>
          </div>
          <div className="w-9" />
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
            className="w-13 h-13 rounded-2xl flex items-center justify-center transition-all hover:scale-105 active:scale-95"
            style={{
              width: '52px', height: '52px',
              background: 'linear-gradient(135deg, #0d9488, #0891b2)',
              boxShadow: '0 4px 20px rgba(13,148,136,0.45), 0 2px 8px rgba(0,0,0,0.15)',
            }}
            title="AI Assistant"
          >
            <Sparkles className="w-5 h-5 text-white" />
          </button>
        )}
      </div>
    </div>
  );
}
