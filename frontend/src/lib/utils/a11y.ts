/**
 * Accessibility utilities — screen reader announcements and focus management.
 */
import { browser } from '$app/environment';

/**
 * Announce a message to screen readers via the live region.
 * The live region is defined in +layout.svelte.
 */
export function announce(message: string, priority: 'polite' | 'assertive' = 'polite'): void {
  if (!browser) return;
  const el = document.getElementById('sr-announcements');
  if (!el) return;

  el.setAttribute('aria-live', priority);
  // Clear then set to ensure re-announcement of same text
  el.textContent = '';
  requestAnimationFrame(() => {
    el.textContent = message;
  });
}

/**
 * Move focus to an element by selector, with a brief delay to ensure DOM is ready.
 */
export function focusElement(selector: string, delay = 50): void {
  if (!browser) return;
  setTimeout(() => {
    const el = document.querySelector<HTMLElement>(selector);
    if (el) {
      el.focus();
    }
  }, delay);
}

/**
 * Trap focus within a container (for modals/drawers).
 * Returns a cleanup function to remove the trap.
 */
export function trapFocus(container: HTMLElement): () => void {
  const focusable = container.querySelectorAll<HTMLElement>(
    'a[href], button:not([disabled]), textarea, input:not([disabled]), select, [tabindex]:not([tabindex="-1"])'
  );
  const first = focusable[0];
  const last = focusable[focusable.length - 1];

  function handleTab(e: KeyboardEvent) {
    if (e.key !== 'Tab') return;

    if (e.shiftKey) {
      if (document.activeElement === first) {
        e.preventDefault();
        last?.focus();
      }
    } else {
      if (document.activeElement === last) {
        e.preventDefault();
        first?.focus();
      }
    }
  }

  container.addEventListener('keydown', handleTab);
  first?.focus();

  return () => {
    container.removeEventListener('keydown', handleTab);
  };
}
