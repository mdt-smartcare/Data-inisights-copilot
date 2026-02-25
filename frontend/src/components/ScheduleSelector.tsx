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
    const [scheduleType, setScheduleType] = useState<'hourly' | 'daily' | 'weekly' | 'interval' | 'custom'>('daily');
    const [hour, setHour] = useState(2);
    const [minute, setMinute] = useState(0);
    const [dayOfWeek, setDayOfWeek] = useState(0);
    const [cronExpression, setCronExpression] = useState('');
    // Countdown state
    const [countdown, setCountdown] = useState<number | null>(null);
    const [isEditing, setIsEditing] = useState(false);

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
            setIsEditing(false); // Close edit mode
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
                return `Every hour at minute :${minute.toString().padStart(2, '0')}`;
            case 'interval':
                return `Every ${minute} minute${minute > 1 ? 's' : ''}`;
            case 'daily':
                return `Daily at ${hour.toString().padStart(2, '0')}:${minute.toString().padStart(2, '0')}`;
            case 'weekly':
                const dayName = DAYS_OF_WEEK.find(d => d.value === dayOfWeek)?.label || 'Monday';
                return `Every ${dayName} at ${hour.toString().padStart(2, '0')}:${minute.toString().padStart(2, '0')}`;
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

            {!isEditing && schedule ? (
                /* Compact Summary View */
                <div className="space-y-4 animate-in fade-in duration-300">
                    <div className="flex items-center justify-between p-4 bg-gray-50 rounded-xl border border-gray-100">
                        <div>
                            <p className="text-xs font-bold text-gray-400 uppercase tracking-wider mb-1">Active interval</p>
                            <p className="text-sm font-bold text-gray-700">{getScheduleDescription()}</p>
                            <div className="flex items-center gap-2 mt-2">
                                <span className={`h-2 w-2 rounded-full ${schedule.enabled ? 'bg-green-500 animate-pulse' : 'bg-gray-300'}`}></span>
                                <span className="text-[10px] font-bold text-gray-500 uppercase">{schedule.enabled ? 'Automatic Sync Active' : 'Paused'}</span>
                            </div>
                        </div>
                        <button
                            onClick={() => setIsEditing(true)}
                            className="px-4 py-2 text-xs font-bold text-blue-600 bg-blue-50 border border-blue-100 rounded-lg hover:bg-blue-100 transition-colors"
                        >
                            Edit Schedule
                        </button>
                    </div>

                    {schedule.last_run_at && (
                        <div className="flex items-center justify-between text-[11px] text-gray-500 px-1">
                            <span>Last sync: <span className="font-bold">{new Date(schedule.last_run_at).toLocaleString()}</span></span>
                            {schedule.last_run_status && (
                                <span className={`px-2 py-0.5 rounded-full font-bold uppercase text-[9px] ${schedule.last_run_status === 'success' ? 'bg-green-100 text-green-700' : 'bg-red-100 text-red-700'
                                    }`}>
                                    {schedule.last_run_status}
                                </span>
                            )}
                        </div>
                    )}

                    <div className="flex gap-2 pt-2">
                        <button
                            onClick={handleTriggerNow}
                            disabled={saving}
                            className="flex-1 px-4 py-2.5 bg-blue-600 text-white rounded-xl text-xs font-bold hover:bg-blue-700 transition-colors shadow-sm disabled:opacity-50"
                        >
                            {saving ? 'Processing...' : 'Sync Now'}
                        </button>
                    </div>
                </div>
            ) : (
                /* Full Edit View */
                <div className="animate-in slide-in-from-top-2 duration-300 space-y-4">
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
                            <div className="grid grid-cols-2 sm:grid-cols-5 gap-2">
                                {(['hourly', 'interval', 'daily', 'weekly', 'custom'] as const).map((type) => (
                                    <button
                                        key={type}
                                        type="button"
                                        onClick={() => {
                                            setScheduleType(type);
                                            if (type === 'interval' && minute === 0) setMinute(15);
                                        }}
                                        disabled={readOnly}
                                        className={`px-2 py-2 text-[11px] font-bold rounded-lg border-2 transition-all uppercase tracking-tight ${scheduleType === type
                                            ? 'border-blue-500 bg-blue-50 text-blue-700'
                                            : 'border-gray-200 bg-white text-gray-700 hover:border-gray-300'
                                            }`}
                                    >
                                        {type === 'hourly' ? 'At Minute' : type.charAt(0).toUpperCase() + type.slice(1)}
                                    </button>
                                ))}
                            </div>
                        </div>

                        {/* Time Selection */}
                        {scheduleType !== 'custom' && (
                            <div className="space-y-3">
                                <div className="flex flex-col">
                                    <label className="block text-sm font-medium text-gray-700 mb-1">
                                        {scheduleType === 'hourly' ? 'Minute of Hour' : scheduleType === 'interval' ? 'Frequency (Minutes)' : 'Time'}
                                    </label>
                                    {scheduleType === 'hourly' || scheduleType === 'interval' ? (
                                        <div className="flex items-center gap-2">
                                            {scheduleType === 'hourly' && <span className="text-sm text-gray-400 font-mono">HH :</span>}
                                            <input
                                                type="number"
                                                min={scheduleType === 'interval' ? "1" : "0"}
                                                max="59"
                                                value={minute}
                                                onChange={(e) => setMinute(Math.max(scheduleType === 'interval' ? 1 : 0, Math.min(59, parseInt(e.target.value) || 0)))}
                                                disabled={readOnly}
                                                className="w-20 rounded-md border-gray-300 shadow-sm focus:border-blue-500 focus:ring-blue-500 sm:text-sm p-2 border font-mono"
                                            />
                                            <span className="text-xs text-gray-400">
                                                {scheduleType === 'hourly' ? 'minutes past the hour' : 'minutes between syncs'}
                                            </span>
                                        </div>
                                    ) : (
                                        <input
                                            type="time"
                                            value={`${hour.toString().padStart(2, '0')}:${minute.toString().padStart(2, '0')}`}
                                            onChange={(e) => {
                                                const [h, m] = e.target.value.split(':').map(Number);
                                                setHour(h);
                                                setMinute(m);
                                            }}
                                            disabled={readOnly}
                                            className="w-full sm:w-48 rounded-md border-gray-300 shadow-sm focus:border-blue-500 focus:ring-blue-500 sm:text-sm p-2 border font-mono"
                                        />
                                    )}
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
                            <div className="space-y-4">
                                <div>
                                    <label className="block text-sm font-medium text-gray-700 mb-1">
                                        <span className="flex items-center gap-1.5">
                                            <svg className="w-4 h-4 text-gray-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10 20l4-16m4 4l4 4-4 4M6 16l-4-4 4-4" />
                                            </svg>
                                            Cron Expression
                                        </span>
                                    </label>
                                    <input
                                        type="text"
                                        value={cronExpression}
                                        onChange={(e) => setCronExpression(e.target.value)}
                                        placeholder="0 2 * * *"
                                        disabled={readOnly}
                                        className="w-full rounded-md border-gray-300 shadow-sm focus:border-blue-500 focus:ring-blue-500 sm:text-sm p-2 border font-mono"
                                    />
                                    <p className="mt-1.5 text-[11px] text-gray-500 flex items-center gap-1">
                                        <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" /></svg>
                                        Format: minute hour day month day-of-week (e.g., <code className="bg-gray-100 px-1 rounded text-blue-600">*/30 * * * *</code> for every 30 mins)
                                    </p>
                                </div>

                                <div>
                                    <p className="text-[10px] font-bold text-gray-400 uppercase mb-2 tracking-wider">Quick Presets</p>
                                    <div className="flex flex-wrap gap-2">
                                        {[
                                            { label: 'Every 5m', val: '*/5 * * * *' },
                                            { label: 'Every 15m', val: '*/15 * * * *' },
                                            { label: 'Every 30m', val: '*/30 * * * *' },
                                            { label: 'Every 2h', val: '0 */2 * * *' },
                                            { label: 'Every 6h', val: '0 */6 * * *' },
                                            { label: 'Mon-Fri 9AM', val: '0 9 * * 1-5' }
                                        ].map((preset) => (
                                            <button
                                                key={preset.val}
                                                type="button"
                                                onClick={() => setCronExpression(preset.val)}
                                                disabled={readOnly}
                                                className="px-2 py-1 text-[11px] font-semibold bg-white border border-gray-200 rounded-md text-gray-600 hover:bg-blue-50 hover:border-blue-300 hover:text-blue-700 transition-all"
                                            >
                                                {preset.label}
                                            </button>
                                        ))}
                                    </div>
                                </div>
                            </div>
                        )}

                        {/* Schedule Description */}
                        <div className="p-3 bg-blue-50 rounded-lg border border-blue-200">
                            <p className="text-sm text-blue-800">
                                <span className="font-medium">Selected: </span>
                                {getScheduleDescription()}
                            </p>
                        </div>
                    </div>

                    {/* Action Buttons */}
                    {!readOnly && (
                        <div className="flex items-center justify-between mt-6 pt-4 border-t border-gray-200">
                            <div className="flex gap-2">
                                {schedule && (
                                    <>
                                        <button
                                            type="button"
                                            onClick={() => setIsEditing(false)}
                                            className="px-4 py-2 text-sm font-medium text-gray-600 bg-gray-100 rounded-lg hover:bg-gray-200 transition-colors"
                                        >
                                            Cancel
                                        </button>
                                        <button
                                            type="button"
                                            onClick={handleDelete}
                                            disabled={saving}
                                            className="px-4 py-2 text-sm font-medium text-red-700 bg-white border border-red-200 rounded-lg hover:bg-red-50 transition-colors disabled:opacity-50"
                                        >
                                            {saving ? '...' : 'Remove'}
                                        </button>
                                    </>
                                )}
                            </div>
                            <button
                                type="button"
                                onClick={handleSave}
                                disabled={saving || !vectorDbName}
                                className="px-6 py-2 text-sm font-medium text-white bg-blue-600 rounded-lg hover:bg-blue-700 transition-colors disabled:opacity-50 disabled:cursor-not-allowed shadow-md"
                            >
                                {saving ? 'Saving...' : schedule ? 'Update Schedule' : 'Create Schedule'}
                            </button>
                        </div>
                    )}
                </div>
            )}
        </div>
    );
};

export default ScheduleSelector;
