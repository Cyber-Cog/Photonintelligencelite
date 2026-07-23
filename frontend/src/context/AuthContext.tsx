import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import {
  ApiError,
  authApi,
  getCsrfToken,
  setCsrfToken as storeCsrfToken,
  type AuthUser,
} from "@/api/client";

interface AuthContextValue {
  user: AuthUser | null;
  loading: boolean;
  csrfToken: string | null;
  smtpConfigured: boolean;
  authAutoVerify: boolean;
  refresh: () => Promise<void>;
  login: (email: string, password: string) => Promise<void>;
  signup: (email: string, password: string, name: string) => Promise<{ verificationLink?: string | null; message?: string | null }>;
  logout: () => Promise<void>;
  updateProfile: (name: string) => Promise<void>;
  changePassword: (currentPassword: string, newPassword: string) => Promise<void>;
  isSuperadmin: boolean;
}

const AuthContext = createContext<AuthContextValue | null>(null);

function syncCsrf(token: string | null) {
  storeCsrfToken(token);
  return token;
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<AuthUser | null>(null);
  const [loading, setLoading] = useState(true);
  const [csrfToken, setCsrfTokenState] = useState<string | null>(getCsrfToken());
  const [smtpConfigured, setSmtpConfigured] = useState(false);
  const [authAutoVerify, setAuthAutoVerify] = useState(true);

  const setCsrfToken = useCallback((token: string | null) => {
    setCsrfTokenState(syncCsrf(token));
  }, []);

  const refresh = useCallback(async () => {
    try {
      const me = await authApi.me();
      setUser(me.user);
      setCsrfToken(me.csrf_token || getCsrfToken());
      setSmtpConfigured(me.smtp_configured);
      setAuthAutoVerify(me.auth_auto_verify);
    } catch {
      setUser(null);
      setCsrfToken(getCsrfToken());
    } finally {
      setLoading(false);
    }
  }, [setCsrfToken]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const login = useCallback(
    async (email: string, password: string) => {
      const res = await authApi.login(email, password);
      setUser(res.user);
      setCsrfToken(res.csrf_token);
    },
    [setCsrfToken],
  );

  const signup = useCallback(
    async (email: string, password: string, name: string) => {
      const res = await authApi.signup(email, password, name);
      setUser(res.user);
      setCsrfToken(res.csrf_token);
      return { verificationLink: res.verification_link, message: res.message };
    },
    [setCsrfToken],
  );

  const logout = useCallback(async () => {
    try {
      await authApi.logout();
    } catch (err) {
      if (!(err instanceof ApiError && (err.status === 401 || err.status === 403))) {
        // still clear local state
      }
    }
    setUser(null);
    setCsrfToken(null);
  }, [setCsrfToken]);

  const updateProfile = useCallback(
    async (name: string) => {
      const res = await authApi.updateProfile(name);
      setUser(res.user);
      setCsrfToken(res.csrf_token);
    },
    [setCsrfToken],
  );

  const changePassword = useCallback(async (currentPassword: string, newPassword: string) => {
    await authApi.changePassword(currentPassword, newPassword);
  }, []);

  const value = useMemo(
    () => ({
      user,
      loading,
      csrfToken,
      smtpConfigured,
      authAutoVerify,
      refresh,
      login,
      signup,
      logout,
      updateProfile,
      changePassword,
      isSuperadmin: user?.role === "superadmin",
    }),
    [
      user,
      loading,
      csrfToken,
      smtpConfigured,
      authAutoVerify,
      refresh,
      login,
      signup,
      logout,
      updateProfile,
      changePassword,
    ],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within AuthProvider");
  return ctx;
}
