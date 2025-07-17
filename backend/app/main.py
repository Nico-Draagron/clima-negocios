from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import JSONResponse
from contextlib import asynccontextmanager
import logging
import time
from typing import Callable
import sentry_sdk
from sentry_sdk.integrations.asgi import SentryAsgiMiddleware

from app.core.config import settings
from app.core.database import engine, check_database_connection
from app.api.v1 import auth, clima, vendas, predicoes, analytics

# Configuração de logging
logging.basicConfig(
    level=logging.INFO if settings.ENVIRONMENT == "production" else logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Configuração do Sentry para monitoramento em produção
if settings.SENTRY_DSN and settings.ENVIRONMENT == "production":
    sentry_sdk.init(
        dsn=settings.SENTRY_DSN,
        environment=settings.ENVIRONMENT,
        traces_sample_rate=0.1,
    )

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Gerencia o ciclo de vida da aplicação.
    """
    # Startup
    logger.info("Iniciando aplicação Clima & Negócios...")
    
    # Verifica conexão com o banco
    if not check_database_connection():
        logger.error("Falha na conexão com o banco de dados")
        raise Exception("Database connection failed")
    
    logger.info("Aplicação iniciada com sucesso!")
    
    yield
    
    # Shutdown
    logger.info("Encerrando aplicação...")
    # Aqui você pode adicionar limpeza de recursos

# Criação da aplicação FastAPI
app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    openapi_url=f"{settings.API_V1_STR}/openapi.json",
    docs_url=f"{settings.API_V1_STR}/docs",
    redoc_url=f"{settings.API_V1_STR}/redoc",
    lifespan=lifespan
)

# Middleware de CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=[str(origin) for origin in settings.BACKEND_CORS_ORIGINS],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Middleware de compressão
app.add_middleware(GZipMiddleware, minimum_size=1000)

# Middleware de segurança - apenas hosts confiáveis
if settings.ENVIRONMENT == "production":
    app.add_middleware(
        TrustedHostMiddleware,
        allowed_hosts=["*.climanegocios.com", "climanegocios.com"]
    )

# Middleware customizado para logging de requisições
@app.middleware("http")
async def log_requests(request: Request, call_next: Callable):
    """
    Loga todas as requisições HTTP.
    """
    start_time = time.time()
    
    # Log da requisição
    logger.info(f"Requisição: {request.method} {request.url.path}")
    
    # Processa a requisição
    response = await call_next(request)
    
    # Calcula tempo de processamento
    process_time = time.time() - start_time
    
    # Adiciona header com tempo de processamento
    response.headers["X-Process-Time"] = str(process_time)
    
    # Log da resposta
    logger.info(
        f"Resposta: {request.method} {request.url.path} "
        f"- Status: {response.status_code} - Tempo: {process_time:.3f}s"
    )
    
    return response

# Middleware para tratamento global de erros
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """
    Tratamento global de exceções não capturadas.
    """
    logger.error(f"Erro não tratado: {exc}", exc_info=True)
    
    if settings.ENVIRONMENT == "production":
        # Em produção, não expor detalhes do erro
        return JSONResponse(
            status_code=500,
            content={
                "detail": "Erro interno do servidor",
                "error_id": str(time.time())  # ID para rastreamento
            }
        )
    else:
        # Em desenvolvimento, mostrar detalhes
        return JSONResponse(
            status_code=500,
            content={
                "detail": str(exc),
                "type": type(exc).__name__
            }
        )

# Rotas da API v1
app.include_router(auth.router, prefix=f"{settings.API_V1_STR}/auth", tags=["auth"])
app.include_router(clima.router, prefix=f"{settings.API_V1_STR}/clima", tags=["clima"])
app.include_router(vendas.router, prefix=f"{settings.API_V1_STR}/vendas", tags=["vendas"])
app.include_router(predicoes.router, prefix=f"{settings.API_V1_STR}/predicoes", tags=["predicoes"])
app.include_router(analytics.router, prefix=f"{settings.API_V1_STR}/analytics", tags=["analytics"])

# Health check endpoint
@app.get("/health", tags=["health"])
async def health_check():
    """
    Endpoint para verificação de saúde da aplicação.
    """
    db_status = check_database_connection()
    
    return {
        "status": "healthy" if db_status else "unhealthy",
        "version": settings.VERSION,
        "environment": settings.ENVIRONMENT,
        "database": "connected" if db_status else "disconnected",
        "timestamp": time.time()
    }

# Root endpoint
@app.get("/", tags=["root"])
async def root():
    """
    Endpoint raiz da API.
    """
    return {
        "message": "Bem-vindo à API Clima & Negócios",
        "version": settings.VERSION,
        "docs": f"{settings.API_V1_STR}/docs",
        "health": "/health"
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=settings.ENVIRONMENT == "development",
        log_level="info" if settings.ENVIRONMENT == "production" else "debug"
    )