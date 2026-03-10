import { createContext, useContext, useState, useEffect, useCallback, type ReactNode } from 'react';
import { oidcService, type OidcUser } from '../services/oidcService';
import { apiClient } from '../services/api';
import type { User } from '../types';


/**
 * Authentication context interface
 * Provides user state and authentication methods throughout the app
 */
export interface AuthContextType {
  user: User | null;                       // Current authenticated user (null if not logged in)
  setUser: (user: User | null) => void;    // Update user state (used after login)
  isAuthenticated: boolean;                 // Quick check if user is logged in
  logout: () => void;                       // Logout function to clear auth state
  isLoading: boolean;                       // Loading state during session restoration
  login: () => Promise<void>;              // Initiate OIDC login flow
  getAccessToken: () => Promise<string | null>; // Get current access token
}

// Create context with undefined as initial value
// This forces consumers to use the context within AuthProvider
const AuthContext = createContext<AuthContextType | undefined>(undefined);

/**
 * Fetch user profile from backend API
 * Returns user details including role from the /auth/me endpoint
 */
async function fetchUserProfile(): Promise<User | null> {
  try {
    const response = await apiClient.get<User>('/api/v1/auth/me');
    return response.data;
  } catch (error) {
    console.error('Error fetching user profile:', error);
    return null;
  }
}

/**
 * Authentication Provider Component
 * Wraps the entire application to provide authentication state globally
 * Uses Keycloak OIDC for authentication
 * 
 * Usage:
 *   <AuthProvider>
 *     <App />
 *   </AuthProvider>
 */
export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [oidcUser, setOidcUser] = useState<OidcUser | null>(null);

  // Initialize auth state from OIDC session
  useEffect(() => {
    const initAuth = async () => {
      try {
        const currentOidcUser = await oidcService.getUser();
        if (currentOidcUser && !currentOidcUser.expired) {
          setOidcUser(currentOidcUser);
          const userProfile = await fetchUserProfile();
          setUser(userProfile);
        }
      } catch (error) {
        console.error('Failed to restore OIDC session:', error);
      } finally {
        setIsLoading(false);
      }
    };

    initAuth();

    // Set up event listeners for token events
    const userManager = oidcService.getUserManager();
    
    const handleUserLoaded = async (loadedUser: OidcUser) => {
      setOidcUser(loadedUser);
      const userProfile = await fetchUserProfile();
      setUser(userProfile);
    };

    const handleUserUnloaded = () => {
      setOidcUser(null);
      setUser(null);
    };

    const handleSilentRenewError = (error: Error) => {
      console.error('Silent renew error:', error);
    };

    userManager.events.addUserLoaded(handleUserLoaded);
    userManager.events.addUserUnloaded(handleUserUnloaded);
    userManager.events.addSilentRenewError(handleSilentRenewError);

    return () => {
      userManager.events.removeUserLoaded(handleUserLoaded);
      userManager.events.removeUserUnloaded(handleUserUnloaded);
      userManager.events.removeSilentRenewError(handleSilentRenewError);
    };
  }, []);

  /**
   * Initiate OIDC login flow - redirects to Keycloak
   */
  const login = useCallback(async () => {
    await oidcService.login();
  }, []);

  /**
   * Logout function
   * Clears OIDC session and redirects to Keycloak logout
   */
  const logout = useCallback(async () => {
    try {
      await oidcService.logout();
    } catch (error) {
      console.error('Logout error:', error);
      // Fallback: remove user locally if redirect fails
      await oidcService.removeUser();
      setUser(null);
      setOidcUser(null);
      window.location.href = '/login';
    }
  }, []);

  /**
   * Get the current access token for API calls
   */
  const getAccessToken = useCallback(async () => {
    return await oidcService.getAccessToken();
  }, []);

  // Check if user is authenticated
  const isAuthenticated = !!user && !!oidcUser && !oidcUser.expired;

  return (
    <AuthContext.Provider value={{ 
      user, 
      setUser, 
      isAuthenticated, 
      logout, 
      isLoading,
      login,
      getAccessToken
    }}>
      {children}
    </AuthContext.Provider>
  );
}


// eslint-disable-next-line react-refresh/only-export-components
export function useAuth() {
  const context = useContext(AuthContext);
  if (context === undefined) {
    throw new Error('useAuth must be used within an AuthProvider');
  }
  return context;
}