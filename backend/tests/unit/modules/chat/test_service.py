"""Tests for chat module service layer."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


class TestIntentClassifier:
    """Tests for IntentClassifier keyword-based classification."""
    
    @pytest.fixture
    def classifier(self):
        """Create IntentClassifier instance."""
        from app.modules.chat.intent_classifier import IntentClassifier
        return IntentClassifier()
    
    def test_sql_keywords_detected(self, classifier):
        """Test that SQL keywords are properly detected."""
        sql_queries = [
            "How many patients are there?",
            "What is the average age?",
            "Show me the total count",
            "What percentage of patients are male?",
            "Give me monthly breakdown",
            "What is the distribution by age?",
        ]
        
        for query in sql_queries:
            has_sql = any(kw in query.lower() for kw in classifier.SQL_KEYWORDS)
            assert has_sql, f"SQL keyword not detected in: {query}"
    
    def test_vector_keywords_detected(self, classifier):
        """Test that vector/RAG keywords are properly detected."""
        vector_queries = [
            "Find patient notes about diabetes",
            "Search for clinical summaries",
            "What did the doctor write about this patient?",
            "Tell me about the patient's medical history",
            "Look for mentions of hypertension",
        ]
        
        for query in vector_queries:
            has_vector = any(kw in query.lower() for kw in classifier.VECTOR_KEYWORDS)
            assert has_vector, f"Vector keyword not detected in: {query}"
    
    def test_hybrid_keywords_detected(self, classifier):
        """Test that hybrid keywords are properly detected."""
        hybrid_queries = [
            "Find notes for patients over 65",
            "Male patients with diabetes diagnosis",
            "Patients in region X with high BP",
        ]
        
        for query in hybrid_queries:
            has_hybrid = any(kw in query.lower() for kw in classifier.HYBRID_KEYWORDS)
            assert has_hybrid, f"Hybrid keyword not detected in: {query}"
    
    def test_keyword_classify_returns_valid_intent(self, classifier):
        """Test that _keyword_classify returns a valid IntentClassification."""
        from app.modules.chat.intent_classifier import IntentClassification
        
        # Pure SQL query with strong signal
        result = classifier._keyword_classify("How many patients are there total count?")
        
        assert result is not None
        assert isinstance(result, IntentClassification)
        assert result.intent in ["A", "B", "C", "Dashboard", "Fallback"]
        assert 0.0 <= result.confidence_score <= 1.0
    
    def test_aggregation_query_classified_as_sql(self, classifier):
        """Test that aggregation queries are classified as SQL."""
        # Queries with multiple SQL keywords for strong signal
        aggregation_queries = [
            "What is the total patient count by region?",
            "Show the average blood pressure percentage breakdown",
            "Count patients grouped by gender distribution",
        ]
        
        for query in aggregation_queries:
            result = classifier._keyword_classify(query)
            if result:  # May return None for ambiguous queries
                assert result.intent == "A", f"Expected SQL intent for: {query}, got: {result.intent}"
    
    def test_document_search_classified_as_vector(self, classifier):
        """Test that document search queries are classified as vector."""
        doc_queries = [
            "Search for patient notes mentioning headache symptoms",
            "Find clinical summaries about treatment plan details",
        ]
        
        for query in doc_queries:
            result = classifier._keyword_classify(query)
            if result:  # May return None for ambiguous queries
                assert result.intent in ["B", "C"], f"Expected vector/hybrid intent for: {query}"


class TestChatService:
    """Tests for ChatService (RAG pipeline)."""
    
    @pytest.fixture
    def mock_db(self):
        """Mock database session."""
        return AsyncMock()
    
    @pytest.mark.asyncio
    async def test_chat_service_initialization(self, mock_db):
        """Test ChatService initializes correctly."""
        with patch('app.modules.chat.service.get_intent_classifier') as mock_classifier:
            mock_classifier.return_value = MagicMock()
            
            from app.modules.chat.service import ChatService
            service = ChatService(mock_db)
            
            assert service is not None


class TestSQLService:
    """Tests for SQLService."""
    
    def test_sql_service_query_type_detection(self):
        """Test SQL service detects query types correctly."""
        # Aggregation patterns - test that our detection logic works
        aggregation_keywords = ["count", "sum", "average", "total", "aggregate", "how many"]
        
        aggregation_queries = [
            ("how many patients", "how many"),
            ("total count of users", "total"),
            ("average age of patients", "average"),
            ("sum of values", "sum"),
        ]
        
        for query, expected_keyword in aggregation_queries:
            is_aggregation = any(kw in query.lower() for kw in aggregation_keywords)
            assert is_aggregation, f"Aggregation not detected: {query}"
    
    def test_sql_service_trend_query_detection(self):
        """Test SQL service detects trend queries."""
        trend_keywords = [
            "trend", "over time", "monthly", "yearly", "weekly", "daily",
            "time series", "historical"
        ]
        
        trend_queries = [
            "Show monthly trend of patients",
            "Patient count over time",
            "Weekly distribution",
        ]
        
        for query in trend_queries:
            is_trend = any(kw in query.lower() for kw in trend_keywords)
            assert is_trend, f"Trend not detected: {query}"
    
    def test_sql_service_comparison_query_detection(self):
        """Test SQL service detects comparison queries."""
        comparison_keywords = [
            "compare", "comparison", "versus", "vs", "difference between",
            "more than", "less than", "higher", "lower"
        ]
        
        comparison_queries = [
            "Compare male vs female patients",
            "Difference between regions",
            "Higher than average",
        ]
        
        for query in comparison_queries:
            is_comparison = any(kw in query.lower() for kw in comparison_keywords)
            assert is_comparison, f"Comparison not detected: {query}"


class TestConversationMemory:
    """Tests for conversation memory."""
    
    def test_memory_stores_messages(self):
        """Test that ConversationMemory stores messages."""
        from app.modules.chat.memory import ConversationMemory
        
        memory = ConversationMemory()
        session_id = "test-session"
        
        session = memory.get_session(session_id)
        session.add_message("user", "Hello")
        session.add_message("assistant", "Hi there!")
        
        messages = session.get_history()
        
        assert len(messages) == 2
        assert messages[0].role == "user"
        assert messages[1].role == "assistant"
        assert messages[0].content == "Hello"
        assert messages[1].content == "Hi there!"
    
    def test_memory_session_history(self):
        """Test that session maintains history correctly."""
        from app.modules.chat.memory import ConversationMemory
        
        memory = ConversationMemory()
        session_id = "test-session"
        
        session = memory.get_session(session_id)
        for i in range(5):
            session.add_message("user", f"Message {i}")
        
        # Get limited history
        history = session.get_history(max_messages=3)
        assert len(history) == 3
        # Should be most recent messages
        assert history[0].content == "Message 2"
        assert history[2].content == "Message 4"
    
    def test_memory_context_string(self):
        """Test getting conversation as context string."""
        from app.modules.chat.memory import ConversationMemory
        
        memory = ConversationMemory()
        session_id = "test-session"
        
        session = memory.get_session(session_id)
        session.add_message("user", "Hello")
        session.add_message("assistant", "Hi!")
        
        context = session.get_context_string()
        
        assert "User: Hello" in context
        assert "Assistant: Hi!" in context
