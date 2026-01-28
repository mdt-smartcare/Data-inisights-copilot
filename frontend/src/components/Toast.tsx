/**
 * Toast notification component for ephemeral user feedback.
 */
import React, { useState, useEffect, useCallback } from 'react';
import './Toast.css';

export type ToastType = 'success' | 'error' | 'info' | 'warning';

export interface ToastData {
    id: string;
    type: ToastType;
    title: string;
    message?: string;
    action?: {
        label: string;
        onClick: () => void;
    };
    duration?: number; // ms, default 5000
}

interface ToastProps extends ToastData {
    onClose: (id: string) => void;
}

const TOAST_ICONS: Record<ToastType, string> = {
    success: '✓',
    error: '✕',
    info: 'ℹ',
    warning: '⚠',
};

const Toast: React.FC<ToastProps> = ({
    id,
    type,
    title,
    message,
    action,
    duration = 5000,
    onClose,
}) => {
    const [isExiting, setIsExiting] = useState(false);

    const handleClose = useCallback(() => {
        setIsExiting(true);
        setTimeout(() => onClose(id), 300); // Match exit animation duration
    }, [id, onClose]);

    // Auto-dismiss
    useEffect(() => {
        if (duration > 0) {
            const timer = setTimeout(handleClose, duration);
            return () => clearTimeout(timer);
        }
    }, [duration, handleClose]);

    return (
        <div className={`toast toast--${type} ${isExiting ? 'toast--exiting' : ''}`}>
            <div className="toast__icon">{TOAST_ICONS[type]}</div>
            <div className="toast__content">
                <div className="toast__title">{title}</div>
                {message && <div className="toast__message">{message}</div>}
            </div>
            {action && (
                <button className="toast__action" onClick={action.onClick}>
                    {action.label}
                </button>
            )}
            <button className="toast__close" onClick={handleClose} aria-label="Close">
                ×
            </button>
        </div>
    );
};

// Toast Container and Context
interface ToastContextValue {
    showToast: (toast: Omit<ToastData, 'id'>) => void;
    success: (title: string, message?: string) => void;
    error: (title: string, message?: string) => void;
    info: (title: string, message?: string) => void;
    warning: (title: string, message?: string) => void;
}

const ToastContext = React.createContext<ToastContextValue | null>(null);

export const ToastProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
    const [toasts, setToasts] = useState<ToastData[]>([]);

    const showToast = useCallback((toast: Omit<ToastData, 'id'>) => {
        const id = `toast-${Date.now()}-${Math.random().toString(36).slice(2, 9)}`;
        setToasts(prev => [...prev, { ...toast, id }]);
    }, []);

    const removeToast = useCallback((id: string) => {
        setToasts(prev => prev.filter(t => t.id !== id));
    }, []);

    const success = useCallback((title: string, message?: string) => {
        showToast({ type: 'success', title, message });
    }, [showToast]);

    const error = useCallback((title: string, message?: string) => {
        showToast({ type: 'error', title, message, duration: 8000 }); // Longer for errors
    }, [showToast]);

    const info = useCallback((title: string, message?: string) => {
        showToast({ type: 'info', title, message });
    }, [showToast]);

    const warning = useCallback((title: string, message?: string) => {
        showToast({ type: 'warning', title, message, duration: 6000 });
    }, [showToast]);

    return (
        <ToastContext.Provider value={{ showToast, success, error, info, warning }}>
            {children}
            <div className="toast-container">
                {toasts.map(toast => (
                    <Toast key={toast.id} {...toast} onClose={removeToast} />
                ))}
            </div>
        </ToastContext.Provider>
    );
};

export const useToast = (): ToastContextValue => {
    const context = React.useContext(ToastContext);
    if (!context) {
        throw new Error('useToast must be used within a ToastProvider');
    }
    return context;
};

export default Toast;
