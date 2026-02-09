export default function AboutPage() {
  return (
    <div className="min-h-screen bg-gray-50 py-12 px-6">
      <div className="max-w-4xl mx-auto">
        <h1 className="text-4xl font-bold text-gray-900 mb-8">About FHIR RAG</h1>
        
        <div className="bg-white rounded-lg shadow-md p-8 space-y-6">
          <section>
            <h2 className="text-2xl font-semibold text-gray-900 mb-3">What is FHIR RAG?</h2>
            <p className="text-gray-700 leading-relaxed">
              FHIR RAG (Fast Healthcare Interoperability Resources - Retrieval-Augmented Generation) 
              is an AI-powered assistant designed to help healthcare professionals, developers, and 
              researchers quickly find and understand FHIR healthcare data standards.
            </p>
          </section>

          <section>
            <h2 className="text-2xl font-semibold text-gray-900 mb-3">How It Works</h2>
            <ol className="list-decimal list-inside space-y-2 text-gray-700">
              <li>Ask questions in natural language about FHIR resources and standards</li>
              <li>The system searches through indexed FHIR documentation using vector embeddings</li>
              <li>An AI model generates accurate answers with source citations</li>
              <li>Review the sources to verify and learn more</li>
            </ol>
          </section>

          <section>
            <h2 className="text-2xl font-semibold text-gray-900 mb-3">Technology Stack</h2>
            <ul className="list-disc list-inside space-y-2 text-gray-700">
              <li><strong>Frontend:</strong> React, TypeScript, Tailwind CSS</li>
              <li><strong>Backend:</strong> Python, FastAPI</li>
              <li><strong>Vector Store:</strong> Embeddings for semantic search</li>
              <li><strong>AI Model:</strong> Large Language Model for response generation</li>
            </ul>
          </section>

          <section>
            <h2 className="text-2xl font-semibold text-gray-900 mb-3">Use Cases</h2>
            <ul className="list-disc list-inside space-y-2 text-gray-700">
              <li>Understanding FHIR resource structures</li>
              <li>Finding specific FHIR implementation guidelines</li>
              <li>Learning about healthcare interoperability standards</li>
              <li>Quick reference for FHIR development</li>
            </ul>
          </section>
        </div>
      </div>
    </div>
  );
}
