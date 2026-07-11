/**
 * Reveal — small scroll-into-view fade/slide wrapper.
 * Ports the demo site's `.reveal` + IntersectionObserver behaviour
 * (see the old static index.html's inline <script>) into a reusable
 * React component so every marketing page can use the same effect.
 */
import { useEffect, useRef, useState, createElement, type ReactNode, type ElementType } from 'react';

interface RevealProps {
  as?: ElementType;
  className?: string;
  style?: React.CSSProperties;
  children: ReactNode;
  [key: string]: unknown;
}

export default function Reveal({ as = 'div', className = '', style, children, ...rest }: RevealProps) {
  const ref = useRef<HTMLElement | null>(null);
  const [visible, setVisible] = useState(false);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const observer = new IntersectionObserver(
      (entries) => {
        entries.forEach((entry) => {
          if (entry.isIntersecting) {
            setVisible(true);
            observer.unobserve(entry.target);
          }
        });
      },
      { threshold: 0.12 },
    );
    observer.observe(el);
    return () => observer.disconnect();
  }, []);

  return createElement(
    as,
    {
      ref,
      className: `reveal${visible ? ' visible' : ''}${className ? ` ${className}` : ''}`,
      style,
      ...rest,
    },
    children,
  );
}

