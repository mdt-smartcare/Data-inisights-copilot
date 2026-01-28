import { useState, useEffect } from 'react';

interface ThinkingIndicatorProps {
    /** Estimated total time in ms (for progress calculation) */
    estimatedTime?: number;
}

/** Progress stages with labels and target percentages */
const STAGES = [
    { label: 'Analyzing query...', targetPercent: 15, icon: '🔍' },
    { label: 'Searching database...', targetPercent: 35, icon: '🗃️' },
    { label: 'Processing data...', targetPercent: 55, icon: '⚙️' },
    { label: 'Generating response...', targetPercent: 80, icon: '✨' },
    { label: 'Almost there...', targetPercent: 95, icon: '🚀' },
];

export default function ThinkingIndicator({
    estimatedTime = 12000 // Default 12 seconds 
}: ThinkingIndicatorProps) {
    const [progress, setProgress] = useState(0);
    const [currentStage, setCurrentStage] = useState(0);
    const [elapsedTime, setElapsedTime] = useState(0);

    // Progress animation
    useEffect(() => {
        const startTime = Date.now();
        const interval = setInterval(() => {
            const elapsed = Date.now() - startTime;
            setElapsedTime(elapsed);

            // Calculate progress with easing (slows down as it approaches 95%)
            // Uses logarithmic easing to feel natural
            const rawProgress = Math.min(elapsed / estimatedTime, 1);
            const easedProgress = Math.min(
                Math.log(1 + rawProgress * 9) / Math.log(10) * 95, // Max 95%
                95
            );

            setProgress(Math.round(easedProgress));

            // Update current stage based on progress
            const newStage = STAGES.findIndex(s => easedProgress < s.targetPercent);
            setCurrentStage(newStage === -1 ? STAGES.length - 1 : Math.max(0, newStage));
        }, 100);

        return () => clearInterval(interval);
    }, [estimatedTime]);

    const stage = STAGES[currentStage];

    return (
        <div className="flex justify-start">
            <div className="bg-white px-4 py-3 rounded-lg shadow-sm border border-gray-200 min-w-[280px] max-w-[350px]">
                {/* Header with stage icon and label */}
                <div className="flex items-center gap-2 mb-2">
                    <span className="text-lg">{stage.icon}</span>
                    <span className="text-sm font-medium text-gray-700">{stage.label}</span>
                </div>

                {/* Progress bar */}
                <div className="relative h-2 bg-gray-100 rounded-full overflow-hidden mb-2">
                    <div
                        className="absolute inset-y-0 left-0 bg-gradient-to-r from-blue-500 to-indigo-600 rounded-full transition-all duration-300 ease-out"
                        style={{ width: `${progress}%` }}
                    />
                    {/* Shimmer effect */}
                    <div
                        className="absolute inset-0 bg-gradient-to-r from-transparent via-white/30 to-transparent animate-shimmer"
                        style={{ backgroundSize: '200% 100%' }}
                    />
                </div>

                {/* Progress percentage and time */}
                <div className="flex justify-between items-center text-xs text-gray-500">
                    <span className="font-mono">{progress}%</span>
                    <span>{Math.round(elapsedTime / 1000)}s</span>
                </div>

                {/* Stage indicators */}
                <div className="flex justify-between mt-2 pt-2 border-t border-gray-100">
                    {STAGES.slice(0, 4).map((s, i) => (
                        <div
                            key={i}
                            className={`flex flex-col items-center transition-all duration-300 ${i <= currentStage ? 'opacity-100' : 'opacity-30'
                                }`}
                        >
                            <div className={`w-2 h-2 rounded-full mb-1 ${i < currentStage
                                    ? 'bg-green-500'
                                    : i === currentStage
                                        ? 'bg-blue-500 animate-pulse'
                                        : 'bg-gray-300'
                                }`} />
                            <span className="text-[10px] text-gray-400 hidden sm:block">
                                {s.icon}
                            </span>
                        </div>
                    ))}
                </div>
            </div>
        </div>
    );
}
