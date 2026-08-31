"""Shared, dependency-free core for IntDog.

The desktop app and research pipelines use this package as their single
transactional boundary.  JSON/Markdown remain portable artifacts; SQLite is
the structured source of truth.
"""

from .models import normalized_name, stable_id, utc_now
from .repository import IntelligenceRepository
from .service import IntDogService
from .jobs import tracked_function, tracked_method

__all__ = ["IntDogService", "IntelligenceRepository", "normalized_name",
           "stable_id", "utc_now",
           "tracked_function", "tracked_method"]
