"""Extension points for later stages.

Stage 2: OpenAI coaching (implemented in providers.coaching).
Stage 3: local interactive dashboard consuming analysis.json.
Stage 4: optional MCP adapter over AnalysisPipeline.
"""

from __future__ import annotations

from check_yourself.models import AnalysisReport, CoachingReport
from check_yourself.providers.coaching import CoachingProvider

__all__ = ["CoachingProvider", "AnalysisReport", "CoachingReport"]
