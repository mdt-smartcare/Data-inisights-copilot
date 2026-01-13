import { Link, useNavigate } from 'react-router-dom';
import { useAuth } from '../../contexts/AuthContext';
import { APP_CONFIG } from '../../config';
import logo from '../../assets/logo.svg';

interface ChatHeaderProps {
  title?: string;
  showBackButton?: boolean;
}

export default function ChatHeader({ 
  title = APP_CONFIG.APP_NAME,
  showBackButton = false 
}: ChatHeaderProps) {
  const navigate = useNavigate();
  const { user, logout } = useAuth();

  const handleLogout = () => {
    logout();
    navigate('/login');
  };

  return (
    <header className="bg-white shadow-sm border-b border-gray-200 px-4 py-2.5">
      <div className="flex items-center justify-between">
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

        <div className="flex items-center gap-4">
          {user?.username && (
            <span className="text-sm text-gray-600">
              Welcome, <span className="font-medium">{user.username}</span>
            </span>
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
