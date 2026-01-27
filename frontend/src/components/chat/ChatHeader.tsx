import { Link, useNavigate, useLocation } from 'react-router-dom';
import { useAuth } from '../../contexts/AuthContext';
import { canManageUsers, canViewAllAuditLogs, getRoleDisplayName } from '../../utils/permissions';
import logo from '../../assets/logo.svg';

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

  const handleLogout = () => {
    logout();
    navigate('/login');
  };

  const isActive = (path: string) => location.pathname === path;

  const navLinks = [
    { path: '/chat', label: 'Chat', show: true },
    { path: '/insights', label: 'Insights', show: true },
    { path: '/config', label: 'Config', show: true },
    { path: '/history', label: 'History', show: true },
    { path: '/users', label: 'Users', show: canManageUsers(user) },
    { path: '/audit', label: 'Audit', show: canViewAllAuditLogs(user) },
  ];

  return (
    <header className="bg-white shadow-sm border-b border-gray-200 px-4 py-2.5">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-6">
          <div className="flex items-center gap-3">
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
            <img src={logo} alt="Logo" className="h-8" />
            <h1 className="text-lg font-semibold text-gray-900">{title}</h1>
          </div>

          {/* Navigation Links */}
          <nav className="flex items-center gap-1">
            {navLinks.filter(l => l.show).map(link => (
              <Link
                key={link.path}
                to={link.path}
                className={`px-3 py-1.5 rounded-md text-sm font-medium transition-colors ${isActive(link.path)
                  ? 'bg-blue-100 text-blue-700'
                  : 'text-gray-600 hover:text-gray-900 hover:bg-gray-100'
                  }`}
              >
                {link.label}
              </Link>
            ))}
          </nav>
        </div>

        <div className="flex items-center gap-4">
          {user && (
            <div className="text-right">
              <div className="text-sm font-medium text-gray-700">{user.username}</div>
              <div className="text-xs text-gray-500">{getRoleDisplayName(user.role)}</div>
            </div>
          )}
          <button
            onClick={handleLogout}
            className="text-sm text-gray-600 hover:text-gray-900 px-3 py-1 rounded-md hover:bg-gray-100 transition-colors"
          >
            Logout
          </button>
        </div>
      </div>
    </header>
  );
}
