import { Link, Navigate, useLocation } from "react-router-dom";
import { Spinner } from "@/components/ui/Spinner";
import { useAuth } from "@/context/AuthContext";

export function RequireAuth({
  children,
  requireVerified = true,
  requireSuperadmin = false,
}: {
  children: React.ReactNode;
  requireVerified?: boolean;
  requireSuperadmin?: boolean;
}) {
  const { user, loading } = useAuth();
  const location = useLocation();

  if (loading) {
    return (
      <div className="flex items-center justify-center gap-2 py-16 text-sm text-stone-500">
        <Spinner className="h-4 w-4" /> Checking session…
      </div>
    );
  }

  if (!user) {
    const next = encodeURIComponent(location.pathname + location.search);
    return <Navigate to={`/login?next=${next}`} replace />;
  }

  if (requireVerified && !user.email_verified) {
    return <Navigate to={`/verify-email?next=${encodeURIComponent(location.pathname)}`} replace />;
  }

  if (requireSuperadmin && user.role !== "superadmin") {
    return <Navigate to="/" replace />;
  }

  return <>{children}</>;
}

/** Soft gate: show teaser when logged out instead of hard redirect. */
export function AuthTeaser({
  title,
  body,
  children,
}: {
  title: string;
  body: string;
  children?: React.ReactNode;
}) {
  const { user, loading } = useAuth();
  const location = useLocation();

  if (loading) {
    return (
      <div className="flex items-center justify-center gap-2 py-16 text-sm text-stone-500">
        <Spinner className="h-4 w-4" /> Loading…
      </div>
    );
  }

  if (user?.email_verified) return <>{children}</>;

  const next = encodeURIComponent(location.pathname + location.search);
  return (
    <div className="tool-enter mx-auto max-w-lg py-16 text-center">
      <h1 className="font-display text-2xl font-semibold text-stone-900 dark:text-stone-50">{title}</h1>
      <p className="mt-3 text-sm leading-relaxed text-stone-500 dark:text-stone-400">{body}</p>
      <div className="mt-8 flex flex-wrap items-center justify-center gap-3">
        <Link to={`/login?next=${next}`} className="btn-primary text-sm">
          Log in
        </Link>
        <Link to={`/signup?next=${next}`} className="btn-secondary text-sm">
          Sign up
        </Link>
      </div>
    </div>
  );
}
