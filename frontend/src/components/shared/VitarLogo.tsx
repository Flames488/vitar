/**
 * Vitar - Logo Component
 * Single source of truth for the Vitar logo across the entire frontend.
 * Swap the image import here to update every logo in the app at once.
 */

import vitarLogoSrc from '@/assets/vitar-logo.png';

interface VitarLogoProps {
  /** Height of the logo in pixels. Width scales proportionally. */
  size?: number;
  /** Additional Tailwind / CSS class names */
  className?: string;
}

export default function VitarLogo({ size = 40, className = '' }: VitarLogoProps) {
  return (
    <img
      src={vitarLogoSrc}
      alt="Vitar — Healthcare Appointment Platform"
      width={size}
      height={size}
      className={`object-contain ${className}`}
      draggable={false}
    />
  );
}
