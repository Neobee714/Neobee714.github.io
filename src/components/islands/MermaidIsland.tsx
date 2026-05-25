/**
 * MermaidIsland — React island that dynamically loads mermaid.js
 * and renders all [data-mermaid] elements on the page.
 * Only loads mermaid if such elements exist.
 */
import { useEffect } from 'react';

export default function MermaidIsland() {
  useEffect(() => {
    const elements = document.querySelectorAll('[data-mermaid]');
    if (!elements.length) return;

    let cancelled = false;

    (async () => {
      const mermaid = (await import('mermaid')).default;
      if (cancelled) return;

      mermaid.initialize({
        startOnLoad: false,
        theme: document.documentElement.getAttribute('data-theme') === 'light'
          ? 'default'
          : 'dark',
        fontFamily: 'inherit',
      });

      for (let i = 0; i < elements.length; i++) {
        const el = elements[i] as HTMLElement;
        const code = el.getAttribute('data-mermaid') || '';
        if (!code.trim()) continue;

        try {
          const { svg } = await mermaid.render(`mermaid-${i}`, code);
          el.innerHTML = svg;
          el.classList.add('mermaid-rendered');
        } catch (err) {
          console.warn('[MermaidIsland] Failed to render diagram:', err);
          el.classList.add('mermaid-error');
        }
      }
    })();

    return () => { cancelled = true; };
  }, []);

  // This component renders nothing visible itself
  return null;
}
