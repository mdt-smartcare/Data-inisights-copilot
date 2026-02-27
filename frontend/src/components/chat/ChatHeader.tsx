import { useState, useRef, useEffect } from 'react';
import { Link, useNavigate, useLocation } from 'react-router-dom';
import { useAuth } from '../../contexts/AuthContext';
import { canManageUsers, canViewAllAuditLogs, canViewConfig, getRoleDisplayName } from '../../utils/permissions';
import logo from '../../assets/logo.svg';
import NotificationCenter from '../NotificationCenter';

interface ChatHeaderProps {
  title?: string;
  showBackButton?: boolean;
}

export default function ChatHeader({
  title,
  showBackButton = false
}: ChatHeaderProps) {
  const navigate = useNavigate();
  const location = useLocation();
  const { user, logout } = useAuth();
  const [showUserMenu, setShowUserMenu] = useState(false);
  const [showLogoutConfirm, setShowLogoutConfirm] = useState(false);
  const [showMobileMenu, setShowMobileMenu] = useState(false);
  const menuRef = useRef<HTMLDivElement>(null);
  const mobileMenuRef = useRef<HTMLDivElement>(null);

  // Close menus when clicking outside
  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (menuRef.current && !menuRef.current.contains(event.target as Node)) {
        setShowUserMenu(false);
        setShowLogoutConfirm(false);
      }
      if (mobileMenuRef.current && !mobileMenuRef.current.contains(event.target as Node)) {
        setShowMobileMenu(false);
      }
    };

    document.addEventListener('mousedown', handleClickOutside);
    return () => {
      document.removeEventListener('mousedown', handleClickOutside);
    };
  }, []);

  const handleLogout = async () => {
    try {
      await logout();
    } catch (error) {
      console.error('Logout failed:', error);
      // Fallback navigation if logout didn't redirect
      navigate('/login');
    }
  };

  const handleLogoutClick = () => {
    setShowLogoutConfirm(true);
  };

  const confirmLogout = async () => {
    setShowLogoutConfirm(false);
    setShowUserMenu(false);
    await handleLogout();
  };

  const isActive = (path: string) => location.pathname === path;

  const navLinks = [
    { path: '/chat', label: 'Chat', show: true },
    { path: '/agents', label: 'Agents', show: canViewConfig(user) },
    { path: '/users', label: 'Users', show: canManageUsers(user) },
    { path: '/audit', label: 'Audit', show: canViewAllAuditLogs(user) },
  ];

  return (
    <header className="bg-white shadow-sm border-b border-gray-200 px-3 sm:px-4 py-2 sm:py-2.5 w-full relative z-40 flex-shrink-0">
      <div className="flex items-center justify-between w-full">
        {/* Left side - Logo and Nav */}
        <div className="flex items-center gap-4 sm:gap-6 flex-1 min-w-0">
          {/* Logo */}
          <div className="flex items-center gap-2 flex-shrink-0">
            {showBackButton && (
              <Link
                to="/"
                className="text-gray-600 hover:text-gray-900 transition-colors"
              >
                <svg
                  className="w-4 h-4"
                  fill="none"
                  stroke="currentColor"
                  viewBox="0 0 24 24"
                >
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    strokeWidth={2}
                    d="M10 19l-7-7m0 0l7-7m-7 7h18"
                  />
                </svg>
              </Link>
            )}
            <img src={logo} alt="Logo" className="h-7 sm:h-8 w-auto" />
          </div>

          {/* Title - hidden on mobile */}
          <h1 className="text-base sm:text-lg font-semibold text-gray-900 truncate hidden md:block">
            {title}
          </h1>

          {/* Navigation Links - Hidden on mobile */}
          <nav className="hidden lg:flex items-center gap-1">
            {navLinks.filter(l => l.show).map(link => (
              <Link
                key={link.path}
                to={link.path}
                className={`px-3 py-1.5 rounded-md text-sm font-medium transition-colors whitespace-nowrap ${isActive(link.path)
                  ? 'bg-blue-100 text-blue-700'
                  : 'text-gray-600 hover:text-gray-900 hover:bg-gray-100'
                  }`}
              >
                {link.label}
              </Link>
            ))}
          </nav>
        </div>

        {/* Right side - Actions */}
        <div className="flex items-center gap-1 sm:gap-3 flex-shrink-0">
          {/* Mobile Navigation Menu */}
          <div className="lg:hidden" ref={mobileMenuRef}>
            <button
              onClick={() => setShowMobileMenu(!showMobileMenu)}
              className="p-2 rounded-md text-gray-600 hover:bg-gray-100"
              aria-label="Menu"
            >
              <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 6h16M4 12h16M4 18h16" />
              </svg>
            </button>
            {showMobileMenu && (
              <div className="fixed inset-0 z-50 lg:hidden" onClick={() => setShowMobileMenu(false)}>
                {/* Backdrop */}
                <div className="fixed inset-0 bg-black/30" />
                {/* Menu */}
                <div 
                  className="fixed top-12 right-2 w-44 bg-white rounded-lg shadow-xl border border-gray-200 py-1 z-50"
                  onClick={(e) => e.stopPropagation()}
                >
                  {navLinks.filter(l => l.show).map(link => (
                    <Link
                      key={link.path}
                      to={link.path}
                      onClick={() => setShowMobileMenu(false)}
                      className={`block px-4 py-2.5 text-sm font-medium ${isActive(link.path)
                        ? 'bg-blue-50 text-blue-700'
                        : 'text-gray-700 hover:bg-gray-100'
                        }`}
                    >
                      {link.label}
                    </Link>
                  ))}
                </div>
              </div>
            )}
          </div>
          
          <NotificationCenter />
          
          {user && (
            <div className="relative" ref={menuRef}>
              {/* User Menu Button */}
              <button
                onClick={() => setShowUserMenu(!showUserMenu)}
                className="flex items-center gap-1 sm:gap-2 p-1 sm:px-2 sm:py-1.5 rounded-lg hover:bg-gray-100 transition-colors"
                aria-label="User menu"
                aria-expanded={showUserMenu}
              >
                {/* User Avatar */}
                <div className="w-7 h-7 sm:w-8 sm:h-8 rounded-full bg-gradient-to-br from-blue-500 to-indigo-600 flex items-center justify-center text-white font-semibold text-xs sm:text-sm shadow-sm flex-shrink-0">
                  {user.username.charAt(0).toUpperCase()}
                </div>

                {/* User Info - hidden on mobile */}
                <div className="text-left hidden md:block">
                  <div className="text-sm font-medium text-gray-900 truncate max-w-[120px]">{user.username}</div>
                  <div className="text-xs text-gray-500">{getRoleDisplayName(user.role)}</div>
                </div>

                {/* Dropdown Icon - hidden on mobile */}
                <svg
                  className={`w-4 h-4 text-gray-500 transition-transform hidden sm:block ${showUserMenu ? 'rotate-180' : ''}`}
                  fill="none"
                  stroke="currentColor"
                  viewBox="0 0 24 24"
                >
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
                </svg>
              </button>

              {/* User Dropdown Menu - Full screen overlay on mobile */}
              {showUserMenu && (
                <>
                  {/* Mobile: Full screen overlay with top sheet */}
                  <div className="sm:hidden fixed inset-0 z-50" onClick={() => setShowUserMenu(false)}>
                    {/* Backdrop */}
                    <div className="fixed inset-0 bg-black/40" />
                    {/* Top Sheet Menu */}
                    <div 
                      className="fixed top-0 left-0 right-0 bg-white rounded-b-2xl shadow-2xl py-4 px-4 pt-12 z-50 animate-in slide-in-from-top duration-200"
                      onClick={(e) => e.stopPropagation()}
                    >
                      {/* User Profile Section */}
                      <div className="flex items-center gap-4 pb-4 border-b border-gray-100">
                        <div className="w-16 h-16 rounded-full bg-gradient-to-br from-blue-500 to-indigo-600 flex items-center justify-center text-white font-semibold text-2xl shadow-md flex-shrink-0">
                          {user.username.charAt(0).toUpperCase()}
                        </div>
                        <div className="flex-1 min-w-0">
                          <div className="text-lg font-semibold text-gray-900 truncate">{user.username}</div>
                          {user.email && (
                            <div className="text-sm text-gray-500 truncate mt-0.5">{user.email}</div>
                          )}
                          <div className="text-sm text-blue-600 font-medium mt-1">{getRoleDisplayName(user.role)}</div>
                        </div>
                        {/* Close button */}
                        <button 
                          onClick={() => setShowUserMenu(false)}
                          className="p-2 rounded-full hover:bg-gray-100 transition-colors"
                        >
                          <svg className="w-6 h-6 text-gray-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                          </svg>
                        </button>
                      </div>

                      {/* Logout Button */}
                      <div className="pt-4">
                        {showLogoutConfirm ? (
                          <div className="p-4 bg-red-50 rounded-xl border border-red-200">
                            <p className="text-base text-red-800 font-medium mb-4 text-center">Are you sure you want to logout?</p>
                            <div className="flex gap-3">
                              <button
                                onClick={confirmLogout}
                                className="flex-1 px-4 py-3.5 bg-red-600 text-white text-base font-semibold rounded-xl hover:bg-red-700 transition-colors active:scale-95"
                              >
                                Yes, Logout
                              </button>
                              <button
                                onClick={() => setShowLogoutConfirm(false)}
                                className="flex-1 px-4 py-3.5 bg-gray-200 text-gray-700 text-base font-semibold rounded-xl hover:bg-gray-300 transition-colors active:scale-95"
                              >
                                Cancel
                              </button>
                            </div>
                          </div>
                        ) : (
                          <button
                            onClick={handleLogoutClick}
                            className="w-full flex items-center justify-center gap-3 px-4 py-4 text-lg text-red-600 bg-red-50 hover:bg-red-100 rounded-xl transition-colors active:scale-95"
                          >
                            <svg
                              className="w-6 h-6"
                              fill="none"
                              stroke="currentColor"
                              viewBox="0 0 24 24"
                            >
                              <path
                                strokeLinecap="round"
                                strokeLinejoin="round"
                                strokeWidth={2}
                                d="M17 16l4-4m0 0l-4-4m4 4H7m6 4v1a3 3 0 01-3 3H6a3 3 0 01-3-3V7a3 3 0 013-3h4a3 3 0 013 3v1"
                              />
                            </svg>
                            <span className="font-semibold">Logout</span>
                          </button>
                        )}
                      </div>
                      
                      {/* Handle bar at bottom */}
                      <div className="w-10 h-1 bg-gray-300 rounded-full mx-auto mt-4" />
                    </div>
                  </div>

                  {/* Desktop: Regular dropdown */}
                  <div className="hidden sm:block absolute right-0 mt-2 w-72 bg-white rounded-xl shadow-xl border border-gray-200 py-3 z-50">
                    {/* User Profile Section */}
                    <div className="px-4 py-4 border-b border-gray-100">
                      <div className="flex items-center gap-4">
                        <div className="w-14 h-14 rounded-full bg-gradient-to-br from-blue-500 to-indigo-600 flex items-center justify-center text-white font-semibold text-xl shadow-md flex-shrink-0">
                          {user.username.charAt(0).toUpperCase()}
                        </div>
                        <div className="flex-1 min-w-0">
                          <div className="text-base font-semibold text-gray-900 truncate">{user.username}</div>
                          {user.email && (
                            <div className="text-sm text-gray-500 truncate mt-0.5">{user.email}</div>
                          )}
                          <div className="text-sm text-blue-600 font-medium mt-1">{getRoleDisplayName(user.role)}</div>
                        </div>
                      </div>
                    </div>

                    {/* Logout Button */}
                    <div className="px-3 py-2">
                      {showLogoutConfirm ? (
                        <div className="px-3 py-3 bg-red-50 rounded-lg border border-red-200">
                          <p className="text-sm text-red-800 font-medium mb-3">Are you sure you want to logout?</p>
                          <div className="flex gap-3">
                            <button
                              onClick={confirmLogout}
                              className="flex-1 px-4 py-2.5 bg-red-600 text-white text-sm font-medium rounded-lg hover:bg-red-700 transition-colors active:scale-95"
                            >
                              Yes, Logout
                            </button>
                            <button
                              onClick={() => setShowLogoutConfirm(false)}
                              className="flex-1 px-4 py-2.5 bg-gray-200 text-gray-700 text-sm font-medium rounded-lg hover:bg-gray-300 transition-colors active:scale-95"
                            >
                              Cancel
                            </button>
                          </div>
                        </div>
                      ) : (
                        <button
                          onClick={handleLogoutClick}
                          className="w-full flex items-center gap-4 px-4 py-3 text-base text-red-600 hover:bg-red-50 rounded-lg transition-colors group active:scale-98"
                        >
                          <svg
                            className="w-5 h-5 group-hover:scale-110 transition-transform"
                            fill="none"
                            stroke="currentColor"
                            viewBox="0 0 24 24"
                          >
                            <path
                              strokeLinecap="round"
                              strokeLinejoin="round"
                              strokeWidth={2}
                              d="M17 16l4-4m0 0l-4-4m4 4H7m6 4v1a3 3 0 01-3 3H6a3 3 0 01-3-3V7a3 3 0 013-3h4a3 3 0 013 3v1"
                            />
                          </svg>
                          <span className="font-semibold">Logout</span>
                        </button>
                      )}
                    </div>
                  </div>
                </>
              )}
            </div>
          )}
        </div>
      </div>
    </header>
  );
}
