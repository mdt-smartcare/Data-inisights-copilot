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
        if (currentOidcUser) {
          // Token exists - check if it's still valid
          if (!currentOidcUser.expired) {
            // Token is valid, use it
            setOidcUser(currentOidcUser);
            const userProfile = await fetchUserProfile();
            setUser(userProfile);
          } else if (currentOidcUser.refresh_token) {
            // Access token expired but we have a refresh token - try to renew
            console.log('Access token expired, attempting renewal...');
            const renewedUser = await oidcService.renewToken();
            if (renewedUser && !renewedUser.expired) {
              setOidcUser(renewedUser);
              const userProfile = await fetchUserProfile();
              setUser(userProfile);
            } else {
              // Renewal failed, clear the stale token
              console.log('Token renewal failed, clearing session');
              await oidcService.removeUser();
            }
          } else {
            // Token expired and no refresh token - clear it
            console.log('Token expired with no refresh token, clearing session');
            await oidcService.removeUser();
          }
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
      // Only fetch profile on initial login, not on token renewal
      // User profile doesn't change just because token was refreshed
      setUser(currentUser => {
        if (!currentUser) {
          // No user yet - this is initial login, fetch profile
          fetchUserProfile().then(profile => setUser(profile));
        }
        return currentUser;
      });
    };

    const handleUserUnloaded = () => {
      setOidcUser(null);
      setUser(null);
    };

    const handleSilentRenewError = (error: Error) => {
      console.error('Silent renew error:', error);
      // If renewal fails due to iframe timeout, the token might still be usable
      // Don't clear the session here - let the API interceptor handle 401s
    };

    const handleAccessTokenExpiring = () => {
      console.log('Access token expiring soon, automatic renewal in progress...');
    };

    const handleAccessTokenExpired = async () => {
      console.log('Access token expired');
      // Token expired - automatic renewal should have kicked in
      // If we get here, renewal may have failed
    };

    userManager.events.addUserLoaded(handleUserLoaded);
    userManager.events.addUserUnloaded(handleUserUnloaded);
    userManager.events.addSilentRenewError(handleSilentRenewError);
    userManager.events.addAccessTokenExpiring(handleAccessTokenExpiring);
    userManager.events.addAccessTokenExpired(handleAccessTokenExpired);

    return () => {
      userManager.events.removeUserLoaded(handleUserLoaded);
      userManager.events.removeUserUnloaded(handleUserUnloaded);
      userManager.events.removeSilentRenewError(handleSilentRenewError);
      userManager.events.removeAccessTokenExpiring(handleAccessTokenExpiring);
      userManager.events.removeAccessTokenExpired(handleAccessTokenExpired);
    };
  }, []);

  /**
   * Initiate OIDC login flow via new tab
   * Opens Keycloak login in a new tab and updates state after success
   */
  const login = useCallback(async () => {
    const oidcUserResult = await oidcService.login();
    setOidcUser(oidcUserResult);
    const userProfile = await fetchUserProfile();
    setUser(userProfile);
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