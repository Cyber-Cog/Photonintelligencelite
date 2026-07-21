import { lazy, Suspense } from "react";
import { Route, Routes } from "react-router-dom";
import { Layout } from "@/components/Layout";
import { RequireAuth } from "@/components/RequireAuth";
import { Spinner } from "@/components/ui/Spinner";
import { LandingPage } from "@/pages/LandingPage";
import { LoginPage } from "@/pages/LoginPage";
import { NotFoundPage } from "@/pages/NotFoundPage";
import { SignupPage } from "@/pages/SignupPage";
import { UploadPage } from "@/pages/UploadPage";

const ArchitecturePage = lazy(() =>
  import("@/pages/ArchitecturePage").then((m) => ({ default: m.ArchitecturePage })),
);
const DashboardPage = lazy(() =>
  import("@/pages/DashboardPage").then((m) => ({ default: m.DashboardPage })),
);
const DataPage = lazy(() => import("@/pages/DataPage").then((m) => ({ default: m.DataPage })));
const DocsPage = lazy(() => import("@/pages/DocsPage").then((m) => ({ default: m.DocsPage })));
const ExplorerPage = lazy(() =>
  import("@/pages/ExplorerPage").then((m) => ({ default: m.ExplorerPage })),
);
const ProcessingPage = lazy(() =>
  import("@/pages/ProcessingPage").then((m) => ({ default: m.ProcessingPage })),
);
const SetupPage = lazy(() => import("@/pages/SetupPage").then((m) => ({ default: m.SetupPage })));
const ValidationPage = lazy(() =>
  import("@/pages/ValidationPage").then((m) => ({ default: m.ValidationPage })),
);
const AdminPage = lazy(() => import("@/pages/AdminPage").then((m) => ({ default: m.AdminPage })));
const SettingsPage = lazy(() =>
  import("@/pages/SettingsPage").then((m) => ({ default: m.SettingsPage })),
);
const VerifyEmailPage = lazy(() =>
  import("@/pages/VerifyEmailPage").then((m) => ({ default: m.VerifyEmailPage })),
);
const ForgotPasswordPage = lazy(() =>
  import("@/pages/ForgotPasswordPage").then((m) => ({ default: m.ForgotPasswordPage })),
);
const ResetPasswordPage = lazy(() =>
  import("@/pages/ResetPasswordPage").then((m) => ({ default: m.ResetPasswordPage })),
);

function RouteFallback() {
  return (
    <div className="flex items-center justify-center gap-2 py-16 text-sm text-stone-500 dark:text-stone-400">
      <Spinner className="h-4 w-4" /> Loading…
    </div>
  );
}

export default function App() {
  return (
    <Layout>
      <Suspense fallback={<RouteFallback />}>
        <Routes>
          <Route path="/" element={<LandingPage />} />
          <Route path="/login" element={<LoginPage />} />
          <Route path="/signup" element={<SignupPage />} />
          <Route path="/verify-email" element={<VerifyEmailPage />} />
          <Route path="/forgot-password" element={<ForgotPasswordPage />} />
          <Route path="/reset-password" element={<ResetPasswordPage />} />
          <Route path="/settings" element={<SettingsPage />} />
          <Route path="/admin" element={<AdminPage />} />
          <Route path="/docs" element={<DocsPage />} />
          <Route
            path="/upload"
            element={
              <RequireAuth>
                <UploadPage />
              </RequireAuth>
            }
          />
          <Route path="/jobs/:jobId/setup" element={<SetupPage />} />
          <Route path="/jobs/:jobId/validate" element={<ValidationPage />} />
          <Route path="/jobs/:jobId/processing" element={<ProcessingPage />} />
          <Route path="/jobs/:jobId/dashboard" element={<DashboardPage />} />
          <Route path="/jobs/:jobId/data" element={<DataPage />} />
          <Route path="/jobs/:jobId/architecture" element={<ArchitecturePage />} />
          <Route path="/jobs/:jobId/explore" element={<ExplorerPage />} />
          <Route path="*" element={<NotFoundPage />} />
        </Routes>
      </Suspense>
    </Layout>
  );
}
