/**
 * Vitar v5 - Marketing Layout
 */

import { Outlet, Link, NavLink } from 'react-router-dom';

export default function MarketingLayout() {
  return (
    <div className="min-h-screen flex flex-col bg-white">
      {/* Navbar */}
      <header className="border-b border-slate-100 sticky top-0 bg-white/95 backdrop-blur z-30">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 h-16 flex items-center justify-between">
          <Link to="/" className="flex items-center gap-2">
            <div className="w-8 h-8 bg-teal-500 rounded-lg flex items-center justify-center">
              <span className="text-white font-bold text-sm">V</span>
            </div>
            <span className="font-bold text-xl text-slate-900">Vitar</span>
          </Link>

          <nav className="hidden md:flex items-center gap-8">
            <NavLink to="/pricing" className={({ isActive }) =>
              `text-sm font-medium transition-colors ${isActive ? 'text-teal-600' : 'text-slate-600 hover:text-slate-900'}`
            }>
              Pricing
            </NavLink>
          </nav>

          <div className="flex items-center gap-3">
            <Link to="/login" className="text-sm font-medium text-slate-600 hover:text-slate-900 transition-colors">
              Sign in
            </Link>
            <Link
              to="/register"
              className="bg-teal-600 hover:bg-teal-700 text-white text-sm font-medium px-4 py-2 rounded-lg transition-colors"
            >
              Start free trial
            </Link>
          </div>
        </div>
      </header>

      {/* Content */}
      <main className="flex-1">
        <Outlet />
      </main>

      {/* Footer */}
      <footer className="border-t border-slate-100 py-8">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 text-center text-sm text-slate-500">
          &copy; {new Date().getFullYear()} Vitar Health. All rights reserved.
        </div>
      </footer>
    </div>
  );
}
