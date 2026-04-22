import { createContext, useContext, useEffect, useState, useCallback, useRef, ReactNode } from 'react';
import { UserProfile, fetchMe, clearAuthToken, buildGoogleAuthStartUrl, LOCAL_DEV_AUTH_ENABLED, setAuthToken, setUnauthorizedHandler, exchangeAuthCode, signInLocalDev } from './api';

interface AuthContextType {
  user: UserProfile | null;
  loading: boolean;
  needsConsent: boolean;
  signIn: () => Promise<void>;
  signOut: () => void;
  connectGmail: () => Promise<void>;
  connectCalendar: () => Promise<void>;
  refreshUser: () => Promise<void>;
}

const AuthContext = createContext<AuthContextType>({
  user: null,
  loading: true,
  needsConsent: false,
  signIn: async () => {},
  signOut: () => {},
  connectGmail: async () => {},
  connectCalendar: async () => {},
  refreshUser: async () => {},
});

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<UserProfile | null>(null);
  const [loading, setLoading] = useState(true);
  const bootRan = useRef(false);

  const refreshUser = useCallback(async () => {
    try {
      const profile = await fetchMe();
      setUser(profile);
    } catch {
      setUser(null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (bootRan.current) return;
    bootRan.current = true;

    const boot = async () => {
      const searchParams = new URLSearchParams(window.location.search);
      const code = searchParams.get('code');
      const callbackPath = window.location.pathname.replace(/\/+$/, '');

      // Exchange one-time auth code from OAuth callback
      if (code && callbackPath === '/auth/callback') {
        await exchangeAuthCode(code);
        window.history.replaceState({}, '', `${window.location.origin}/`);
      }

      // Legacy support: if an access_token is in the hash (e.g. mobile redirect)
      const hashParams = new URLSearchParams(window.location.hash.replace(/^#/, ''));
      const legacyToken = hashParams.get('access_token') || searchParams.get('access_token');
      if (legacyToken) {
        setAuthToken(legacyToken);
        window.history.replaceState({}, '', `${window.location.origin}/`);
      }

      await refreshUser();
    };
    boot();
  }, [refreshUser]);

  useEffect(() => {
    setUnauthorizedHandler(() => {
      setUser(null);
      setLoading(false);
    });

    return () => setUnauthorizedHandler(null);
  }, []);

  const signIn = useCallback(async () => {
    if (LOCAL_DEV_AUTH_ENABLED) {
      await signInLocalDev();
      await refreshUser();
      return;
    }
    window.location.href = buildGoogleAuthStartUrl();
  }, [refreshUser]);

  const signOut = useCallback(() => {
    clearAuthToken();
  }, []);

  const connectGmail = useCallback(async () => {
    const url = buildGoogleAuthStartUrl({
      connectGmail: true,
      connectCalendar: !!user?.calendar_connected,
    });
    window.location.href = url;
  }, [user]);

  const connectCalendar = useCallback(async () => {
    const url = buildGoogleAuthStartUrl({
      connectGmail: !!user?.gmail_connected,
      connectCalendar: true,
    });
    window.location.href = url;
  }, [user]);

  const needsConsent = !!user && !user.data_consent_accepted_at;

  return (
    <AuthContext.Provider value={{ user, loading, needsConsent, signIn, signOut, connectGmail, connectCalendar, refreshUser }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  return useContext(AuthContext);
}
