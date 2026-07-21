/**
 * Best-effort browser-side gzip for plain .csv uploads using the native CompressionStream
 * API (docs/PRD.md §0 — "browser may gzip plain CSV uploads when supported"). Falls back to
 * uploading the original file untouched when the API is unavailable; already-compressed
 * .csv.gz files are never touched here.
 *
 * Cast through `unknown`/`any` throughout: CompressionStream is not yet part of the
 * standard lib.dom.d.ts typings shipped with the TypeScript version pinned here, and this
 * is a progressive-enhancement path that must degrade silently rather than fail a build.
 */
type MaybeWindow = typeof window & { CompressionStream?: new (format: string) => unknown };

export function supportsClientGzip(): boolean {
  return typeof (window as MaybeWindow).CompressionStream === "function";
}

export async function gzipFile(file: File): Promise<File> {
  const CompressionStreamCtor = (window as MaybeWindow).CompressionStream;
  if (!CompressionStreamCtor) return file;

  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const gzipStream = new CompressionStreamCtor("gzip") as any;
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const stream = (file.stream() as any).pipeThrough(gzipStream);
  const compressedBlob = await new Response(stream).blob();
  const gzName = file.name.toLowerCase().endsWith(".gz") ? file.name : `${file.name}.gz`;
  return new File([compressedBlob], gzName, { type: "application/gzip" });
}

export async function maybeCompress(file: File): Promise<File> {
  const lower = file.name.toLowerCase();
  const isAlreadyCompressed = lower.endsWith(".gz");
  const isExcel = lower.endsWith(".xlsx") || lower.endsWith(".xlsm") || lower.endsWith(".xls");
  // Never gzip Excel — the server must read the workbook format to convert it to CSV.
  if (isAlreadyCompressed || isExcel || !supportsClientGzip()) return file;
  try {
    const compressed = await gzipFile(file);
    return compressed.size < file.size ? compressed : file;
  } catch {
    return file;
  }
}
