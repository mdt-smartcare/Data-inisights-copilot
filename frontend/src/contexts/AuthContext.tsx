import { createContext, useContext, useState, useEffect, type ReactNode } from 'react';
import { getUserProfile } from '../services/api';
import type { User } from '../types';


/**
 * Authentication context interface
 * Provides user state and authentication methods throughout the app
 */
interface AuthContextType {
  user: User | null;                       // Current authenticated user (null if not logged in)
  setUser: (user: User | null) => void;    // Update user state (used after login)
  isAuthenticated: boolean;                 // Quick check if user is logged in
  logout: () => void;                       // Logout function to clear auth state
  isLoading: boolean;                       // Loading state during session restoration
}

// Create context with undefined as initial value
// This forces consumers to use the context within AuthProvider
const AuthContext = createContext<AuthContextType | undefined>(undefined);

/**
 * Authentication Provider Component
 * Wraps the entire application to provide authentication state globally
 * 
 * Usage:
 *   <AuthProvider>
 *     <App />
 *   </AuthProvider>
 */
export function AuthProvider({ children }: { children: ReactNode }) {
  // User state stored in memory (not persisted across page refreshes)
  // Actual authentication persistence is handled by localStorage tokens
  const [user, setUser] = useState<User | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    const restoreSession = async () => {
      const token = localStorage.getItem('auth_token');
      if (token && !user) {
        try {
          const profile = await getUserProfile();
          // Map backend user to frontend user type if needed, but they should match
          setUser(profile);
        } catch (error) {
          console.error("Failed to restore session", error);
          // If token is invalid, clear it
          localStorage.removeItem('auth_token');
          localStorage.removeItem('expiresAt');
        }
      }
      setIsLoading(false);
    };

    restoreSession();
  }, []); // Run once on mount

  /**
   * Logout function
   * Clears all authentication data from both memory and localStorage
   */
  const logout = () => {
    setUser(null);                                // Clear user from memory
    localStorage.removeItem('auth_token');        // Remove JWT token
    localStorage.removeItem('expiresAt');         // Remove expiration timestamp
  };

  // Check if user is authenticated by verifying both user state and token existence
  // This double-check ensures consistency between memory and localStorage
  const isAuthenticated = !!user && !!localStorage.getItem('auth_token');

  return (
    <AuthContext.Provider value={{ user, setUser, isAuthenticated, logout, isLoading }}>
      {children}
    </AuthContext.Provider>
  );
}

/**
 * Custom hook to access authentication context
 * 
 * Usage:
 *   const { user, logout, isAuthenticated, setUser } = useAuth();
 * 
 * @throws Error if used outside of AuthProvider
 * @returns AuthContextType - Authentication state and methods
 * 
 * Example:
 *   function MyComponent() {
 *     const { user, logout } = useAuth();
 *     return <div>Welcome {user?.username} <button onClick={logout}>Logout</button></div>
 *   }
 */
export function useAuth() {
  const context = useContext(AuthContext);
  if (context === undefined) {
    throw new Error('useAuth must be used within an AuthProvider');
  }
  return context;
}
