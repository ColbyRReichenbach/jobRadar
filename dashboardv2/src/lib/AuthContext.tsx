import { createContext, useContext, useEffect, useState, useCallback, ReactNode } from 'react';
import { UserProfile, fetchMe, clearAuthToken, getGoogleAuthUrl } from './api';

interface AuthContextType {
  user: UserProfile | null;
  loading: boolean;
  signIn: () => Promise<void>;
  signOut: () => void;
  connectGmail: () => Promise<void>;
  refreshUser: () => Promise<void>;
}

const AuthContext = createContext<AuthContextType>({
  user: null,
  loading: true,
  signIn: async () => {},
  signOut: () => {},
  connectGmail: async () => {},
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

  const signIn = useCallback(async () => {
    const url = await getGoogleAuthUrl(false);
    window.location.href = url;
  }, []);

  const signOut = useCallback(() => {
    clearAuthToken();
    setUser(null);
  }, []);

  const connectGmail = useCallback(async () => {
    const url = await getGoogleAuthUrl(true);
    window.location.href = url;
  }, []);

  return (
    <AuthContext.Provider value={{ user, loading, signIn, signOut, connectGmail, refreshUser }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  return useContext(AuthContext);
}
