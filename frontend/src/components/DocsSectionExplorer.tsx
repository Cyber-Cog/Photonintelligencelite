import { useCallback, useEffect, useMemo, useState } from "react";
import type { AlgorithmDoc } from "@/content/algorithms";

type DocsSectionExplorerProps = {
  docs: AlgorithmDoc[];
  activeId: string | null;
  onJump: (id: string) => void;
};

export function DocsSectionExplorer({ docs, activeId, onJump }: DocsSectionExplorerProps) {
  const [query, setQuery] = useState("");

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return docs;
    return docs.filter(
      (d) =>
        d.title.toLowerCase().includes(q) ||
        d.id.toLowerCase().includes(q) ||
        d.summary.toLowerCase().includes(q),
    );
  }, [docs, query]);

  return (
    <nav aria-label="Algorithm section explorer" className="docs-explorer">
      <div className="mb-3">
        <p className="tool-eyebrow">Section explorer</p>
        <label className="sr-only" htmlFor="docs-explorer-search">
          Filter algorithms
        </label>
        <input
          id="docs-explorer-search"
          type="search"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Filter modules…"
          className="input mt-2.5 py-1.5 text-xs"
        />
      </div>

      {/* Mobile jump list */}
      <div className="lg:hidden">
        <label className="sr-only" htmlFor="docs-explorer-jump">
          Jump to algorithm
        </label>
        <select
          id="docs-explorer-jump"
          className="input py-2 text-sm"
          value={activeId ?? ""}
          onChange={(e) => {
            if (e.target.value) onJump(e.target.value);
          }}
        >
          <option value="" disabled>
            Jump to module…
          </option>
          {filtered.map((d) => (
            <option key={d.id} value={d.id}>
              {d.title}
            </option>
          ))}
        </select>
        {query && filtered.length === 0 ? (
          <p className="mt-2 text-xs text-stone-500">No modules match.</p>
        ) : null}
      </div>

      {/* Desktop sticky list */}
      <ul className="hidden max-h-[calc(100vh-11rem)] space-y-0.5 overflow-y-auto pr-1 lg:block">
        {filtered.map((d) => {
          const isActive = d.id === activeId;
          return (
            <li key={d.id}>
              <button
                type="button"
                onClick={() => onJump(d.id)}
                className={`w-full rounded-xl px-2.5 py-2 text-left text-sm transition-all duration-150 ${
                  isActive
                    ? "bg-brand-50 font-semibold text-brand-800 shadow-sm shadow-brand-600/10 dark:bg-brand-950/40 dark:text-brand-300 dark:shadow-none"
                    : "text-stone-600 hover:bg-stone-100 hover:text-stone-900 dark:text-stone-400 dark:hover:bg-stone-800/80 dark:hover:text-stone-100"
                }`}
                aria-current={isActive ? "true" : undefined}
              >
                <span className="line-clamp-2">{d.title}</span>
              </button>
            </li>
          );
        })}
        {filtered.length === 0 ? (
          <li className="px-2.5 py-2 text-xs text-stone-500">No modules match.</li>
        ) : null}
      </ul>
    </nav>
  );
}

/** Tracks which algorithm section is in view for the explorer. */
export function useActiveSection(ids: string[]) {
  const [activeId, setActiveId] = useState<string | null>(ids[0] ?? null);

  useEffect(() => {
    if (ids.length === 0) return;

    const elements = ids
      .map((id) => document.getElementById(id))
      .filter((el): el is HTMLElement => Boolean(el));

    if (elements.length === 0) return;

    const visibility = new Map<string, number>();

    const io = new IntersectionObserver(
      (entries) => {
        for (const entry of entries) {
          visibility.set(entry.target.id, entry.isIntersecting ? entry.intersectionRatio : 0);
        }
        let bestId = ids[0];
        let bestRatio = -1;
        for (const id of ids) {
          const ratio = visibility.get(id) ?? 0;
          if (ratio > bestRatio) {
            bestRatio = ratio;
            bestId = id;
          }
        }
        if (bestRatio > 0) setActiveId(bestId);
      },
      {
        rootMargin: "-20% 0px -55% 0px",
        threshold: [0, 0.1, 0.25, 0.5, 0.75, 1],
      },
    );

    for (const el of elements) io.observe(el);
    return () => io.disconnect();
  }, [ids]);

  const jumpTo = useCallback((id: string) => {
    const el = document.getElementById(id);
    if (!el) return;
    setActiveId(id);
    el.scrollIntoView({ behavior: "smooth", block: "start" });
    el.classList.add("docs-section-flash");
    window.setTimeout(() => el.classList.remove("docs-section-flash"), 1200);
    const url = new URL(window.location.href);
    url.hash = id;
    window.history.replaceState(null, "", url.toString());
  }, []);

  useEffect(() => {
    const hash = window.location.hash.replace(/^#/, "");
    if (hash && ids.includes(hash)) {
      window.requestAnimationFrame(() => jumpTo(hash));
    }
  }, [ids, jumpTo]);

  return { activeId, jumpTo };
}
