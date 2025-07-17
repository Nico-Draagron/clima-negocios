from app.models.base import BaseModel, TimestampMixin
from app.models.user import User, UserRole
from app.models.clima import (
    EstacaoMeteorologica,
    DadoClimatico,
    PrevisaoTempo,
    EventoClimatico
)
from app.models.vendas import (
    Venda,
    MetaVenda,
    ProdutoVenda,
    CategoriaVenda,
    CanalVenda
)
from app.models.predicoes import (
    Predicao,
    ModeloML,
    HistoricoPredicao,
    ConfiguracaoModelo,
    TipoPredicao,
    StatusPredicao
)

__all__ = [
    # Base
    'BaseModel',
    'TimestampMixin',
    
    # User
    'User',
    'UserRole',
    
    # Clima
    'EstacaoMeteorologica',
    'DadoClimatico', 
    'PrevisaoTempo',
    'EventoClimatico',
    
    # Vendas
    'Venda',
    'MetaVenda',
    'ProdutoVenda',
    'CategoriaVenda',
    'CanalVenda',
    
    # Predições
    'Predicao',
    'ModeloML',
    'HistoricoPredicao',
    'ConfiguracaoModelo',
    'TipoPredicao',
    'StatusPredicao'
]