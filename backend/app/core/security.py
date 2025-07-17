from datetime import datetime, timedelta
from typing import Optional, Union, Dict, Any
from jose import JWTError, jwt
from passlib.context import CryptContext
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session
import secrets
import string
from email_validator import validate_email, EmailNotValidError

from .config import settings
from .database import get_db

# Configuração do contexto de criptografia
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# OAuth2 scheme
oauth2_scheme = OAuth2PasswordBearer(
    tokenUrl=f"{settings.API_V1_STR}/auth/login",
    auto_error=True
)

# Funções de hash de senha
def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verifica se a senha corresponde ao hash."""
    return pwd_context.verify(plain_password, hashed_password)

def get_password_hash(password: str) -> str:
    """Gera hash da senha."""
    return pwd_context.hash(password)

# Funções de token JWT
def create_token(
    subject: Union[str, Dict[str, Any]], 
    token_type: str,
    expires_delta: Optional[timedelta] = None
) -> str:
    """
    Cria um token JWT.
    
    Args:
        subject: Dados a serem codificados no token
        token_type: Tipo do token (access ou refresh)
        expires_delta: Tempo de expiração
    """
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        if token_type == "access":
            expire = datetime.utcnow() + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
        else:  # refresh token
            expire = datetime.utcnow() + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
    
    to_encode = {
        "exp": expire,
        "sub": str(subject),
        "type": token_type,
        "iat": datetime.utcnow()
    }
    
    encoded_jwt = jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)
    return encoded_jwt

def create_access_token(subject: Union[str, Dict[str, Any]]) -> str:
    """Cria token de acesso."""
    return create_token(subject, "access")

def create_refresh_token(subject: Union[str, Dict[str, Any]]) -> str:
    """Cria token de refresh."""
    return create_token(subject, "refresh")

def decode_token(token: str) -> Dict[str, Any]:
    """
    Decodifica e valida um token JWT.
    
    Returns:
        Payload do token
        
    Raises:
        HTTPException: Se o token for inválido
    """
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        return payload
    except JWTError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token inválido",
            headers={"WWW-Authenticate": "Bearer"},
        )

# Validação de email
def validate_email_address(email: str) -> str:
    """
    Valida e normaliza endereço de email.
    
    Returns:
        Email normalizado
        
    Raises:
        ValueError: Se o email for inválido
    """
    try:
        validation = validate_email(email, check_deliverability=False)
        return validation.email
    except EmailNotValidError as e:
        raise ValueError(f"Email inválido: {str(e)}")

# Gerador de senhas temporárias
def generate_temp_password(length: int = 12) -> str:
    """
    Gera uma senha temporária segura.
    """
    alphabet = string.ascii_letters + string.digits + "!@#$%^&*"
    password = ''.join(secrets.choice(alphabet) for _ in range(length))
    return password

# Rate limiting simples (pode ser substituído por uma solução mais robusta)
class RateLimiter:
    def __init__(self, max_requests: int = 100, window_seconds: int = 60):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self.requests = {}
    
    def is_allowed(self, key: str) -> bool:
        """
        Verifica se a requisição é permitida baseado em rate limiting.
        """
        now = datetime.utcnow()
        
        # Limpa requisições antigas
        self.requests = {
            k: v for k, v in self.requests.items() 
            if (now - v[-1]).total_seconds() < self.window_seconds
        }
        
        # Verifica o limite
        if key in self.requests:
            recent_requests = [
                req for req in self.requests[key] 
                if (now - req).total_seconds() < self.window_seconds
            ]
            if len(recent_requests) >= self.max_requests:
                return False
            self.requests[key] = recent_requests + [now]
        else:
            self.requests[key] = [now]
        
        return True

# Instância global do rate limiter
rate_limiter = RateLimiter()

# Dependency para verificar rate limiting
def check_rate_limit(token: str = Depends(oauth2_scheme)):
    """
    Verifica rate limiting para o usuário.
    """
    payload = decode_token(token)
    user_id = payload.get("sub")
    
    if not rate_limiter.is_allowed(f"user:{user_id}"):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Muitas requisições. Tente novamente mais tarde."
        )
    
    return user_id

# Dependency para obter usuário atual
async def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db)
):
    """
    Obtém usuário atual baseado no token JWT.
    """
    from app.models.user import User  # Import aqui para evitar circular import
    
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Não foi possível validar as credenciais",
        headers={"WWW-Authenticate": "Bearer"},
    )
    
    try:
        payload = decode_token(token)
        user_id: str = payload.get("sub")
        if user_id is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception
    
    user = db.query(User).filter(User.id == int(user_id)).first()
    if user is None:
        raise credentials_exception
    
    return user

# Dependency para verificar se usuário é admin
async def require_admin(current_user = Depends(get_current_user)):
    """
    Verifica se o usuário atual é admin.
    """
    if not current_user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Acesso negado. Privilégios de administrador necessários."
        )
    return current_user

# Dependency para verificar se usuário está ativo
async def require_active_user(current_user = Depends(get_current_user)):
    """
    Verifica se o usuário está ativo.
    """
    if not current_user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Usuário inativo"
        )
    return current_user

# Função para verificar API Key
def verify_api_key(api_key: str, db: Session) -> Optional[Any]:
    """
    Verifica se API key é válida.
    """
    from app.models.user import User  # Import aqui para evitar circular import
    
    if not api_key or not api_key.startswith("cn_"):
        return None
    
    user = db.query(User).filter(User.api_key == api_key).first()
    if not user or not user.is_active:
        return None
    
    return user