import React, { useState } from 'react';
import { type AgentConfig, activateConfig } from '../../services/api';
import { useDismissedVersionAlert } from '../../hooks';
import ConfirmationModal from '../ConfirmationModal';

interface NewVersionAlertProps {
  /** The inactive published config that could be activated */
  inactiveConfig: AgentConfig;
  /** The currently active config version (for comparison in the message) */
  activeVersion?: number;
  /** Agent ID for the dismiss key */
  agentId: string;
  /** Callback when version is successfully activated */
  onActivated?: () => void;
  /** Optional additional class names */
  className?: string;
}

/**
 * Alert banner shown on the Overview tab when a newer published config version
 * exists but isn't active. Users can enable it directly via one-click activation
 * with confirmation, or dismiss it (persisted via localStorage until a newer
 * version is created).
 */
export default function NewVersionAlert({
  inactiveConfig,
  activeVersion,
  agentId,
  onActivated,
  className = '',
}: NewVersionAlertProps) {
  const [showConfirmModal, setShowConfirmModal] = useState(false);
  const [isActivating, setIsActivating] = useState(false);
  
  const { isDismissed, dismiss } = useDismissedVersionAlert(
    agentId,
    inactiveConfig.version
  );

  // Don't render if already dismissed
  if (isDismissed) {
    return null;
  }

  const handleEnableClick = () => {
    setShowConfirmModal(true);
  };

  const handleConfirmActivate = async () => {
    setIsActivating(true);
    try {
      await activateConfig(inactiveConfig.id);
      setShowConfirmModal(false);
      onActivated?.();
    } catch (error) {
      console.error('Failed to activate config:', error);
      // Keep modal open on error so user can retry
    } finally {
      setIsActivating(false);
    }
  };

  const handleCancelActivate = () => {
    setShowConfirmModal(false);
  };

  const handleDismiss = () => {
    dismiss();
  };

  const versionMessage = activeVersion
    ? `Version ${inactiveConfig.version} is available but not active. Currently using version ${activeVersion}.`
    : `Version ${inactiveConfig.version} is available but not active.`;

  return (
    <>
      <div
        className={`
          mb-4 p-4 rounded-md shadow-sm
          bg-blue-50 border-l-4 border-blue-400 text-blue-700
          ${className}
        `}
        role="alert"
        aria-live="polite"
      >
        <div className="flex items-start gap-3">
          {/* Info icon */}
          <div className="flex-shrink-0 mt-0.5">
            <svg className="w-5 h-5 text-blue-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
            </svg>
          </div>
          
          {/* Content */}
          <div className="flex-1 min-w-0">
            <p className="font-medium text-sm leading-relaxed">
              {versionMessage}
            </p>
          </div>

          {/* Actions */}
          <div className="flex-shrink-0 flex items-center gap-2">
            <button
              onClick={handleEnableClick}
              className="px-3 py-1.5 text-sm font-medium text-white bg-blue-600 hover:bg-blue-700 rounded-md shadow-sm transition-colors focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2"
            >
              Enable Now
            </button>
            <button
              onClick={handleDismiss}
              className="text-blue-500 opacity-70 hover:opacity-100 transition-opacity p-1 rounded hover:bg-blue-100 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2 focus:ring-offset-transparent"
              aria-label="Dismiss alert"
              title="Dismiss"
            >
              <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
              </svg>
            </button>
          </div>
        </div>
      </div>

      {/* Confirmation Modal */}
      <ConfirmationModal
        show={showConfirmModal}
        title="Activate Configuration"
        message={`Are you sure you want to activate version ${inactiveConfig.version}? This will deactivate the current active configuration.`}
        onConfirm={handleConfirmActivate}
        onCancel={handleCancelActivate}
        confirmText="Activate"
        cancelText="Cancel"
        type="info"
        isLoading={isActivating}
      />
    </>
  );
}
