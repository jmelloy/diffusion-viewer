from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import Session, select

import models
import schemas
from database import get_db
from utils.security import (
    create_access_token,
    get_current_user,
    hash_password,
    verify_password,
)


router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post(
    "/register",
    response_model=schemas.TokenResponse,
    status_code=status.HTTP_201_CREATED,
)
def register(payload: schemas.UserCreate, db: Session = Depends(get_db)):
    existing = db.exec(
        select(models.User).where(models.User.username == payload.username)
    ).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Username already taken",
        )
    if payload.email:
        email_taken = db.exec(
            select(models.User).where(models.User.email == payload.email)
        ).first()
        if email_taken:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Email already registered",
            )

    user = models.User(
        username=payload.username,
        email=payload.email,
        hashed_password=hash_password(payload.password),
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    token = create_access_token(subject=user.username)
    return schemas.TokenResponse(access_token=token, user=schemas.UserPublic.model_validate(user))


@router.post("/login", response_model=schemas.TokenResponse)
def login(payload: schemas.UserLogin, db: Session = Depends(get_db)):
    user = db.exec(
        select(models.User).where(models.User.username == payload.username)
    ).first()
    if not user or not verify_password(payload.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
        )
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account is disabled",
        )
    token = create_access_token(subject=user.username)
    return schemas.TokenResponse(access_token=token, user=schemas.UserPublic.model_validate(user))


@router.get("/me", response_model=schemas.UserPublic)
def me(current_user: models.User = Depends(get_current_user)):
    return current_user
