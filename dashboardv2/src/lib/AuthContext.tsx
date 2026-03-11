import { createContext, useContext, useEffect, useState, useCallback, ReactNode } from 'react';
import { UserProfile, fetchMe, clearAuthToken, buildGoogleAuthStartUrl, setUnauthorizedHandler } from './api';

interface AuthContextType {
  user: UserProfile | null;
  loading: boolean;
  signIn: () => Promise<void>;
  signOut: () => void;
  connectGmail: () => Promise<void>;
  connectCalendar: () => Promise<void>;
  refreshUser: () => Promise<void>;
}

const AuthContext = createContext<AuthContextType>({
  user: null,
  loading: true,
  signIn: async () => {},
  signOut: () => {},
  connectGmail: async () => {},
  connectCalendar: async () => {},
  refreshUser: async () => {},
});

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<UserProfile | null>(null);
  const [loading, setLoading] = useState(true);

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
    const path = window.location.pathname;
    if (path === '/auth/callback') {
      // Google OAuth now relies on the refresh cookie, not a token in the URL.
      window.history.replaceState({}, '', '/');
    }
    // fetchMe will try refresh cookie if no in-memory token
    refreshUser();
  }, [refreshUser]);

  useEffect(() => {
    setUnauthorizedHandler(() => {
      setUser(null);
      setLoading(false);
    });

    return () => setUnauthorizedHandler(null);
  }, []);

  const signIn = useCallback(async () => {
    window.location.href = buildGoogleAuthStartUrl();
  }, []);

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

  return (
    <AuthContext.Provider value={{ user, loading, signIn, signOut, connectGmail, connectCalendar, refreshUser }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  return useContext(AuthContext);
}
