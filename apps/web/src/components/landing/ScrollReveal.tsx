"use client";

import {
  memo,
  useEffect,
  useRef,
  useState,
  type ReactNode,
} from "react";

export interface ScrollRevealProps {
  children: ReactNode;
  /** Optional stagger delay in milliseconds (e.g. 0, 80, 160) */
  delayMs?: number;
  /** Optional custom class names */
  className?: string;
  /** Optional HTML tag role or id */
  id?: string;
}

/**
 * Bidirectional IntersectionObserver reveal wrapper.
 * - Smoothly reveals elements with upward motion when scrolling down.
 * - Gracefully re-reveals elements with consistent motion when scrolling back up.
 * - Automatically disables motion transitions when `prefers-reduced-motion: reduce` is enabled.
 */
function ScrollReveal({
  children,
  delayMs = 0,
  className = "",
  id,
}: ScrollRevealProps) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const lastScrollYRef = useRef<number>(0);
  const [isVisible, setIsVisible] = useState<boolean>(true);
  const [scrollDirection, setScrollDirection] = useState<"down" | "up">("down");
  const [reducedMotion, setReducedMotion] = useState<boolean>(false);

  useEffect(() => {
    if (typeof window === "undefined") {
      return;
    }

    const mediaQuery = window.matchMedia("(prefers-reduced-motion: reduce)");
    const handleMotionChange = () => {
      const prefersReduced = mediaQuery.matches;
      setReducedMotion(prefersReduced);
      if (prefersReduced) {
        setIsVisible(true);
      }
    };
    handleMotionChange();

    if (typeof mediaQuery.addEventListener === "function") {
      mediaQuery.addEventListener("change", handleMotionChange);
    }

    if (mediaQuery.matches || typeof IntersectionObserver === "undefined") {
      return () => {
        if (typeof mediaQuery.removeEventListener === "function") {
          mediaQuery.removeEventListener("change", handleMotionChange);
        }
      };
    }

    const handleScroll = () => {
      const currentY = window.scrollY || window.pageYOffset || 0;
      setScrollDirection(currentY >= lastScrollYRef.current ? "down" : "up");
      lastScrollYRef.current = currentY;
    };

    window.addEventListener("scroll", handleScroll, { passive: true });

    const element = containerRef.current;
    if (!element) {
      return () => {
        window.removeEventListener("scroll", handleScroll);
        if (typeof mediaQuery.removeEventListener === "function") {
          mediaQuery.removeEventListener("change", handleMotionChange);
        }
      };
    }

    const observer = new IntersectionObserver(
      (entries) => {
        for (const entry of entries) {
          if (entry.isIntersecting) {
            setIsVisible(true);
          } else {
            // Allow bidirectional re-entry when scrolling back up or down
            setIsVisible(false);
          }
        }
      },
      {
        threshold: 0.1,
        rootMargin: "0px 0px -32px 0px",
      },
    );

    observer.observe(element);

    return () => {
      observer.disconnect();
      window.removeEventListener("scroll", handleScroll);
      if (typeof mediaQuery.removeEventListener === "function") {
        mediaQuery.removeEventListener("change", handleMotionChange);
      }
    };
  }, []);

  const hiddenOffsetClass =
    scrollDirection === "down"
      ? "opacity-0 translate-y-4"
      : "opacity-0 -translate-y-3";

  const motionClass = reducedMotion
    ? "opacity-100 translate-y-0"
    : isVisible
      ? "opacity-100 translate-y-0 transition-all duration-500 ease-out"
      : `${hiddenOffsetClass} transition-all duration-300 ease-out`;

  return (
    <div
      id={id}
      ref={containerRef}
      style={
        !reducedMotion && delayMs > 0
          ? { transitionDelay: `${delayMs}ms` }
          : undefined
      }
      className={`will-change-[transform,opacity] ${motionClass} ${className}`}
    >
      {children}
    </div>
  );
}

export default memo(ScrollReveal);
