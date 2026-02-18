"""
Pipeline - Data transformation and orchestration layer.

This module contains components for transforming data between different
formats and orchestrating the complete conversion pipeline.

Components:
- pdf_to_json: Convert extracted PDF data to JSON format
- json_to_xlsx: Generate XLSX files from JSON data
- orchestrator: Coordinate the complete pipeline flow
"""

from .orchestrator import PipelineOrchestrator

__all__ = [
    "PipelineOrchestrator",
]
