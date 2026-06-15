from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.db import get_db
from app.core.security import encrypt_secret
from app.models import Account, User
from app.schemas.account import AccountCreate, AccountOut, AccountSummary, ConnectionTest
from app.services import binance_client

router = APIRouter()


def _mask(key: str) -> str:
    if len(key) <= 8:
        return "****"
    return f"{key[:4]}…{key[-4:]}"


def _out(a: Account) -> AccountOut:
    return AccountOut(
        id=a.id, name=a.name, api_key_masked=_mask(a.api_key),
        testnet=a.testnet, created_at=a.created_at,
    )


def _owned(account_id: int, user: User, db: Session) -> Account:
    a = db.get(Account, account_id)
    if a is None or a.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Account not found")
    return a


@router.get("", response_model=List[AccountOut])
def list_accounts(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    rows = db.query(Account).filter(Account.user_id == user.id).order_by(Account.id).all()
    return [_out(a) for a in rows]


@router.post("", response_model=AccountOut)
def create_account(
    body: AccountCreate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    account = Account(
        user_id=user.id,
        name=body.name.strip() or "Account",
        api_key=body.api_key.strip(),
        api_secret_encrypted=encrypt_secret(body.api_secret.strip()),
        testnet=body.testnet,
    )
    db.add(account)
    db.commit()
    db.refresh(account)
    return _out(account)


@router.delete("/{account_id}")
def delete_account(
    account_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    account = _owned(account_id, user, db)
    if account.bots:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "Account has bots; delete them first",
        )
    db.delete(account)
    db.commit()
    binance_client.invalidate_account(account_id)
    return {"deleted": account_id}


@router.post("/{account_id}/test", response_model=ConnectionTest)
def test_account(
    account_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    account = _owned(account_id, user, db)
    svc = binance_client.get_service_for_account(account)
    return ConnectionTest(**svc.test_connection())


@router.get("/{account_id}/summary", response_model=AccountSummary)
def account_summary(
    account_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    account = _owned(account_id, user, db)
    svc = binance_client.get_service_for_account(account)
    try:
        return svc.get_account_summary()
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(exc))
