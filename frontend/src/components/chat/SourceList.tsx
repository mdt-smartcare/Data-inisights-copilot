import type { Source } from '../../types';

interface SourceListProps {
  sources: Source[];
}

export default function SourceList({ sources }: SourceListProps) {
  if (!sources || sources.length === 0) return null;

  return (
    <div className="mt-2 pt-2 border-t border-gray-200">
      <p className="text-xs font-semibold mb-1.5 text-gray-700">Sources:</p>
      <div className="space-y-1.5">
        {sources.map((source, idx) => (
          <div 
            key={source.id} 
            className="text-xs text-gray-600 bg-gray-50 p-1.5 rounded"
          >
            <span className="font-medium text-blue-600">[{idx + 1}]</span>{' '}
            <span className="text-gray-700">
              {source.content.substring(0, 100)}
              {source.content.length > 100 && '...'}
            </span>
            {source.score && (
              <span className="text-[10px] text-gray-500 ml-1.5">
                (Score: {source.score.toFixed(2)})
              </span>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}
