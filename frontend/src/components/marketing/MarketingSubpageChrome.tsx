/**
 * Shared "back to home" nav + simple footer used by the marketing
 * subpages (Contact, Growth, Screens, Feedback). Matches the demo
 * static site's per-page nav/footer pattern exactly.
 */
import { Link } from 'react-router-dom';
import type { ReactNode } from 'react';

interface FooterLink {
  label: string;
  to?: string;
  href?: string;
}

interface MarketingSubpageChromeProps {
  footerLinks: FooterLink[];
  children: ReactNode;
}

export default function MarketingSubpageChrome({ footerLinks, children }: MarketingSubpageChromeProps) {
  return (
    <>
      <nav>
        <Link to="/" className="nav-logo">
          <img src="/icon-192x192.png" alt="Vitar logo" />
          <span>Vitar</span>
        </Link>
        <Link to="/" className="nav-back">← Back to home</Link>
      </nav>

      <main>{children}</main>

      <footer>
        <p>&copy; {new Date().getFullYear()} LiveVault. Built for Nigerian healthcare.</p>
        <div className="flinks">
          {footerLinks.map((link) =>
            link.to ? (
              <Link key={link.label} to={link.to}>{link.label}</Link>
            ) : (
              <a key={link.label} href={link.href} target={link.href?.startsWith('http') ? '_blank' : undefined} rel={link.href?.startsWith('http') ? 'noopener' : undefined}>
                {link.label}
              </a>
            ),
          )}
        </div>
      </footer>
    </>
  );
}
