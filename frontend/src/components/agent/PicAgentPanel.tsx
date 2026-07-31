import { useCallback, useEffect, useRef, useState } from "react";
import { agentChat, getAgentStatus } from "@/api/client";
import { Spinner } from "@/components/ui/Spinner";

type Turn = { role: "user" | "assistant"; content: string };

type Props = {
  jobId?: string | null;
  context?: "upload" | "validation" | "general";
  suggestedPrompts?: string[];
};

export function PicAgentPanel({ jobId, context = "general", suggestedPrompts }: Props) {
  const [enabled, setEnabled] = useState<boolean | null>(null);
  const [open, setOpen] = useState(false);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [turns, setTurns] = useState<Turn[]>([]);
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    void getAgentStatus()
      .then((s) => setEnabled(s.enabled))
      .catch(() => setEnabled(false));
  }, []);

  useEffect(() => {
    if (scrollRef.current) scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
  }, [turns, open]);

  const send = useCallback(
    async (text: string) => {
      const message = text.trim();
      if (!message || busy) return;
      setError(null);
      setBusy(true);
      setTurns((prev) => [...prev, { role: "user", content: message }]);
      setInput("");
      try {
        const history = turns.slice(-6);
        const res = await agentChat({
          message,
          job_id: jobId ?? undefined,
          context,
          history,
        });
        setTurns((prev) => [...prev, { role: "assistant", content: res.content }]);
      } catch (e) {
        setError(e instanceof Error ? e.message : "Could not reach PIC Analyst.");
      } finally {
        setBusy(false);
      }
    },
    [busy, context, jobId, turns],
  );

  if (enabled === false) return null;

  const prompts =
    suggestedPrompts ??
    (context === "upload"
      ? [
          "Which signals are missing at SCB/string level?",
          "Why might clipping analysis not run?",
          "Summarize detected architecture.",
        ]
      : ["What should I fix in Setup?", "Explain blocked fault modules."]);

  return (
    <div className="rounded-xl border border-[color:var(--pic-border)] bg-[color:var(--pic-surface-raised)]">
      <button
        type="button"
        className="flex w-full items-center justify-between gap-3 px-4 py-3 text-left"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
      >
        <div>
          <p className="font-display text-sm font-semibold text-[color:var(--pic-text)]">PIC Analyst</p>
          <p className="text-xs text-[color:var(--pic-text-muted)]">ZenMux-powered help for this upload</p>
        </div>
        <span className="text-xs text-[color:var(--pic-text-muted)]">{open ? "▾" : "▸"}</span>
      </button>

      {open ? (
        <div className="border-t border-[color:var(--pic-border-subtle)] px-4 pb-4 pt-3">
          {turns.length === 0 ? (
            <div className="mb-3 flex flex-wrap gap-2">
              {prompts.map((p) => (
                <button
                  key={p}
                  type="button"
                  className="rounded-lg border border-[color:var(--pic-border-subtle)] bg-[color:var(--pic-surface-muted)] px-2.5 py-1 text-xs text-[color:var(--pic-text-secondary)] hover:border-brand-300/60"
                  onClick={() => void send(p)}
                  disabled={busy}
                >
                  {p}
                </button>
              ))}
            </div>
          ) : null}

          <div ref={scrollRef} className="mb-3 max-h-72 space-y-3 overflow-y-auto overscroll-contain pr-1">
            {turns.map((t, i) => (
              <div
                key={`${t.role}-${i}`}
                className={`rounded-lg px-3 py-2 text-sm ${
                  t.role === "user"
                    ? "ml-8 bg-brand-50/80 text-brand-950 dark:bg-brand-950/30 dark:text-brand-100"
                    : "mr-4 bg-[color:var(--pic-surface-muted)] text-[color:var(--pic-text-secondary)]"
                }`}
              >
                {t.content}
              </div>
            ))}
            {busy ? (
              <div className="flex items-center gap-2 text-xs text-[color:var(--pic-text-muted)]">
                <Spinner className="h-3.5 w-3.5" /> Thinking…
              </div>
            ) : null}
          </div>

          {error ? <p className="mb-2 text-xs text-rose-600 dark:text-rose-400">{error}</p> : null}

          <form
            className="flex gap-2"
            onSubmit={(e) => {
              e.preventDefault();
              void send(input);
            }}
          >
            <input
              type="text"
              className="min-w-0 flex-1 rounded-lg border border-[color:var(--pic-border)] bg-[color:var(--pic-surface)] px-3 py-2 text-sm"
              placeholder="Ask about detected signals, architecture, or blocked analyses…"
              value={input}
              onChange={(e) => setInput(e.target.value)}
              disabled={busy || enabled === null}
            />
            <button type="submit" className="btn-primary shrink-0 px-3 py-2 text-sm" disabled={busy || !input.trim()}>
              Send
            </button>
          </form>
        </div>
      ) : null}
    </div>
  );
}
