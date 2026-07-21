import { createContext, useCallback, useContext, useMemo, useState, type ReactNode } from "react";
import type { UploadResponse } from "@/types";

interface JobContextValue {
  jobId: string | null;
  uploadInfo: UploadResponse | null;
  setJob: (jobId: string, uploadInfo?: UploadResponse | null) => void;
  clearJob: () => void;
}

const JobContext = createContext<JobContextValue | null>(null);

export function JobProvider({ children }: { children: ReactNode }) {
  const [jobId, setJobId] = useState<string | null>(null);
  const [uploadInfo, setUploadInfo] = useState<UploadResponse | null>(null);

  const setJob = useCallback((id: string, info?: UploadResponse | null) => {
    setJobId(id);
    if (info !== undefined) setUploadInfo(info);
  }, []);

  const clearJob = useCallback(() => {
    setJobId(null);
    setUploadInfo(null);
  }, []);

  const value = useMemo(
    () => ({ jobId, uploadInfo, setJob, clearJob }),
    [jobId, uploadInfo, setJob, clearJob],
  );

  return <JobContext.Provider value={value}>{children}</JobContext.Provider>;
}

export function useJob() {
  const ctx = useContext(JobContext);
  if (!ctx) throw new Error("useJob must be used within JobProvider");
  return ctx;
}
