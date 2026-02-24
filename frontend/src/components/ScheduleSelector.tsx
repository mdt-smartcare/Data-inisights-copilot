import React, { useState, useEffect, useCallback } from 'react';
import {
    createVectorDbSchedule,
    getVectorDbSchedule,
    deleteVectorDbSchedule,
    triggerVectorDbSync,
    handleApiError,
    type VectorDbSchedule,
    type ScheduleCreateRequest
} from '../services/api';

interface ScheduleSelectorProps {
    vectorDbName: string;
    readOnly?: boolean;
    onScheduleChange?: (schedule: VectorDbSchedule | null) => void;
}

const DAYS_OF_WEEK = [
    { value: 0, label: 'Monday' },
    { value: 1, label: 'Tuesday' },
    { value: 2, label: 'Wednesday' },
    { value: 3, label: 'Thursday' },
    { value: 4, label: 'Friday' },
    { value: 5, label: 'Saturday' },
    { value: 6, label: 'Sunday' },
];

const ScheduleSelector: React.FC<ScheduleSelectorProps> = ({
    vectorDbName,
    readOnly = false,
    onScheduleChange
}) => {
    const [schedule, setSchedule] = useState<VectorDbSchedule | null>(null);
    const [loading, setLoading] = useState(true);
    const [saving, setSaving] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const [success, setSuccess] = useState<string | null>(null);

    // Form state
    const [enabled, setEnabled] = useState(true);
    const [scheduleType, setScheduleType] = useState<'hourly' | 'daily' | 'weekly' | 'custom'>('daily');
    const [hour, setHour] = useState(2);
    const [minute, setMinute] = useState(0);
    const [dayOfWeek, setDayOfWeek] = useState(0);
    const [cronExpression, setCronExpression] = useState('');

    // Countdown state
    const [countdown, setCountdown] = useState<number | null>(null);

    // Load existing schedule
    const loadSchedule = useCallback(async () => {
        if (!vectorDbName) return;
        
        setLoading(true);
        setError(null);
        
        try {
            const data = await getVectorDbSchedule(vectorDbName);
            setSchedule(data);
            setEnabled(data.enabled);
            setScheduleType(data.schedule_type);
            setHour(data.schedule_hour);
            setMinute(data.schedule_minute);
            if (data.schedule_day_of_week !== undefined) {
                setDayOfWeek(data.schedule_day_of_week);
            }
            if (data.schedule_cron) {
                setCronExpression(data.schedule_cron);
            }
            if (data.countdown_seconds !== undefined) {
                setCountdown(data.countdown_seconds);
            }
            onScheduleChange?.(data);
        } catch (err: any) {
            // 404 means no schedule exists yet, which is fine
            if (err.response?.status !== 404) {
                setError(handleApiError(err));
            }
            setSchedule(null);
            onScheduleChange?.(null);
        } finally {
            setLoading(false);
        }
    }, [vectorDbName, onScheduleChange]);

    useEffect(() => {
        loadSchedule();
    }, [loadSchedule]);

    // Countdown timer
    useEffect(() => {
        if (countdown === null || countdown <= 0 || !enabled) return;

        const timer = setInterval(() => {
            setCountdown(prev => {
                if (prev === null || prev <= 0) return null;
                return prev - 1;
            });
        }, 1000);

        return () => clearInterval(timer);
    }, [countdown, enabled]);

    // Refresh countdown periodically
    useEffect(() => {
        if (!schedule?.enabled) return;

        const refreshInterval = setInterval(() => {
            loadSchedule();
        }, 60000); // Refresh every minute

        return () => clearInterval(refreshInterval);
    }, [schedule?.enabled, loadSchedule]);

    const handleSave = async () => {
        if (readOnly || !vectorDbName) return;

        setSaving(true);
        setError(null);
        setSuccess(null);

        try {
            const request: ScheduleCreateRequest = {
                schedule_type: scheduleType,
                hour,
                minute,
                enabled,
            };

            if (scheduleType === 'weekly') {
                request.day_of_week = dayOfWeek;
            }

            if (scheduleType === 'custom' && cronExpression) {
                request.cron_expression = cronExpression;
            }

            const result = await createVectorDbSchedule(vectorDbName, request);
            setSchedule(result.schedule);
            setCountdown(result.schedule.countdown_seconds ?? null);
            setSuccess('Schedule saved successfully');
            onScheduleChange?.(result.schedule);

            setTimeout(() => setSuccess(null), 3000);
        } catch (err) {
            setError(handleApiError(err));
        } finally {
            setSaving(false);
        }
    };

    const handleDelete = async () => {
        if (readOnly || !vectorDbName) return;

        setSaving(true);
        setError(null);

        try {
            await deleteVectorDbSchedule(vectorDbName);
            setSchedule(null);
            setCountdown(null);
            setSuccess('Schedule deleted');
            onScheduleChange?.(null);

            setTimeout(() => setSuccess(null), 3000);
        } catch (err) {
            setError(handleApiError(err));
        } finally {
            setSaving(false);
        }
    };

    const handleTriggerNow = async () => {
        if (readOnly || !vectorDbName) return;

        setSaving(true);
        setError(null);

        try {
            await triggerVectorDbSync(vectorDbName);
            setSuccess('Sync triggered! Check embedding jobs for progress.');
            setTimeout(() => setSuccess(null), 5000);
        } catch (err) {
            setError(handleApiError(err));
        } finally {
            setSaving(false);
        }
    };

    const formatCountdown = (seconds: number): string => {
        const hours = Math.floor(seconds / 3600);
        const mins = Math.floor((seconds % 3600) / 60);
        const secs = seconds % 60;

        if (hours > 0) {
            return `${hours}h ${mins}m ${secs}s`;
        } else if (mins > 0) {
            return `${mins}m ${secs}s`;
        }
        return `${secs}s`;
    };

    const getScheduleDescription = (): string => {
        switch (scheduleType) {
            case 'hourly':
                return `Every hour at :${minute.toString().padStart(2, '0')}`;
            case 'daily':
                return `Daily at ${hour.toString().padStart(2, '0')}:${minute.toString().padStart(2, '0')} UTC`;
            case 'weekly':
                const dayName = DAYS_OF_WEEK.find(d => d.value === dayOfWeek)?.label || 'Monday';
                return `Every ${dayName} at ${hour.toString().padStart(2, '0')}:${minute.toString().padStart(2, '0')} UTC`;
            case 'custom':
                return cronExpression || 'Custom cron schedule';
            default:
                return '';
        }
    };

    if (loading) {
        return (
            <div className="p-4 bg-gray-50 rounded-lg border border-gray-200 animate-pulse">
                <div className="h-4 bg-gray-200 rounded w-1/3 mb-4"></div>
                <div className="h-8 bg-gray-200 rounded w-full"></div>
            </div>
        );
    }

    return (
        <div className="bg-white p-6 rounded-lg border border-gray-200 shadow-sm">
            <div className="flex items-center gap-3 mb-4">
                <div className="p-2 bg-blue-100 rounded-full">
                    <svg className="w-5 h-5 text-blue-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
                    </svg>
                </div>
                <h3 className="text-lg font-medium text-gray-900">Sync Schedule</h3>
                {schedule?.enabled && countdown !== null && countdown > 0 && (
                    <span className="ml-auto inline-flex items-center px-3 py-1 rounded-full text-sm font-medium bg-blue-100 text-blue-800">
                        <svg className="w-4 h-4 mr-1.5 animate-pulse" fill="currentColor" viewBox="0 0 20 20">
                            <circle cx="10" cy="10" r="3" />
                        </svg>
                        Next sync in: {formatCountdown(countdown)}
                    </span>
                )}
            </div>

            {/* Status Messages */}
            {error && (
                <div className="mb-4 px-4 py-3 rounded-lg text-sm font-medium bg-red-50 text-red-800 border border-red-200">
                    ✗ {error}
                </div>
            )}
            {success && (
                <div className="mb-4 px-4 py-3 rounded-lg text-sm font-medium bg-green-50 text-green-800 border border-green-200">
                    ✓ {success}
                </div>
            )}

            {/* Enable/Disable Toggle */}
            <div className="flex items-center justify-between mb-6 p-4 bg-gray-50 rounded-lg">
                <div>
                    <label className="block text-sm font-medium text-gray-900">Enable Automatic Sync</label>
                    <p className="text-xs text-gray-500 mt-0.5">
                        Automatically sync embeddings on a schedule
                    </p>
                </div>
                <label className="relative inline-flex items-center cursor-pointer">
                    <input
                        type="checkbox"
                        className="sr-only peer"
                        checked={enabled}
                        onChange={(e) => setEnabled(e.target.checked)}
                        disabled={readOnly}
                    />
                    <div className="w-11 h-6 bg-gray-300 hover:bg-gray-400 peer-focus:outline-none rounded-full peer peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-gray-300 after:border after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:bg-blue-600"></div>
                </label>
            </div>

            {/* Schedule Configuration */}
            <div className={`space-y-4 transition-opacity ${enabled ? 'opacity-100' : 'opacity-50 pointer-events-none'}`}>
                {/* Schedule Type */}
                <div>
                    <label className="block text-sm font-medium text-gray-700 mb-2">Schedule Type</label>
                    <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
                        {(['hourly', 'daily', 'weekly', 'custom'] as const).map((type) => (
                            <button
                                key={type}
                                type="button"
                                onClick={() => setScheduleType(type)}
                                disabled={readOnly}
                                className={`px-4 py-2 text-sm font-medium rounded-lg border-2 transition-all ${
                                    scheduleType === type
                                        ? 'border-blue-500 bg-blue-50 text-blue-700'
                                        : 'border-gray-200 bg-white text-gray-700 hover:border-gray-300'
                                }`}
                            >
                                {type.charAt(0).toUpperCase() + type.slice(1)}
                            </button>
                        ))}
                    </div>
                </div>

                {/* Time Selection */}
                {scheduleType !== 'custom' && (
                    <div className="grid grid-cols-2 gap-4">
                        {scheduleType !== 'hourly' && (
                            <div>
                                <label className="block text-sm font-medium text-gray-700 mb-1">Hour (UTC)</label>
                                <select
                                    value={hour}
                                    onChange={(e) => setHour(parseInt(e.target.value))}
                                    disabled={readOnly}
                                    className="w-full rounded-md border-gray-300 shadow-sm focus:border-blue-500 focus:ring-blue-500 sm:text-sm p-2 border"
                                >
                                    {Array.from({ length: 24 }, (_, i) => (
                                        <option key={i} value={i}>
                                            {i.toString().padStart(2, '0')}:00
                                        </option>
                                    ))}
                                </select>
                            </div>
                        )}
                        <div>
                            <label className="block text-sm font-medium text-gray-700 mb-1">Minute</label>
                            <select
                                value={minute}
                                onChange={(e) => setMinute(parseInt(e.target.value))}
                                disabled={readOnly}
                                className="w-full rounded-md border-gray-300 shadow-sm focus:border-blue-500 focus:ring-blue-500 sm:text-sm p-2 border"
                            >
                                {[0, 15, 30, 45].map((m) => (
                                    <option key={m} value={m}>
                                        :{m.toString().padStart(2, '0')}
                                    </option>
                                ))}
                            </select>
                        </div>
                    </div>
                )}

                {/* Day of Week (for weekly) */}
                {scheduleType === 'weekly' && (
                    <div>
                        <label className="block text-sm font-medium text-gray-700 mb-1">Day of Week</label>
                        <select
                            value={dayOfWeek}
                            onChange={(e) => setDayOfWeek(parseInt(e.target.value))}
                            disabled={readOnly}
                            className="w-full rounded-md border-gray-300 shadow-sm focus:border-blue-500 focus:ring-blue-500 sm:text-sm p-2 border"
                        >
                            {DAYS_OF_WEEK.map((day) => (
                                <option key={day.value} value={day.value}>
                                    {day.label}
                                </option>
                            ))}
                        </select>
                    </div>
                )}

                {/* Custom Cron Expression */}
                {scheduleType === 'custom' && (
                    <div>
                        <label className="block text-sm font-medium text-gray-700 mb-1">Cron Expression</label>
                        <input
                            type="text"
                            value={cronExpression}
                            onChange={(e) => setCronExpression(e.target.value)}
                            placeholder="0 2 * * *"
                            disabled={readOnly}
                            className="w-full rounded-md border-gray-300 shadow-sm focus:border-blue-500 focus:ring-blue-500 sm:text-sm p-2 border"
                        />
                        <p className="mt-1 text-xs text-gray-500">
                            Standard cron format: minute hour day month day-of-week
                        </p>
                    </div>
                )}

                {/* Schedule Description */}
                <div className="p-3 bg-blue-50 rounded-lg border border-blue-200">
                    <p className="text-sm text-blue-800">
                        <span className="font-medium">Schedule: </span>
                        {getScheduleDescription()}
                    </p>
                </div>

                {/* Last Run Status */}
                {schedule?.last_run_at && (
                    <div className="p-3 bg-gray-50 rounded-lg border border-gray-200">
                        <div className="flex items-center justify-between">
                            <div>
                                <p className="text-sm text-gray-700">
                                    <span className="font-medium">Last run: </span>
                                    {new Date(schedule.last_run_at).toLocaleString()}
                                </p>
                                {schedule.last_run_status && (
                                    <p className="text-xs mt-1">
                                        <span className={`inline-flex items-center px-2 py-0.5 rounded text-xs font-medium ${
                                            schedule.last_run_status === 'success'
                                                ? 'bg-green-100 text-green-800'
                                                : schedule.last_run_status === 'running'
                                                ? 'bg-yellow-100 text-yellow-800'
                                                : 'bg-red-100 text-red-800'
                                        }`}>
                                            {schedule.last_run_status}
                                        </span>
                                    </p>
                                )}
                            </div>
                        </div>
                    </div>
                )}
            </div>

            {/* Action Buttons */}
            {!readOnly && (
                <div className="flex items-center justify-between mt-6 pt-4 border-t border-gray-200">
                    <div className="flex gap-2">
                        {schedule && (
                            <>
                                <button
                                    type="button"
                                    onClick={handleTriggerNow}
                                    disabled={saving}
                                    className="px-4 py-2 text-sm font-medium text-blue-700 bg-blue-50 rounded-lg hover:bg-blue-100 border border-blue-200 transition-colors disabled:opacity-50"
                                >
                                    {saving ? 'Processing...' : 'Sync Now'}
                                </button>
                                <button
                                    type="button"
                                    onClick={handleDelete}
                                    disabled={saving}
                                    className="px-4 py-2 text-sm font-medium text-red-700 bg-red-50 rounded-lg hover:bg-red-100 border border-red-200 transition-colors disabled:opacity-50"
                                >
                                    Delete Schedule
                                </button>
                            </>
                        )}
                    </div>
                    <button
                        type="button"
                        onClick={handleSave}
                        disabled={saving || !vectorDbName}
                        className="px-6 py-2 text-sm font-medium text-white bg-blue-600 rounded-lg hover:bg-blue-700 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                    >
                        {saving ? 'Saving...' : schedule ? 'Update Schedule' : 'Create Schedule'}
                    </button>
                </div>
            )}
        </div>
    );
};

export default ScheduleSelector;
