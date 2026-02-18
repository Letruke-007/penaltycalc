"""
Tests for PipelineOrchestrator.
"""

import pytest
from pathlib import Path
from app.pipeline.orchestrator import PipelineOrchestrator


class TestPipelineOrchestrator:
    """Test suite for PipelineOrchestrator."""

    @pytest.fixture
    def orchestrator(self):
        """Create a PipelineOrchestrator instance for testing."""
        return PipelineOrchestrator()

    @pytest.mark.asyncio
    async def test_execute_not_implemented(self, orchestrator, sample_pdf_path):
        """Test that execute raises NotImplementedError."""
        with pytest.raises(NotImplementedError):
            await orchestrator.execute(sample_pdf_path)

    def test_validate_input_not_implemented(self, orchestrator, sample_pdf_path):
        """Test that validate_input raises NotImplementedError."""
        with pytest.raises(NotImplementedError):
            orchestrator.validate_input(sample_pdf_path)

    # TODO: Add actual implementation tests
