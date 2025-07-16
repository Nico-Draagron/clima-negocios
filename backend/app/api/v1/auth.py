# Endpoints de autenticação
from fastapi import APIRouter, Depends, HTTPException, status, Body, BackgroundTasks
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from typing import Optional
from datetime import datetime, timedelta
import secrets

from app.core.config import settings
from app.core.security import (
    verify_password, 
    get_password_hash, 
    create_access_token,
    create_refresh_token,
    decode_token,
    oauth2_scheme,
    validate_email_address,
    generate_temp_password
)
from app.core.database import get_db
from app.models.user import User, UserRole
from app.schemas.auth import (
    Token,
    TokenRefresh,
    UserCreate,
    UserResponse,
    UserUpdate,
    PasswordChange,
    PasswordReset,
    EmailVerification
)
from app.utils.email import send_verification_email, send_password_reset_email

router = APIRouter()

@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def register(
    user_data: UserCreate,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db)
):
    """
    Registra um novo usuário no sistema.
    """
    # Valida email
    try:
        email_normalizado = validate_email_address(user_data.email)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    
    # Verifica se usuário já existe
    existing_user = db.query(User).filter(
        (User.email == email_normalizado) | 
        (User.username == user_data.username)
    ).first()
    
    if existing_user:
        if existing_user.email == email_normalizado:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Email já cadastrado"
            )
        else:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Username já em uso"
            )
    
    # Cria novo usuário
    db_user = User(
        email=email_normalizado,
        username=user_data.username,
        full_name=user_data.full_name,
        hashed_password=get_password_hash(user_data.password),
        company_name=user_data.company_name,
        company_sector=user_data.company_sector,
        company_size=user_data.company_size,
        role=UserRole.USER,
        email_verification_token=secrets.token_urlsafe(32)
    )
    
    db.add(db_user)
    db.commit()
    db.refresh(db_user)
    
    # Envia email de verificação
    background_tasks.add_task(
        send_verification_email,
        db_user.email,
        db_user.full_name,
        db_user.email_verification_token
    )
    
    return db_user

@router.post("/login", response_model=Token)
async def login(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db)
):
    """
    Autentica usuário e retorna tokens de acesso.
    """
    # Busca usuário por email ou username
    user = db.query(User).filter(
        (User.email == form_data.username) | 
        (User.username == form_data.username)
    ).first()
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Credenciais inválidas",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    # Verifica se conta está bloqueada
    if user.locked_until and user.locked_until > datetime.utcnow():
        raise HTTPException(
            status_code=status.HTTP_423_LOCKED,
            detail=f"Conta bloqueada até {user.locked_until.strftime('%d/%m/%Y %H:%M')}"
        )
    
    # Verifica senha
    if not verify_password(form_data.password, user.hashed_password):
        # Incrementa tentativas falhas
        user.failed_login_attempts += 1
        
        # Bloqueia após 5 tentativas
        if user.failed_login_attempts >= 5:
            user.locked_until = datetime.utcnow() + timedelta(minutes=30)
            db.commit()
            
            raise HTTPException(
                status_code=status.HTTP_423_LOCKED,
                detail="Conta bloqueada por múltiplas tentativas falhas"
            )
        
        db.commit()
        
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Credenciais inválidas",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    # Verifica se usuário está ativo
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Usuário inativo"
        )
    
    # Login bem-sucedido - reseta tentativas
    user.failed_login_attempts = 0
    user.last_login = datetime.utcnow()
    db.commit()
    
    # Cria tokens
    access_token = create_access_token(user.id)
    refresh_token = create_refresh_token(user.id)
    
    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer",
        "expires_in": settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60
    }

@router.post("/refresh", response_model=Token)
async def refresh_token(
    token_data: TokenRefresh,
    db: Session = Depends(get_db)
):
    """
    Gera novo access token usando refresh token.
    """
    try:
        payload = decode_token(token_data.refresh_token)
        
        if payload.get("type") != "refresh":
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token inválido"
            )
        
        user_id = payload.get("sub")
        user = db.query(User).filter(User.id == user_id).first()
        
        if not user or not user.is_active:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Usuário não encontrado ou inativo"
            )
        
        # Gera novos tokens
        access_token = create_access_token(user.id)
        new_refresh_token = create_refresh_token(user.id)
        
        return {
            "access_token": access_token,
            "refresh_token": new_refresh_token,
            "token_type": "bearer",
            "expires_in": settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60
        }
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token inválido ou expirado"
        )

@router.get("/me", response_model=UserResponse)
async def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db)
):
    """
    Retorna informações do usuário autenticado.
    """
    payload = decode_token(token)
    user_id = payload.get("sub")
    
    user = db.query(User).filter(User.id == user_id).first()
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Usuário não encontrado"
        )
    
    return user

@router.put("/me", response_model=UserResponse)
async def update_user(
    user_update: UserUpdate,
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db)
):
    """
    Atualiza informações do usuário.
    """
    payload = decode_token(token)
    user_id = payload.get("sub")
    
    user = db.query(User).filter(User.id == user_id).first()
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Usuário não encontrado"
        )
    
    # Atualiza campos permitidos
    update_data = user_update.dict(exclude_unset=True)
    
    for field, value in update_data.items():
        setattr(user, field, value)
    
    db.commit()
    db.refresh(user)
    
    return user

@router.post("/change-password")
async def change_password(
    password_data: PasswordChange,
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db)
):
    """
    Altera senha do usuário.
    """
    payload = decode_token(token)
    user_id = payload.get("sub")
    
    user = db.query(User).filter(User.id == user_id).first()
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Usuário não encontrado"
        )
    
    # Verifica senha atual
    if not verify_password(password_data.current_password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Senha atual incorreta"
        )
    
    # Atualiza senha
    user.hashed_password = get_password_hash(password_data.new_password)
    user.password_changed_at = datetime.utcnow()
    
    db.commit()
    
    return {"message": "Senha alterada com sucesso"}

@router.post("/forgot-password")
async def forgot_password(
    email: str = Body(..., embed=True),
    background_tasks: BackgroundTasks = BackgroundTasks(),
    db: Session = Depends(get_db)
):
    """
    Inicia processo de recuperação de senha.
    """
    user = db.query(User).filter(User.email == email).first()
    
    # Sempre retorna sucesso para não revelar se email existe
    if not user:
        return {"message": "Se o email existir, instruções serão enviadas"}
    
    # Gera token de reset
    user.password_reset_token = secrets.token_urlsafe(32)
    user.password_reset_expires = datetime.utcnow() + timedelta(hours=1)
    
    db.commit()
    
    # Envia email
    background_tasks.add_task(
        send_password_reset_email,
        user.email,
        user.full_name,
        user.password_reset_token
    )
    
    return {"message": "Se o email existir, instruções serão enviadas"}

@router.post("/reset-password")
async def reset_password(
    reset_data: PasswordReset,
    db: Session = Depends(get_db)
):
    """
    Reseta senha usando token.
    """
    user = db.query(User).filter(
        User.password_reset_token == reset_data.token
    ).first()
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Token inválido"
        )
    
    # Verifica se token expirou
    if user.password_reset_expires < datetime.utcnow():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Token expirado"
        )
    
    # Reseta senha
    user.hashed_password = get_password_hash(reset_data.new_password)
    user.password_changed_at = datetime.utcnow()
    user.password_reset_token = None
    user.password_reset_expires = None
    
    db.commit()
    
    return {"message": "Senha resetada com sucesso"}

@router.post("/verify-email")
async def verify_email(
    verification: EmailVerification,
    db: Session = Depends(get_db)
):
    """
    Verifica email do usuário.
    """
    user = db.query(User).filter(
        User.email_verification_token == verification.token
    ).first()
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Token inválido"
        )
    
    user.is_verified = True
    user.email_verification_token = None
    
    db.commit()
    
    return {"message": "Email verificado com sucesso"}

@router.post("/logout")
async def logout(token: str = Depends(oauth2_scheme)):
    """
    Logout do usuário (invalida token no cliente).
    """
    # Em uma implementação real, poderia adicionar token a uma blacklist
    return {"message": "Logout realizado com sucesso"}