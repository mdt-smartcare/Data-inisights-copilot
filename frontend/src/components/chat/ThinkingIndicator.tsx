import { useState, useEffect } from 'react';

interface ThinkingIndicatorProps {
    /** Estimated total time in ms (for progress calculation) */
    estimatedTime?: number;
}

/** Progress stages with labels and target percentages */
const STAGES = [
    { label: 'Analyzing query...', targetPercent: 15 },
    { label: 'Searching database...', targetPercent: 35 },
    { label: 'Processing data...', targetPercent: 55 },
    { label: 'Generating response...', targetPercent: 80 },
    { label: 'Almost there...', targetPercent: 95 },
];

export default function ThinkingIndicator({
    estimatedTime = 12000
}: ThinkingIndicatorProps) {
    const [progress, setProgress] = useState(0);
    const [currentStage, setCurrentStage] = useState(0);
    const [elapsedTime, setElapsedTime] = useState(0);

    useEffect(() => {
        const startTime = Date.now();
        const interval = setInterval(() => {
            const elapsed = Date.now() - startTime;
            setElapsedTime(elapsed);

            const rawProgress = Math.min(elapsed / estimatedTime, 1);
            const easedProgress = Math.min(
                Math.log(1 + rawProgress * 9) / Math.log(10) * 95,
                95
            );

            setProgress(Math.round(easedProgress));

            const newStage = STAGES.findIndex(s => easedProgress < s.targetPercent);
            setCurrentStage(newStage === -1 ? STAGES.length - 1 : Math.max(0, newStage));
        }, 100);

        return () => clearInterval(interval);
    }, [estimatedTime]);

    const stage = STAGES[currentStage];

    return (
        <div className="flex justify-start">
            <div className="bg-white px-4 py-3 rounded-lg shadow-sm border border-gray-200 min-w-[260px] max-w-[320px]">
                {/* Header with AI avatar and stage label */}
                <div className="flex items-center gap-2.5 mb-3">
                    <div className="flex-shrink-0 w-6 h-6 rounded-full bg-gradient-to-br from-purple-500 to-pink-500 flex items-center justify-center animate-pulse">
                        <span className="text-white text-[8px] font-bold">AI</span>
                    </div>
                    <span className="text-sm text-gray-600">{stage.label}</span>
                </div>

                {/* Progress bar */}
                <div className="relative h-1.5 bg-gray-100 rounded-full overflow-hidden mb-2">
                    <div
                        className="absolute inset-y-0 left-0 bg-gradient-to-r from-blue-500 to-indigo-600 rounded-full transition-all duration-300 ease-out"
                        style={{ width: `${progress}%` }}
                    />
                    <div
                        className="absolute inset-0 bg-gradient-to-r from-transparent via-white/40 to-transparent animate-shimmer"
                        style={{ backgroundSize: '200% 100%' }}
                    />
                </div>

                {/* Progress info */}
                <div className="flex justify-between items-center text-[11px] text-gray-400">
                    <div className="flex items-center gap-1.5">
                        {/* Stage dots */}
                        {STAGES.slice(0, 4).map((_, i) => (
                            <div
                                key={i}
                                className={`w-1.5 h-1.5 rounded-full transition-colors duration-300 ${i < currentStage
                                        ? 'bg-green-400'
                                        : i === currentStage
                                            ? 'bg-blue-500'
                                            : 'bg-gray-200'
                                    }`}
                            />
                        ))}
                    </div>
                    <span className="font-mono">{progress}% · {Math.round(elapsedTime / 1000)}s</span>
                </div>
            </div>
        </div>
    );
}

