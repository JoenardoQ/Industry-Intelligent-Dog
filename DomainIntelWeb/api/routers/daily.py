from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Annotated, Callable, Literal

from fastapi import APIRouter, HTTPException, Query

from ..schemas import CountState, DailyState, DeleteDailyRequest


def build_daily_router(*, data_root: Path, dataio, resolve_folder: Callable[[str], str],
                       present_item: Callable[[dict], dict]) -> APIRouter:
    router = APIRouter(prefix="/api/industries/{folder}", tags=["daily"])

    @router.get("/daily", response_model=DailyState)
    def daily(folder: str, date: str | None = None, category: str | None = None,
              sort: Literal["title", "category", "source"] = "title",
              query: Annotated[str, Query(max_length=200)] = "",
              cursor: Annotated[str, Query(max_length=500)] = "",
              limit: Annotated[int, Query(ge=1, le=100)] = 50) -> dict:
        folder = resolve_folder(folder)
        try:
            page = dataio.page_daily(
                data_root, folder, date, category, query, sort, cursor, limit)
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
        rows = [present_item(item) for item in page["items"]]
        sort_key = {
            "title": lambda item: str(item.get("title") or "").casefold(),
            "category": lambda item: (
                str(item.get("category") or "").casefold(),
                str(item.get("title") or "").casefold()),
            "source": lambda item: (
                str(item.get("display_source") or "N/A").casefold(),
                str(item.get("title") or "").casefold()),
        }[sort]
        rows.sort(key=sort_key)
        return {
            "items": rows, "total": page["total"],
            "next_cursor": page["next_cursor"], "selection_scope": "current_page",
            "dates": dataio.list_daily_dates(data_root, folder),
            "counts": dict(Counter(str(item.get("category") or "unknown") for item in rows)),
            "origins": dict(Counter(str(item.get("origin") or "unknown") for item in rows)),
        }

    @router.delete("/daily", response_model=CountState)
    def delete_daily(folder: str, request: DeleteDailyRequest) -> dict:
        folder = resolve_folder(folder)
        identities = [(item.date, item.category, item.key) for item in request.items]
        return {"deleted": dataio.delete_daily_items(data_root, folder, identities)}

    return router
