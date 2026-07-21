/** Underline-style enterprise tabs (sticky Results sections, toolbars). */
export function SubnavTabs({
  items,
  activeId,
  onSelect,
  ariaLabel,
  className = "",
  /** Align first tab with panel body padding (Setup unified card). */
  inset = false,
}: {
  items: { id: string; label: string }[];
  activeId: string;
  onSelect: (id: string) => void;
  ariaLabel: string;
  className?: string;
  inset?: boolean;
}) {
  return (
    <nav
      className={`flex w-full gap-0 overflow-x-auto overflow-y-hidden border-b border-stone-200/80 dark:border-stone-800 ${
        inset ? "px-2 sm:px-3" : ""
      } ${className}`}
      aria-label={ariaLabel}
    >
      {items.map((item) => {
        const active = item.id === activeId;
        return (
          <button
            key={item.id}
            type="button"
            data-results-section={item.id}
            data-tour={`nav-${item.id}`}
            onClick={() => onSelect(item.id)}
            className={`-mb-px shrink-0 border-b-2 px-3 py-2.5 text-xs font-semibold transition-all duration-200 ease-out ${
              active
                ? "border-brand-600 text-stone-900 dark:border-brand-400 dark:text-amber-100"
                : "border-transparent text-stone-600 hover:text-stone-900 dark:text-stone-300 dark:hover:text-amber-200"
            }`}
          >
            {item.label}
          </button>
        );
      })}
    </nav>
  );
}
