import redis
import json
import pickle
from typing import Optional, Any, Union
from datetime import timedelta
import hashlib
import logging
from functools import wraps
import asyncio

from app.core.config import settings

logger = logging.getLogger(__name__)

class CacheService:
    """
    Serviço de cache usando Redis para otimizar performance.
    """
    
    def __init__(self):
        self.redis_client = None
        self._connect()
    
    def _connect(self):
        """Estabelece conexão com Redis."""
        try:
            self.redis_client = redis.Redis(
                host=settings.REDIS_HOST,
                port=settings.REDIS_PORT,
                password=settings.REDIS_PASSWORD,
                db=settings.REDIS_DB,
                decode_responses=False,  # Para suportar pickle
                socket_connect_timeout=5,
                socket_timeout=5,
                retry_on_timeout=True,
                health_check_interval=30
            )
            # Testa conexão
            self.redis_client.ping()
            logger.info("Conexão com Redis estabelecida com sucesso")
        except Exception as e:
            logger.error(f"Erro ao conectar com Redis: {e}")
            self.redis_client = None
    
    def _generate_key(self, prefix: str, params: dict) -> str:
        """
        Gera chave única baseada em prefixo e parâmetros.
        """
        # Ordena os parâmetros para garantir consistência
        sorted_params = json.dumps(params, sort_keys=True)
        hash_params = hashlib.md5(sorted_params.encode()).hexdigest()
        return f"{prefix}:{hash_params}"
    
    def get(self, key: str, deserialize: bool = True) -> Optional[Any]:
        """
        Recupera valor do cache.
        
        Args:
            key: Chave do cache
            deserialize: Se deve deserializar o valor
        """
        if not self.redis_client:
            return None
        
        try:
            value = self.redis_client.get(key)
            if value is None:
                return None
            
            if deserialize:
                try:
                    # Tenta JSON primeiro (mais rápido)
                    return json.loads(value)
                except:
                    # Fallback para pickle
                    return pickle.loads(value)
            return value
        except Exception as e:
            logger.error(f"Erro ao recuperar do cache: {e}")
            return None
    
    def set(
        self, 
        key: str, 
        value: Any, 
        ttl: Optional[int] = None,
        serialize: bool = True
    ) -> bool:
        """
        Armazena valor no cache.
        
        Args:
            key: Chave do cache
            value: Valor a ser armazenado
            ttl: Tempo de vida em segundos
            serialize: Se deve serializar o valor
        """
        if not self.redis_client:
            return False
        
        try:
            if serialize:
                try:
                    # Tenta JSON primeiro
                    serialized_value = json.dumps(value)
                except:
                    # Fallback para pickle
                    serialized_value = pickle.dumps(value)
            else:
                serialized_value = value
            
            if ttl:
                self.redis_client.setex(key, ttl, serialized_value)
            else:
                self.redis_client.set(key, serialized_value)
            
            return True
        except Exception as e:
            logger.error(f"Erro ao armazenar no cache: {e}")
            return False
    
    def delete(self, key: str) -> bool:
        """Remove chave do cache."""
        if not self.redis_client:
            return False
        
        try:
            self.redis_client.delete(key)
            return True
        except Exception as e:
            logger.error(f"Erro ao deletar do cache: {e}")
            return False
    
    def delete_pattern(self, pattern: str) -> int:
        """
        Remove todas as chaves que correspondem ao padrão.
        
        Returns:
            Número de chaves deletadas
        """
        if not self.redis_client:
            return 0
        
        try:
            keys = self.redis_client.keys(pattern)
            if keys:
                return self.redis_client.delete(*keys)
            return 0
        except Exception as e:
            logger.error(f"Erro ao deletar padrão do cache: {e}")
            return 0
    
    def exists(self, key: str) -> bool:
        """Verifica se chave existe no cache."""
        if not self.redis_client:
            return False
        
        try:
            return bool(self.redis_client.exists(key))
        except Exception as e:
            logger.error(f"Erro ao verificar existência no cache: {e}")
            return False
    
    def increment(self, key: str, amount: int = 1) -> Optional[int]:
        """Incrementa valor numérico no cache."""
        if not self.redis_client:
            return None
        
        try:
            return self.redis_client.incr(key, amount)
        except Exception as e:
            logger.error(f"Erro ao incrementar no cache: {e}")
            return None
    
    def get_ttl(self, key: str) -> Optional[int]:
        """Retorna o TTL restante de uma chave em segundos."""
        if not self.redis_client:
            return None
        
        try:
            ttl = self.redis_client.ttl(key)
            return ttl if ttl >= 0 else None
        except Exception as e:
            logger.error(f"Erro ao obter TTL: {e}")
            return None
    
    def set_hash(self, name: str, key: str, value: Any, serialize: bool = True) -> bool:
        """Armazena valor em hash."""
        if not self.redis_client:
            return False
        
        try:
            if serialize:
                value = json.dumps(value)
            self.redis_client.hset(name, key, value)
            return True
        except Exception as e:
            logger.error(f"Erro ao armazenar em hash: {e}")
            return False
    
    def get_hash(self, name: str, key: str, deserialize: bool = True) -> Optional[Any]:
        """Recupera valor de hash."""
        if not self.redis_client:
            return None
        
        try:
            value = self.redis_client.hget(name, key)
            if value and deserialize:
                return json.loads(value)
            return value
        except Exception as e:
            logger.error(f"Erro ao recuperar de hash: {e}")
            return None
    
    def get_all_hash(self, name: str, deserialize: bool = True) -> dict:
        """Recupera todos os valores de um hash."""
        if not self.redis_client:
            return {}
        
        try:
            data = self.redis_client.hgetall(name)
            if deserialize:
                return {k.decode(): json.loads(v) for k, v in data.items()}
            return {k.decode(): v.decode() for k, v in data.items()}
        except Exception as e:
            logger.error(f"Erro ao recuperar hash completo: {e}")
            return {}

# Instância global do cache
cache_service = CacheService()

# Decorador para cache automático
def cache_result(
    prefix: str, 
    ttl: Optional[int] = None,
    key_params: Optional[list] = None
):
    """
    Decorador para cachear resultados de funções.
    
    Args:
        prefix: Prefixo da chave do cache
        ttl: Tempo de vida em segundos (padrão: settings.CACHE_TTL)
        key_params: Lista de parâmetros a incluir na chave
    """
    def decorator(func):
        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            # Gera chave do cache
            cache_params = {}
            if key_params:
                # Usa apenas os parâmetros especificados
                cache_params = {k: kwargs.get(k) for k in key_params if k in kwargs}
            else:
                # Usa todos os kwargs
                cache_params = kwargs
            
            cache_key = cache_service._generate_key(prefix, cache_params)
            
            # Verifica cache
            cached_value = cache_service.get(cache_key)
            if cached_value is not None:
                logger.debug(f"Cache hit para {cache_key}")
                return cached_value
            
            # Executa função
            result = await func(*args, **kwargs)
            
            # Armazena no cache
            cache_ttl = ttl or settings.CACHE_TTL
            cache_service.set(cache_key, result, cache_ttl)
            logger.debug(f"Resultado cacheado em {cache_key} por {cache_ttl}s")
            
            return result
        
        @wraps(func)
        def sync_wrapper(*args, **kwargs):
            # Versão síncrona do wrapper
            cache_params = {}
            if key_params:
                cache_params = {k: kwargs.get(k) for k in key_params if k in kwargs}
            else:
                cache_params = kwargs
            
            cache_key = cache_service._generate_key(prefix, cache_params)
            
            cached_value = cache_service.get(cache_key)
            if cached_value is not None:
                logger.debug(f"Cache hit para {cache_key}")
                return cached_value
            
            result = func(*args, **kwargs)
            
            cache_ttl = ttl or settings.CACHE_TTL
            cache_service.set(cache_key, result, cache_ttl)
            logger.debug(f"Resultado cacheado em {cache_key} por {cache_ttl}s")
            
            return result
        
        # Retorna o wrapper apropriado
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        else:
            return sync_wrapper
    
    return decorator

# Funções auxiliares para cache de tipos específicos
class CacheKeys:
    """Namespaces para chaves de cache."""
    CLIMA_ATUAL = "clima:atual"
    CLIMA_PREVISAO = "clima:previsao"
    VENDAS_DIA = "vendas:dia"
    VENDAS_AGREGADO = "vendas:agregado"
    PREDICAO_RESULTADO = "predicao:resultado"
    USUARIO_PERFIL = "usuario:perfil"
    ANALYTICS_DASHBOARD = "analytics:dashboard"
    ML_MODEL = "ml:model"
    ESTACAO_INFO = "estacao:info"
    CORRELACAO_CLIMA = "correlacao:clima"