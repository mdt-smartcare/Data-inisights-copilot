import { Link } from 'react-router-dom';

export default function HomePage() {
  return (
    <div className="min-h-screen flex flex-col items-center justify-center bg-gradient-to-br from-blue-50 to-indigo-100">
      <div className="max-w-4xl mx-auto px-6 py-12 text-center">
        <h1 className="text-5xl font-bold text-gray-900 mb-6">
          FHIR RAG Assistant
        </h1>
        <p className="text-xl text-gray-600 mb-8">
          AI-powered assistant for FHIR healthcare data queries using Retrieval-Augmented Generation
        </p>
        
        <div className="flex gap-4 justify-center">
          <Link
            to="/chat"
            className="bg-blue-600 hover:bg-blue-700 text-white font-semibold py-3 px-8 rounded-lg transition-colors shadow-lg"
          >
            Start Chatting
          </Link>
          <Link
            to="/about"
            className="bg-white hover:bg-gray-50 text-gray-800 font-semibold py-3 px-8 rounded-lg transition-colors shadow-lg border border-gray-300"
          >
            Learn More
          </Link>
        </div>

        <div className="mt-16 grid grid-cols-1 md:grid-cols-3 gap-8">
          <div className="bg-white p-6 rounded-lg shadow-md">
            <div className="text-3xl mb-4">🤖</div>
            <h3 className="text-lg font-semibold mb-2">AI-Powered</h3>
            <p className="text-gray-600">
              Advanced language models for accurate FHIR data retrieval
            </p>
          </div>
          
          <div className="bg-white p-6 rounded-lg shadow-md">
            <div className="text-3xl mb-4">⚡</div>
            <h3 className="text-lg font-semibold mb-2">Fast Responses</h3>
            <p className="text-gray-600">
              Optimized vector search for instant query results
            </p>
          </div>
          
          <div className="bg-white p-6 rounded-lg shadow-md">
            <div className="text-3xl mb-4">📚</div>
            <h3 className="text-lg font-semibold mb-2">Source Citations</h3>
            <p className="text-gray-600">
              Every answer includes relevant source references
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}
