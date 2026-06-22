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
