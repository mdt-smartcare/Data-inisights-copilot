/**
 * ModelCatalog Component
 * 
 * DEPRECATED: This component used old /api/v1/settings/embedding/* APIs that no longer exist.
 * Model management has been moved to the AI Registry page (/ai-registry).
 * 
 * This component now displays a migration notice directing users to the new AI Registry.
 */
import React from 'react';

interface ModelCatalogProps {
  onModelActivated?: (result: unknown) => void;
  readOnly?: boolean;
}

const ModelCatalog: React.FC<ModelCatalogProps> = () => {
  return (
    <div className="flex flex-col items-center justify-center p-8 text-center">
      <svg 
        className="w-16 h-16 text-blue-500 mb-4" 
        fill="none" 
        stroke="currentColor" 
        viewBox="0 0 24 24"
      >
        <path 
          strokeLinecap="round" 
          strokeLinejoin="round" 
          strokeWidth={1.5} 
          d="M13 10V3L4 14h7v7l9-11h-7z" 
        />
      </svg>
      <h3 className="text-lg font-semibold text-gray-900 mb-2">
        Model Catalog Migrated
      </h3>
      <p className="text-gray-600 mb-4 max-w-md">
        The embedding model catalog has been migrated to the new <strong>AI Registry</strong> page.
        You can now manage all AI models (LLM, Embedding, Reranker) from a unified interface.
      </p>
      <a
        href="/ai-registry"
        className="inline-flex items-center px-4 py-2 bg-blue-600 text-white font-medium rounded-lg hover:bg-blue-700 transition-colors"
      >
        <svg className="w-4 h-4 mr-2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 7l5 5m0 0l-5 5m5-5H6" />
        </svg>
        Go to AI Registry
      </a>
    </div>
  );
};

export default ModelCatalog;
