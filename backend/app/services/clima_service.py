# Serviços de clima
import httpx
import asyncio
from typing import Dict, List, Optional, Tuple
from datetime import datetime, timedelta
import logging
from sqlalchemy.orm import Session
import pandas as pd
import numpy as np

from app.core.config import settings
from app.models.clima import DadoClimatico, EstacaoMeteorologica, PrevisaoTempo, EventoClimatico
from app.models.vendas import Venda
from app.models.user import User
from app.services.cache_service import cache_service, cache_result, CacheKeys
from app.core.database import get_db_context

logger = logging.getLogger(__name__)

class ClimaService:
    """
    Serviço para gerenciar dados climáticos.
    """
    
    def __init__(self):
        self.inmet_base_url = settings.INMET_BASE_URL
        self.nomads_base_url = settings.NOMADS_BASE_URL
        self.http_client = None
    
    async def __aenter__(self):
        self.http_client = httpx.AsyncClient(timeout=30.0)
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.http_client:
            await self.http_client.aclose()
    
    @cache_result(CacheKeys.CLIMA_ATUAL, ttl=300, key_params=['estacao_codigo'])
    async def obter_clima_atual(self, estacao_codigo: str) -> Optional[Dict]:
        """
        Obtém dados climáticos atuais de uma estação.
        
        Args:
            estacao_codigo: Código INMET da estação
            
        Returns:
            Dados climáticos atuais
        """
        try:
            # Busca dados da API do INMET
            url = f"{self.inmet_base_url}/estacao/dados/{estacao_codigo}"
            response = await self.http_client.get(url)
            
            if response.status_code != 200:
                logger.error(f"Erro ao buscar dados INMET: {response.status_code}")
                return None
            
            dados = response.json()
            
            if not dados:
                return None
            
            # Processa e padroniza dados
            clima_atual = self._processar_dados_inmet(dados[-1] if dados else {})
            
            # Salva no banco
            await self._salvar_dado_climatico(estacao_codigo, clima_atual)
            
            return clima_atual
            
        except Exception as e:
            logger.error(f"Erro ao obter clima atual: {e}")
            return None
    
    def _processar_dados_inmet(self, dados_raw: Dict) -> Dict:
        """
        Processa dados brutos do INMET.
        """
        return {
            'data_hora': datetime.fromisoformat(dados_raw.get('DT_MEDICAO', '')),
            'temperatura': float(dados_raw.get('TEM_INS', 0) or 0),
            'temperatura_min': float(dados_raw.get('TEM_MIN', 0) or 0),
            'temperatura_max': float(dados_raw.get('TEM_MAX', 0) or 0),
            'umidade': float(dados_raw.get('UMD_INS', 0) or 0),
            'pressao': float(dados_raw.get('PRE_INS', 0) or 0),
            'vento_velocidade': float(dados_raw.get('VEN_VEL', 0) or 0),
            'vento_direcao': float(dados_raw.get('VEN_DIR', 0) or 0),
            'precipitacao_1h': float(dados_raw.get('CHUVA', 0) or 0),
            'radiacao_solar': float(dados_raw.get('RAD_GLO', 0) or 0),
            'ponto_orvalho': float(dados_raw.get('PTO_INS', 0) or 0),
            'pressao_nivel_mar': float(dados_raw.get('PRE_MAX', 0) or 0),
        }
    
    async def _salvar_dado_climatico(self, estacao_codigo: str, dados: Dict):
        """
        Salva dados climáticos no banco.
        """
        try:
            with get_db_context() as db:
                # Busca estação
                estacao = db.query(EstacaoMeteorologica).filter(
                    EstacaoMeteorologica.codigo_inmet == estacao_codigo
                ).first()
                
                if not estacao:
                    logger.warning(f"Estação {estacao_codigo} não encontrada")
                    return
                
                # Verifica se já existe dado para esta hora
                existe = db.query(DadoClimatico).filter(
                    DadoClimatico.estacao_id == estacao.id,
                    DadoClimatico.data_hora == dados['data_hora']
                ).first()
                
                if existe:
                    return
                
                # Cria registro
                dado_climatico = DadoClimatico(
                    estacao_id=estacao.id,
                    **dados
                )
                
                db.add(dado_climatico)
                db.commit()
                
                # Atualiza última leitura da estação
                estacao.ultima_leitura = dados['data_hora']
                db.commit()
                
        except Exception as e:
            logger.error(f"Erro ao salvar dados climáticos: {e}")
    
    @cache_result(CacheKeys.CLIMA_PREVISAO, ttl=3600, key_params=['lat', 'lon', 'dias'])
    async def obter_previsao_tempo(
        self, 
        lat: float, 
        lon: float, 
        dias: int = 7
    ) -> Optional[List[Dict]]:
        """
        Obtém previsão do tempo para coordenadas específicas.
        
        Args:
            lat: Latitude
            lon: Longitude  
            dias: Número de dias de previsão (máx 15)
            
        Returns:
            Lista com previsões diárias
        """
        try:
            # Usa API do NOMADS/GFS para previsões
            previsoes = await self._buscar_previsao_gfs(lat, lon, dias)
            
            # Salva previsões no banco
            await self._salvar_previsoes(lat, lon, previsoes)
            
            return previsoes
            
        except Exception as e:
            logger.error(f"Erro ao obter previsão: {e}")
            return None
    
    async def _buscar_previsao_gfs(
        self, 
        lat: float, 
        lon: float, 
        dias: int
    ) -> List[Dict]:
        """
        Busca previsão no modelo GFS.
        """
        # URL para acessar dados GFS (exemplo simplificado)
        # Em produção, implementar parser completo dos dados GRIB2
        
        previsoes = []
        
        # Por enquanto, retorna dados simulados
        # TODO: Implementar integração real com NOMADS
        for d in range(dias):
            data_previsao = datetime.now() + timedelta(days=d)
            
            # Simula variação realista de temperatura
            temp_base = 25 + np.sin(d * 0.5) * 5
            
            previsao = {
                'data_previsao': data_previsao,
                'temperatura': round(temp_base + np.random.normal(0, 2), 1),
                'temperatura_min': round(temp_base - 5 + np.random.normal(0, 1), 1),
                'temperatura_max': round(temp_base + 5 + np.random.normal(0, 1), 1),
                'umidade': round(70 + np.random.normal(0, 10), 0),
                'probabilidade_chuva': round(max(0, min(100, 30 + np.random.normal(0, 20))), 0),
                'precipitacao_esperada': round(max(0, np.random.exponential(5)), 1),
                'vento_velocidade': round(max(0, 10 + np.random.normal(0, 5)), 1),
                'vento_direcao': round(np.random.uniform(0, 360), 0),
                'condicao_tempo': np.random.choice(['Ensolarado', 'Parcialmente Nublado', 'Nublado', 'Chuvoso']),
                'modelo_previsao': 'GFS',
                'confiabilidade': round(max(0.6, 0.95 - (d * 0.05)), 2)  # Diminui com o tempo
            }
            
            previsoes.append(previsao)
        
        return previsoes
    
    async def _salvar_previsoes(self, lat: float, lon: float, previsoes: List[Dict]):
        """
        Salva previsões no banco de dados.
        """
        try:
            with get_db_context() as db:
                for previsao in previsoes:
                    # Verifica se já existe previsão para esta data/local
                    existe = db.query(PrevisaoTempo).filter(
                        PrevisaoTempo.latitude == lat,
                        PrevisaoTempo.longitude == lon,
                        PrevisaoTempo.data_previsao == previsao['data_previsao'],
                        PrevisaoTempo.modelo_previsao == previsao['modelo_previsao']
                    ).first()
                    
                    if not existe:
                        nova_previsao = PrevisaoTempo(
                            latitude=lat,
                            longitude=lon,
                            horizonte_horas=(previsao['data_previsao'] - datetime.now()).total_seconds() / 3600,
                            **previsao
                        )
                        db.add(nova_previsao)
                
                db.commit()
        except Exception as e:
            logger.error(f"Erro ao salvar previsões: {e}")
    
    @cache_result(CacheKeys.CORRELACAO_CLIMA, ttl=1800, key_params=['user_id', 'periodo_dias'])
    async def analisar_correlacao_clima_vendas(
        self,
        user_id: int,
        periodo_dias: int = 30
    ) -> Dict:
        """
        Analisa correlação entre clima e vendas.
        
        Args:
            user_id: ID do usuário
            periodo_dias: Período de análise em dias
            
        Returns:
            Análise de correlação
        """
        try:
            with get_db_context() as db:
                # Busca dados de vendas e clima do período
                data_inicio = datetime.now() - timedelta(days=periodo_dias)
                
                # Query para juntar vendas com dados climáticos
                query = f"""
                    SELECT 
                        v.data_venda,
                        v.valor_total,
                        v.categoria,
                        v.quantidade_itens,
                        dc.temperatura,
                        dc.umidade,
                        dc.precipitacao_24h,
                        dc.vento_velocidade,
                        dc.condicao_tempo
                    FROM vendas v
                    LEFT JOIN dados_climaticos dc 
                        ON DATE(v.data_venda) = DATE(dc.data_hora)
                        AND v.hora = EXTRACT(hour FROM dc.data_hora)
                    WHERE v.user_id = :user_id
                    AND v.data_venda >= :data_inicio
                    AND dc.temperatura IS NOT NULL
                    ORDER BY v.data_venda
                """
                
                df = pd.read_sql(query, db.bind, params={
                    'user_id': user_id,
                    'data_inicio': data_inicio
                })
                
                if df.empty or len(df) < 10:
                    return {'erro': 'Dados insuficientes para análise'}
                
                # Calcula correlações
                correlacoes = {
                    'temperatura_vendas': round(df['valor_total'].corr(df['temperatura']), 3),
                    'umidade_vendas': round(df['valor_total'].corr(df['umidade']), 3),
                    'chuva_vendas': round(df['valor_total'].corr(df['precipitacao_24h'].fillna(0)), 3),
                    'vento_vendas': round(df['valor_total'].corr(df['vento_velocidade']), 3),
                }
                
                # Análise por categoria
                correlacoes_categoria = {}
                for categoria in df['categoria'].unique():
                    df_cat = df[df['categoria'] == categoria]
                    if len(df_cat) > 10:
                        correlacoes_categoria[categoria] = {
                            'temperatura': round(df_cat['valor_total'].corr(df_cat['temperatura']), 3),
                            'umidade': round(df_cat['valor_total'].corr(df_cat['umidade']), 3),
                            'chuva': round(df_cat['valor_total'].corr(df_cat['precipitacao_24h'].fillna(0)), 3),
                            'amostras': len(df_cat)
                        }
                
                # Identifica padrões
                padroes = self._identificar_padroes_clima_vendas(df)
                
                # Recomendações baseadas nas correlações
                recomendacoes = self._gerar_recomendacoes_clima(correlacoes, correlacoes_categoria)
                
                return {
                    'correlacoes_gerais': correlacoes,
                    'correlacoes_por_categoria': correlacoes_categoria,
                    'padroes_identificados': padroes,
                    'recomendacoes': recomendacoes,
                    'periodo_analisado': periodo_dias,
                    'total_registros': len(df)
                }
                
        except Exception as e:
            logger.error(f"Erro ao analisar correlação: {e}")
            return {'erro': str(e)}
    
    def _identificar_padroes_clima_vendas(self, df: pd.DataFrame) -> List[Dict]:
        """
        Identifica padrões entre clima e vendas.
        """
        padroes = []
        
        # Padrão: Vendas em dias quentes
        df_quente = df[df['temperatura'] > df['temperatura'].quantile(0.75)]
        if len(df_quente) > 5:
            vendas_media_quente = df_quente['valor_total'].mean()
            vendas_media_geral = df['valor_total'].mean()
            
            if vendas_media_quente > vendas_media_geral * 1.1:
                padroes.append({
                    'tipo': 'temperatura_alta',
                    'descricao': 'Vendas aumentam em dias quentes',
                    'impacto': f"+{((vendas_media_quente / vendas_media_geral - 1) * 100):.1f}%",
                    'confianca': 'alta' if vendas_media_quente > vendas_media_geral * 1.2 else 'média',
                    'temperatura_limite': round(df['temperatura'].quantile(0.75), 1)
                })
        
        # Padrão: Vendas em dias chuvosos
        df_chuva = df[df['precipitacao_24h'] > 0]
        if len(df_chuva) > 5:
            vendas_media_chuva = df_chuva['valor_total'].mean()
            vendas_media_sem_chuva = df[df['precipitacao_24h'] == 0]['valor_total'].mean()
            
            if vendas_media_chuva < vendas_media_sem_chuva * 0.9:
                padroes.append({
                    'tipo': 'chuva',
                    'descricao': 'Vendas diminuem em dias chuvosos',
                    'impacto': f"{((vendas_media_chuva / vendas_media_sem_chuva - 1) * 100):.1f}%",
                    'confianca': 'alta' if vendas_media_chuva < vendas_media_sem_chuva * 0.8 else 'média'
                })
        
        # Padrão: Melhor faixa de temperatura
        df['temp_faixa'] = pd.cut(df['temperatura'], bins=5)
        vendas_por_faixa = df.groupby('temp_faixa')['valor_total'].agg(['mean', 'count'])
        
        if len(vendas_por_faixa) > 3:
            melhor_faixa = vendas_por_faixa['mean'].idxmax()
            if vendas_por_faixa.loc[melhor_faixa, 'count'] > 5:
                padroes.append({
                    'tipo': 'temperatura_otima',
                    'descricao': f'Vendas são melhores entre {melhor_faixa.left:.0f}°C e {melhor_faixa.right:.0f}°C',
                    'impacto': 'Faixa ótima identificada',
                    'confianca': 'média'
                })
        
        return padroes
    
    def _gerar_recomendacoes_clima(
        self, 
        correlacoes: Dict, 
        correlacoes_categoria: Dict
    ) -> List[str]:
        """
        Gera recomendações baseadas nas correlações.
        """
        recomendacoes = []
        
        # Recomendações baseadas em temperatura
        if correlacoes['temperatura_vendas'] > 0.5:
            recomendacoes.append(
                "📈 Forte correlação positiva com temperatura. "
                "Considere aumentar estoque em dias quentes e promover produtos refrescantes."
            )
        elif correlacoes['temperatura_vendas'] < -0.5:
            recomendacoes.append(
                "📉 Correlação negativa com temperatura. "
                "Prepare promoções para dias quentes e foque em produtos adequados ao frio."
            )
        
        # Recomendações baseadas em chuva
        if correlacoes['chuva_vendas'] < -0.3:
            recomendacoes.append(
                "🌧️ Vendas caem em dias chuvosos. "
                "Considere serviços de delivery e promoções online para esses dias."
            )
        
        # Recomendações por categoria
        for categoria, dados in correlacoes_categoria.items():
            if dados['temperatura'] > 0.6:
                recomendacoes.append(
                    f"🔥 {categoria.capitalize()} tem alta sensibilidade à temperatura. "
                    f"Ajuste previsões de demanda conforme previsão do tempo."
                )
        
        # Se não há correlações significativas
        if not recomendacoes:
            recomendacoes.append(
                "📊 Não foram identificadas correlações fortes. "
                "Continue monitorando ou analise um período maior."
            )
        
        return recomendacoes
    
    async def detectar_eventos_climaticos_extremos(
        self,
        estado: str,
        dias_analise: int = 7
    ) -> List[Dict]:
        """
        Detecta eventos climáticos extremos em uma região.
        """
        try:
            with get_db_context() as db:
                # Define thresholds para eventos extremos
                thresholds = {
                    'onda_calor': {'temperatura': 35, 'dias_consecutivos': 3},
                    'onda_frio': {'temperatura': 10, 'dias_consecutivos': 2},
                    'chuva_intensa': {'precipitacao_24h': 50},
                    'seca': {'precipitacao_acumulada_7d': 5}
                }
                
                data_inicio = datetime.now() - timedelta(days=dias_analise)
                
                # Busca dados climáticos do estado
                estacoes = db.query(EstacaoMeteorologica).filter(
                    EstacaoMeteorologica.estado == estado,
                    EstacaoMeteorologica.ativa == True
                ).all()
                
                eventos = []
                
                for estacao in estacoes:
                    # Análise de temperatura
                    dados_temp = db.query(DadoClimatico).filter(
                        DadoClimatico.estacao_id == estacao.id,
                        DadoClimatico.data_hora >= data_inicio
                    ).order_by(DadoClimatico.data_hora).all()
                    
                    if dados_temp:
                        # Detecta ondas de calor
                        dias_quentes = 0
                        for dado in dados_temp:
                            if dado.temperatura and dado.temperatura > thresholds['onda_calor']['temperatura']:
                                dias_quentes += 1
                                if dias_quentes >= thresholds['onda_calor']['dias_consecutivos']:
                                    eventos.append({
                                        'tipo': 'onda_calor',
                                        'severidade': 'alta',
                                        'local': estacao.cidade,
                                        'inicio': dado.data_hora - timedelta(days=dias_quentes-1),
                                        'temperatura_maxima': dado.temperatura,
                                        'descricao': f'Onda de calor em {estacao.cidade} - {dias_quentes} dias consecutivos acima de {thresholds["onda_calor"]["temperatura"]}°C'
                                    })
                            else:
                                dias_quentes = 0
                
                return eventos
                
        except Exception as e:
            logger.error(f"Erro ao detectar eventos extremos: {e}")
            return []
    
    async def buscar_estacoes_proximas(
        self,
        lat: float,
        lon: float,
        raio_km: float = 50
    ) -> List[Dict]:
        """
        Busca estações meteorológicas próximas a uma coordenada.
        """
        try:
            with get_db_context() as db:
                # Query usando função de distância (requer PostGIS)
                query = """
                    SELECT 
                        id,
                        codigo_inmet,
                        nome,
                        cidade,
                        estado,
                        latitude,
                        longitude,
                        ST_Distance(
                            ST_MakePoint(:lon, :lat)::geography,
                            ST_MakePoint(longitude, latitude)::geography
                        ) / 1000 as distancia_km
                    FROM estacoes_meteorologicas
                    WHERE ativa = true
                    AND ST_DWithin(
                        ST_MakePoint(:lon, :lat)::geography,
                        ST_MakePoint(longitude, latitude)::geography,
                        :raio_m
                    )
                    ORDER BY distancia_km
                    LIMIT 10
                """
                
                result = db.execute(query, {
                    'lat': lat,
                    'lon': lon,
                    'raio_m': raio_km * 1000
                })
                
                estacoes = []
                for row in result:
                    estacoes.append({
                        'id': row.id,
                        'codigo_inmet': row.codigo_inmet,
                        'nome': row.nome,
                        'cidade': row.cidade,
                        'estado': row.estado,
                        'latitude': row.latitude,
                        'longitude': row.longitude,
                        'distancia_km': round(row.distancia_km, 1)
                    })
                
                return estacoes
                
        except Exception as e:
            logger.error(f"Erro ao buscar estações próximas: {e}")
            return []

# Instância global do serviço (para uso sem context manager)
clima_service = ClimaService()