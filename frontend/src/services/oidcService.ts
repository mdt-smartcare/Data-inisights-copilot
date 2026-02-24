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
  automaticSilentRenew: true,
  silentRequestTimeoutInSeconds: 30,
});

/**
 * OIDC Authentication Service
 * Provides methods for Keycloak OIDC authentication flow
 */
export const oidcService = {
  /**
   * Initiate login by redirecting to Keycloak login page
   */
  login: async (): Promise<void> => {
    await userManager.signinRedirect();
  },

  /**
   * Handle callback from Keycloak after successful authentication
   * @returns OidcUser object containing tokens and user info
   */
  handleCallback: async (): Promise<OidcUser> => {
    return await userManager.signinRedirectCallback();
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
   * Remove user from local storage (silent logout without redirect)
   */
  removeUser: async (): Promise<void> => {
    await userManager.removeUser();
  },

  /**
   * Get the access token for API calls
   * @returns Access token string or null if not authenticated
   */
  getAccessToken: async (): Promise<string | null> => {
    const user = await userManager.getUser();
    return user?.access_token || null;
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
   * Silent token renewal
   * @returns Renewed OidcUser or null if renewal fails
   */
  renewToken: async (): Promise<OidcUser | null> => {
    try {
      return await userManager.signinSilent();
    } catch (error) {
      console.error('Silent token renewal failed:', error);
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
