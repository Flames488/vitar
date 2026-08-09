/**
 * Vitar — Currency Formatter Utility
 * Single source of truth for money formatting across the app.
 * Use `useGeoStore().formatMoney()` in components (it calls this internally).
 * Use `formatNaira()` for hardcoded NGN values (e.g. seed data, constants).
 */

export interface CurrencyFormat {
  symbol: string;
  code: string;
  locale: string;
  decimals: number;
}

export const NGN_FORMAT: CurrencyFormat = {
  symbol: '₦',
  code: 'NGN',
  locale: 'en-NG',
  decimals: 0,
};

export const USD_FORMAT: CurrencyFormat = {
  symbol: '$',
  code: 'USD',
  locale: 'en-US',
  decimals: 2,
};

// Mirrors backend/app/services/geo_service.py's CURRENCY_FORMAT — keep
// these in sync if a currency is added/changed on either side.
const CURRENCY_FORMATS: Record<string, CurrencyFormat> = {
  NGN: NGN_FORMAT,
  USD: USD_FORMAT,
  GBP: { symbol: '£', code: 'GBP', locale: 'en-GB', decimals: 2 },
  EUR: { symbol: '€', code: 'EUR', locale: 'de-DE', decimals: 2 },
  GHS: { symbol: '₵', code: 'GHS', locale: 'en-GH', decimals: 2 },
  KES: { symbol: 'KSh', code: 'KES', locale: 'en-KE', decimals: 0 },
  ZAR: { symbol: 'R', code: 'ZAR', locale: 'en-ZA', decimals: 2 },
  AUD: { symbol: 'A$', code: 'AUD', locale: 'en-AU', decimals: 2 },
  INR: { symbol: '₹', code: 'INR', locale: 'en-IN', decimals: 0 },
  CAD: { symbol: 'CA$', code: 'CAD', locale: 'en-CA', decimals: 2 },
};

/** Look up display format for a currency code; falls back to NGN. */
export function getCurrencyFormat(code: string | null | undefined): CurrencyFormat {
  return CURRENCY_FORMATS[(code ?? 'NGN').toUpperCase()] ?? NGN_FORMAT;
}

/**
 * Format a monetary amount with the given currency format.
 * Defaults to NGN if no format is provided.
 */
export function formatMoney(amount: number, fmt: CurrencyFormat = NGN_FORMAT): string {
  const symbol = fmt.symbol;
  if (fmt.decimals === 0) {
    return `${symbol}${Math.round(amount).toLocaleString(fmt.locale)}`;
  }
  return `${symbol}${amount.toLocaleString(fmt.locale, {
    minimumFractionDigits: fmt.decimals,
    maximumFractionDigits: fmt.decimals,
  })}`;
}

/** Convenience: always format as Naira */
export function formatNaira(amount: number): string {
  return formatMoney(amount, NGN_FORMAT);
}
