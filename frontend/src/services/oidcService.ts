import { UserManager, WebStorageStateStore, User as OidcUser } from 'oidc-client-ts';
import { OIDC_CONFIG } from '../config';

/**
 * OIDC User Manager instance
 * Handles authentication flow with Keycloak IDP
 */
const userManager = new UserManager({
  authority: OIDC_CONFIG.authority,
  client_id: OIDC_CONFIG.client_id,
  redirect_uri: OIDC_CONFIG.redirect_uri,
  post_logout_redirect_uri: OIDC_CONFIG.post_logout_redirect_uri,
  scope: OIDC_CONFIG.scope,
  response_type: OIDC_CONFIG.response_type,
  userStore: new WebStorageStateStore({ store: window.localStorage }),
  // Enable automatic silent renewal - uses refresh_token via token endpoint
  automaticSilentRenew: true,
  // Fire accessTokenExpiring event 60 seconds before token expires
  accessTokenExpiringNotificationTimeInSeconds: 60,
  // Timeout for silent renew attempts
  silentRequestTimeoutInSeconds: 30,
});

// Key for signaling auth completion between tabs
const AUTH_COMPLETE_KEY = 'oidc_auth_complete';
const LOGIN_TIMEOUT_MS = 5 * 60 * 1000; // 5 minutes timeout for login

/**
 * OIDC Authentication Service
 * Provides methods for Keycloak OIDC authentication flow
 */
export const oidcService = {
  /**
   * Initiate login in a new browser tab
   * Opens Keycloak login in a new tab with proper PKCE/state handling
   * @returns OidcUser object after successful authentication
   */
  login: async (): Promise<OidcUser> => {
    // Clear any stale auth completion signal
    localStorage.removeItem(AUTH_COMPLETE_KEY);
    
    // Create signin request using the internal client (handles PKCE, state, nonce)
    // Note: createSigninRequest is on OidcClient, accessed via _client
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const client = (userManager as any)._client;
    const signinRequest = await client.createSigninRequest({});
    
    // Open in new tab
    const authTab = window.open(signinRequest.url, '_blank');
    
    if (!authTab) {
      throw new Error('Failed to open login tab. Please allow popups for this site.');
    }

    return new Promise((resolve, reject) => {
      let checkInterval: ReturnType<typeof setInterval> | null = null;
      let timeoutId: ReturnType<typeof setTimeout> | null = null;
      
      const cleanup = () => {
        window.removeEventListener('storage', handleStorageChange);
        if (checkInterval) clearInterval(checkInterval);
        if (timeoutId) clearTimeout(timeoutId);
      };

      // Listen for auth completion via storage event
      const handleStorageChange = async (event: StorageEvent) => {
        if (event.key === AUTH_COMPLETE_KEY && event.newValue === 'true') {
          cleanup();
          localStorage.removeItem(AUTH_COMPLETE_KEY);
          
          // Get the user from storage and validate
          const user = await userManager.getUser();
          if (user && !user.expired) {
            resolve(user);
          } else {
            reject(new Error('Authentication failed: No valid user found after login'));
          }
        }
      };

      window.addEventListener('storage', handleStorageChange);
      
      // Check periodically in case tab was closed
      checkInterval = setInterval(async () => {
        if (authTab.closed) {
          cleanup();
          // Check if auth completed before tab closed
          const user = await userManager.getUser();
          if (user && !user.expired) {
            localStorage.removeItem(AUTH_COMPLETE_KEY);
            resolve(user);
          } else {
            reject(new Error('Login cancelled: Tab was closed'));
          }
        }
      }, 500);
      
      // Timeout to prevent hanging forever
      timeoutId = setTimeout(() => {
        cleanup();
        try { authTab.close(); } catch { /* ignore */ }
        reject(new Error('Login timed out. Please try again.'));
      }, LOGIN_TIMEOUT_MS);
    });
  },

  /**
   * Handle callback from Keycloak in the new tab
   * Processes the callback, stores tokens, signals main window, and closes tab
   */
  handleTabCallback: async (): Promise<void> => {
    // Process the callback using the library (validates state, exchanges code)
    await userManager.signinRedirectCallback();
    
    // Signal the main window that auth is complete
    localStorage.setItem(AUTH_COMPLETE_KEY, 'true');
    
    // Close this tab
    window.close();
  },

  /**
   * Check if current window is a callback (has auth code in URL)
   */
  isTabCallback: (): boolean => {
    return window.location.search.includes('code=') && window.location.search.includes('state=');
  },

  /**
   * Get the current authenticated user
   * @returns OidcUser if authenticated, null otherwise
   */
  getUser: async (): Promise<OidcUser | null> => {
    return await userManager.getUser();
  },

  /**
   * Logout user and redirect to Keycloak logout page
   */
  logout: async (): Promise<void> => {
    await userManager.signoutRedirect();
  },

  /**
   * Logout user and redirect to login with an error message
   * Clears Keycloak SSO session so user must re-authenticate
   */
  logoutWithMessage: async (errorCode: string): Promise<void> => {
    const redirectUrl = `${window.location.origin}/login?error=${errorCode}`;
    await userManager.signoutRedirect({ post_logout_redirect_uri: redirectUrl });
  },

  /**
   * Remove user from local storage (silent logout without redirect)
   */
  removeUser: async (): Promise<void> => {
    await userManager.removeUser();
  },

  /**
   * Get the access token for API calls
   * Checks expiration and attempts renewal if needed
   * @returns Access token string or null if not authenticated/renewal failed
   */
  getAccessToken: async (): Promise<string | null> => {
    const user = await userManager.getUser();
    if (!user) {
      return null;
    }
    
    // If token is expired or expiring soon, try to renew
    if (user.expired) {
      // Token is expired - automaticSilentRenew should handle this,
      // but let's try manual renewal as fallback
      try {
        const renewedUser = await userManager.signinSilent();
        return renewedUser?.access_token || null;
      } catch {
        return null;
      }
    }
    
    return user.access_token;
  },

  /**
   * Check if user is authenticated
   * @returns true if user has valid token, false otherwise
   */
  isAuthenticated: async (): Promise<boolean> => {
    const user = await userManager.getUser();
    return !!user && !user.expired;
  },

  /**
   * Silent token renewal using refresh token
   * Note: We avoid iframe-based signinSilent() as it often times out.
   * Instead, we use the refresh token directly if available.
   * @returns Renewed OidcUser or null if renewal fails
   */
  renewToken: async (): Promise<OidcUser | null> => {
    try {
      const currentUser = await userManager.getUser();
      // Only attempt renewal if we have a user with a refresh token
      if (!currentUser?.refresh_token) {
        return null;
      }
      // Use signinSilent with refresh token - this should work without iframe
      // if the IDP supports refresh tokens
      return await userManager.signinSilent();
    } catch (error) {
      console.error('Silent token renewal failed:', error);
      // Don't spam console with expected errors
      return null;
    }
  },

  /**
   * Get the UserManager instance for advanced use cases
   * @returns UserManager instance
   */
  getUserManager: (): UserManager => userManager,
};

// Export the OIDC User type for use in other components
export type { OidcUser };
