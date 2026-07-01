import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import App from './App.tsx'
import { initAnalytics } from '@/lib/analytics'
import { initSentry } from '@/lib/sentry'

// 1. Sentry first — catches crashes even during React setup
initSentry()

// 2. PostHog — initialise before first render so the first pageview isn't missed
initAnalytics()

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
  </StrictMode>,
)
