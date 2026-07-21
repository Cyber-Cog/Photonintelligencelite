import { useState, type RefObject } from "react";
import { downloadPlotlyPng } from "@/lib/chartTheme";

export function ChartDownloadButton({
  hostRef,
  filename,
  className = "btn-secondary text-xs",
}: {
  hostRef: RefObject<HTMLElement | null>;
  filename: string;
  className?: string;
}) {
  const [busy, setBusy] = useState(false);

  return (
    <button
      type="button"
      className={className}
      disabled={busy}
      onClick={async () => {
        setBusy(true);
        try {
          await downloadPlotlyPng(hostRef.current, filename);
        } finally {
          setBusy(false);
        }
      }}
    >
      {busy ? "Saving…" : "Download chart"}
    </button>
  );
}
