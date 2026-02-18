"""
Tests for ProcessingService.
"""

import pytest
from pathlib import Path
from app.services.processing_service import ProcessingService


class TestProcessingService:
    """Test suite for ProcessingService."""

    @pytest.fixture
    def service(self):
        """Create a ProcessingService instance for testing."""
        return ProcessingService()

    @pytest.mark.asyncio
    async def test_process_pdf_to_xlsx_not_implemented(self, service, sample_pdf_path):
        """Test that process_pdf_to_xlsx raises NotImplementedError."""
        with pytest.raises(NotImplementedError):
            await service.process_pdf_to_xlsx(sample_pdf_path)

    @pytest.mark.asyncio
    async def test_process_batch_not_implemented(self, service, temp_output_dir):
        """Test that process_batch raises NotImplementedError."""
        pdf_paths = [Path("file1.pdf"), Path("file2.pdf")]
        with pytest.raises(NotImplementedError):
            await service.process_batch(pdf_paths, temp_output_dir)

    # TODO: Add actual implementation tests
    # @pytest.mark.asyncio
    # async def test_process_pdf_to_xlsx_success(self, service, sample_pdf_path, temp_output_dir):
    #     """Test successful PDF to XLSX conversion."""
    #     output_path = await service.process_pdf_to_xlsx(
    #         sample_pdf_path,
    #         output_path=temp_output_dir / "output.xlsx"
    #     )
    #     assert output_path.exists()
    #     assert output_path.suffix == ".xlsx"
