"""
Tests for feedback endpoint and Langfuse integration.

Tests cover:
1. Feedback submission API endpoint
2. Langfuse score pushing
3. Error handling when Langfuse is unavailable
"""
import pytest
from unittest.mock import MagicMock, patch, AsyncMock
import pandas as pd

from backend.models.schemas import FeedbackRequest


class TestFeedbackEndpoint:
    """Test feedback API endpoint."""

    def test_submit_feedback_success(self, client, auth_headers, sample_feedback_request):
        """Test successful feedback submission."""
        with patch('backend.api.routes.feedback._push_feedback_to_langfuse', new_callable=AsyncMock):
            response = client.post(
                "/api/v1/feedback",
                json=sample_feedback_request,
                headers=auth_headers
            )
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert "feedback_id" in data
        assert "rating: 1" in data["message"]

    def test_submit_feedback_thumbs_down(self, client, auth_headers):
        """Test negative feedback submission (thumbs down)."""
        feedback_request = {
            "trace_id": "test-trace-negative-123",
            "query": "Show me patient data",
            "rating": -1,
            "comment": "Response was incorrect"
        }
        
        with patch('backend.api.routes.feedback._push_feedback_to_langfuse', new_callable=AsyncMock):
            response = client.post(
                "/api/v1/feedback",
                json=feedback_request,
                headers=auth_headers
            )
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert "rating: -1" in data["message"]

    def test_submit_feedback_requires_auth(self, client, sample_feedback_request):
        """Test that feedback endpoint requires authentication."""
        response = client.post(
            "/api/v1/feedback",
            json=sample_feedback_request
        )
        
        assert response.status_code == 401

    def test_submit_feedback_invalid_rating(self, client, auth_headers):
        """Test that invalid rating values are rejected."""
        invalid_request = {
            "trace_id": "test-trace-123",
            "query": "Test query",
            "rating": 5  # Invalid: should be -1, 0, or 1
        }
        
        response = client.post(
            "/api/v1/feedback",
            json=invalid_request,
            headers=auth_headers
        )
        
        assert response.status_code == 422  # Validation error

    def test_submit_feedback_missing_trace_id(self, client, auth_headers):
        """Test that trace_id is required."""
        invalid_request = {
            "query": "Test query",
            "rating": 1
        }
        
        response = client.post(
            "/api/v1/feedback",
            json=invalid_request,
            headers=auth_headers
        )
        
        assert response.status_code == 422


class TestLangfuseIntegration:
    """Test Langfuse score pushing functionality."""

    @pytest.mark.asyncio
    async def test_push_feedback_to_langfuse_positive(self):
        """Test pushing positive feedback score to Langfuse."""
        from backend.api.routes.feedback import _push_feedback_to_langfuse
        
        mock_langfuse = MagicMock()
        mock_tracing_manager = MagicMock()
        mock_tracing_manager.langfuse_enabled = True
        mock_tracing_manager.langfuse = mock_langfuse
        
        request = FeedbackRequest(
            trace_id="test-trace-123",
            query="How many patients?",
            rating=1,
            comment="Great response!"
        )
        
        with patch('backend.api.routes.feedback.get_tracing_manager', return_value=mock_tracing_manager):
            await _push_feedback_to_langfuse(request, "test_user", "feedback-id-123")
        
        # Verify score was pushed to Langfuse
        assert mock_langfuse.score.call_count == 2  # user_feedback + detailed_user_feedback
        
        # Check first score call (user_feedback)
        first_call = mock_langfuse.score.call_args_list[0]
        assert first_call.kwargs["name"] == "user_feedback"
        assert first_call.kwargs["value"] == 1.0  # Positive
        assert first_call.kwargs["trace_id"] == "test-trace-123"

    @pytest.mark.asyncio
    async def test_push_feedback_to_langfuse_negative(self):
        """Test pushing negative feedback score to Langfuse."""
        from backend.api.routes.feedback import _push_feedback_to_langfuse
        
        mock_langfuse = MagicMock()
        mock_tracing_manager = MagicMock()
        mock_tracing_manager.langfuse_enabled = True
        mock_tracing_manager.langfuse = mock_langfuse
        
        request = FeedbackRequest(
            trace_id="test-trace-456",
            query="Show patient records",
            rating=-1,
            comment="Wrong data returned"
        )
        
        with patch('backend.api.routes.feedback.get_tracing_manager', return_value=mock_tracing_manager):
            await _push_feedback_to_langfuse(request, "test_user", "feedback-id-456")
        
        # Check score value is 0 for negative feedback
        first_call = mock_langfuse.score.call_args_list[0]
        assert first_call.kwargs["value"] == 0.0  # Negative

    @pytest.mark.asyncio
    async def test_push_feedback_langfuse_disabled(self):
        """Test that feedback push is skipped when Langfuse is disabled."""
        from backend.api.routes.feedback import _push_feedback_to_langfuse
        
        mock_tracing_manager = MagicMock()
        mock_tracing_manager.langfuse_enabled = False
        
        request = FeedbackRequest(
            trace_id="test-trace-789",
            query="Test query",
            rating=1
        )
        
        with patch('backend.api.routes.feedback.get_tracing_manager', return_value=mock_tracing_manager):
            # Should not raise any errors
            await _push_feedback_to_langfuse(request, "test_user", "feedback-id-789")

    @pytest.mark.asyncio
    async def test_push_feedback_langfuse_error_handled(self):
        """Test that Langfuse errors don't break feedback submission."""
        from backend.api.routes.feedback import _push_feedback_to_langfuse
        
        mock_langfuse = MagicMock()
        mock_langfuse.score.side_effect = Exception("Langfuse connection error")
        
        mock_tracing_manager = MagicMock()
        mock_tracing_manager.langfuse_enabled = True
        mock_tracing_manager.langfuse = mock_langfuse
        
        request = FeedbackRequest(
            trace_id="test-trace-error",
            query="Test query",
            rating=1
        )
        
        with patch('backend.api.routes.feedback.get_tracing_manager', return_value=mock_tracing_manager):
            # Should not raise - errors are caught and logged
            await _push_feedback_to_langfuse(request, "test_user", "feedback-id-error")

    @pytest.mark.asyncio
    async def test_push_feedback_includes_metadata(self):
        """Test that detailed feedback includes all metadata."""
        from backend.api.routes.feedback import _push_feedback_to_langfuse
        
        mock_langfuse = MagicMock()
        mock_tracing_manager = MagicMock()
        mock_tracing_manager.langfuse_enabled = True
        mock_tracing_manager.langfuse = mock_langfuse
        
        request = FeedbackRequest(
            trace_id="test-trace-meta",
            query="Original question",
            selected_suggestion="Follow-up question",
            rating=1,
            comment="User comment here"
        )
        
        with patch('backend.api.routes.feedback.get_tracing_manager', return_value=mock_tracing_manager):
            await _push_feedback_to_langfuse(request, "admin", "feedback-meta-123")
        
        # Check detailed score call (second call)
        detailed_call = mock_langfuse.score.call_args_list[1]
        metadata = detailed_call.kwargs.get("metadata", {})
        
        assert metadata["username"] == "admin"
        assert metadata["original_query"] == "Original question"
        assert metadata["selected_suggestion"] == "Follow-up question"
        assert metadata["user_comment"] == "User comment here"
        assert metadata["raw_rating"] == 1
