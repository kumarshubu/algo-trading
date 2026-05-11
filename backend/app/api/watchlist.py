"""Watchlist API endpoints."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from app.db.database import get_db
from app.models.watchlist import Watchlist
from app.schemas.watchlist import WatchlistItemCreate, WatchlistItemRead
from app.schemas.common import SuccessResponse

router = APIRouter(prefix="/watchlist", tags=["watchlist"])


@router.get("", response_model=SuccessResponse[list[WatchlistItemRead]])
def get_watchlist(db: Session = Depends(get_db)):
    items = db.query(Watchlist).order_by(Watchlist.created_at.asc()).all()
    return SuccessResponse(data=[WatchlistItemRead.model_validate(i) for i in items])


@router.post("", response_model=SuccessResponse[WatchlistItemRead], status_code=201)
def add_to_watchlist(item: WatchlistItemCreate, db: Session = Depends(get_db)):
    db_item = Watchlist(symbol=item.symbol)
    try:
        db.add(db_item)
        db.commit()
        db.refresh(db_item)
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail=f"{item.symbol} is already in watchlist")
    return SuccessResponse(data=WatchlistItemRead.model_validate(db_item))


@router.delete("/{symbol}")
def remove_from_watchlist(symbol: str, db: Session = Depends(get_db)):
    symbol = symbol.upper().strip()
    item = db.query(Watchlist).filter(Watchlist.symbol == symbol).first()
    if not item:
        raise HTTPException(status_code=404, detail=f"{symbol} not found in watchlist")
    db.delete(item)
    db.commit()
    return {"success": True, "data": {"message": f"{symbol} removed from watchlist"}}
