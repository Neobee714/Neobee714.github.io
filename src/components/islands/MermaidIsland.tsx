/**
 * MermaidIsland — React island that dynamically loads mermaid.js
 * and renders all [data-mermaid] elements on the page.
 * Re-renders after Astro swaps and theme changes.
 */
import { useEffect } from 'react';

export default function MermaidIsland() {
  useEffect(() => {
    let cancelled = false;
    let renderRun = 0;

    const getTheme = () =>
      document.documentElement.getAttribute('data-theme') === 'light'
        ? 'default'
        : 'dark';

    const parseSvg = (svg: string) => {
      const doc = new DOMParser().parseFromString(svg, 'image/svg+xml');
      const svgEl = doc.documentElement;
      if (svgEl.tagName.toLowerCase() !== 'svg') {
        throw new Error('Mermaid render did not produce an SVG root element');
      }
      return svgEl;
    };

    const renderAll = async () => {
      const elements = document.querySelectorAll<HTMLElement>('[data-mermaid]');
      if (!elements.length) return;

      const currentRun = ++renderRun;
      const mermaid = (await import('mermaid')).default;
      if (cancelled || currentRun !== renderRun) return;

      mermaid.initialize({
        startOnLoad: false,
        securityLevel: 'strict',
        theme: getTheme(),
        fontFamily: 'inherit',
      });

      for (let i = 0; i < elements.length; i++) {
        if (cancelled || currentRun !== renderRun) return;

        const el = elements[i];
        const code = el.getAttribute('data-mermaid') || '';
        if (!code.trim()) continue;

        try {
          const renderId =
            el.dataset.mermaidRenderId ??
            `mermaid-${i}-${Math.random().toString(36).slice(2, 10)}`;
          el.dataset.mermaidRenderId = renderId;

          const { svg } = await mermaid.render(`${renderId}-${getTheme()}`, code);
          if (cancelled || currentRun !== renderRun) return;

          el.replaceChildren(document.importNode(parseSvg(svg), true));
          el.classList.add('mermaid-rendered');
          el.classList.remove('mermaid-error');
        } catch (err) {
          console.warn('[MermaidIsland] Failed to render diagram:', err);
          el.classList.add('mermaid-error');
        }
      }
    };

    const handleAfterSwap = () => {
      void renderAll();
    };

    const themeObserver = new MutationObserver((mutations) => {
      for (const mutation of mutations) {
        if (mutation.attributeName === 'data-theme') {
          void renderAll();
          break;
        }
      }
    });

    themeObserver.observe(document.documentElement, {
      attributes: true,
      attributeFilter: ['data-theme'],
    });
    document.addEventListener('astro:after-swap', handleAfterSwap);
    void renderAll();

    return () => {
      cancelled = true;
      renderRun++;
      themeObserver.disconnect();
      document.removeEventListener('astro:after-swap', handleAfterSwap);
    };
  }, []);

  // This component renders nothing visible itself
  return null;
}
