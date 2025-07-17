# Serviços de machine learning
import numpy as np
import pandas as pd
from typing import Dict, List, Optional, Tuple, Any
import joblib
import json
from datetime import datetime, timedelta
import logging
from sklearn.ensemble import RandomForestRegressor, GradientBoostingRegressor
from sklearn.preprocessing import StandardScaler
from sklearn.model_selection import train_test_split, cross_val_score, TimeSeriesSplit
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
import tensorflow as tf
from prophet import Prophet
import asyncio
from concurrent.futures import ThreadPoolExecutor
import os

from app.core.config import settings
from app.models.predicoes import Predicao, ModeloML, TipoPredicao, StatusPredicao
from app.models.vendas import Venda
from app.services.cache_service import cache_service, CacheKeys
from app.core.database import get_db_context

logger = logging.getLogger(__name__)

class MLService:
    """
    Serviço de Machine Learning para predições.
    """
    
    def __init__(self):
        self.models_cache = {}
        self.executor = ThreadPoolExecutor(max_workers=4)
        self._ensure_model_directory()
        self._load_models()
    
    def _ensure_model_directory(self):
        """Garante que o diretório de modelos existe."""
        os.makedirs(settings.MODEL_PATH, exist_ok=True)
    
    def _load_models(self):
        """Carrega modelos salvos em memória."""
        try:
            with get_db_context() as db:
                modelos_ativos = db.query(ModeloML).filter(
                    ModeloML.ativo == True,
                    ModeloML.em_producao == True
                ).all()
                
                for modelo in modelos_ativos:
                    try:
                        model_data = {
                            'model': joblib.load(modelo.caminho_modelo),
                            'metadata': modelo.dict()
                        }
                        
                        if modelo.caminho_scaler and os.path.exists(modelo.caminho_scaler):
                            model_data['scaler'] = joblib.load(modelo.caminho_scaler)
                        
                        if modelo.caminho_encoder and os.path.exists(modelo.caminho_encoder):
                            model_data['encoder'] = joblib.load(modelo.caminho_encoder)
                        
                        self.models_cache[modelo.nome] = model_data
                        logger.info(f"Modelo {modelo.nome} carregado com sucesso")
                        
                    except Exception as e:
                        logger.error(f"Erro ao carregar modelo {modelo.nome}: {e}")
        
        except Exception as e:
            logger.error(f"Erro ao carregar modelos: {e}")
    
    async def criar_predicao(
        self,
        user_id: int,
        tipo: TipoPredicao,
        parametros: Dict
    ) -> Predicao:
        """
        Cria uma nova predição.
        
        Args:
            user_id: ID do usuário
            tipo: Tipo de predição
            parametros: Parâmetros da predição
            
        Returns:
            Objeto Predicao criado
        """
        try:
            with get_db_context() as db:
                # Cria registro de predição
                predicao = Predicao(
                    user_id=user_id,
                    tipo=tipo,
                    status=StatusPredicao.PENDENTE,
                    data_inicio=parametros.get('data_inicio', datetime.now()),
                    data_fim=parametros.get('data_fim', datetime.now() + timedelta(days=7)),
                    horizonte_dias=parametros.get('horizonte_dias', 7),
                    parametros=parametros
                )
                
                db.add(predicao)
                db.commit()
                db.refresh(predicao)
                
                # Processa predição assincronamente
                asyncio.create_task(self._processar_predicao(predicao.id))
                
                return predicao
                
        except Exception as e:
            logger.error(f"Erro ao criar predição: {e}")
            raise
    
    async def _processar_predicao(self, predicao_id: int):
        """
        Processa uma predição de forma assíncrona.
        """
        try:
            with get_db_context() as db:
                # Atualiza status
                predicao = db.query(Predicao).filter(Predicao.id == predicao_id).first()
                if not predicao:
                    return
                
                predicao.status = StatusPredicao.PROCESSANDO
                predicao.iniciado_em = datetime.now()
                db.commit()
                
                # Executa predição baseada no tipo
                if predicao.tipo == TipoPredicao.VENDAS_DIARIA:
                    resultado = await self._prever_vendas_diarias(predicao)
                elif predicao.tipo == TipoPredicao.VENDAS_SEMANAL:
                    resultado = await self._prever_vendas_semanais(predicao)
                elif predicao.tipo == TipoPredicao.DEMANDA_PRODUTO:
                    resultado = await self._prever_demanda_produto(predicao)
                else:
                    raise ValueError(f"Tipo de predição não suportado: {predicao.tipo}")
                
                # Atualiza resultado
                predicao.resultado = resultado['predicoes']
                predicao.metricas = resultado['metricas']
                predicao.confianca = resultado['confianca']
                predicao.modelo_nome = resultado['modelo_utilizado']
                predicao.modelo_versao = resultado.get('modelo_versao', '1.0')
                predicao.status = StatusPredicao.CONCLUIDA
                predicao.concluido_em = datetime.now()
                predicao.tempo_processamento = (
                    predicao.concluido_em - predicao.iniciado_em
                ).total_seconds()
                
                db.commit()
                
                # Limpa cache relacionado
                cache_service.delete_pattern(f"{CacheKeys.PREDICAO_RESULTADO}:{predicao_id}:*")
                
        except Exception as e:
            logger.error(f"Erro ao processar predição {predicao_id}: {e}")
            
            with get_db_context() as db:
                predicao = db.query(Predicao).filter(Predicao.id == predicao_id).first()
                if predicao:
                    predicao.status = StatusPredicao.ERRO
                    predicao.erro_mensagem = str(e)
                    predicao.concluido_em = datetime.now()
                    db.commit()
    
    async def _prever_vendas_diarias(self, predicao: Predicao) -> Dict:
        """
        Realiza predição de vendas diárias.
        """
        try:
            # Busca dados históricos
            df_vendas = await self._preparar_dados_vendas(
                predicao.user_id,
                predicao.parametros
            )
            
            if len(df_vendas) < settings.MIN_TRAINING_SAMPLES:
                raise ValueError(f"Dados insuficientes para predição. Mínimo necessário: {settings.MIN_TRAINING_SAMPLES}")
            
            # Prepara features
            X, y, feature_names = self._preparar_features_vendas(df_vendas)
            
            # Treina modelo se necessário ou usa existente
            modelo_nome = f"vendas_diarias_user_{predicao.user_id}"
            
            if modelo_nome not in self.models_cache:
                modelo_info = await self._treinar_modelo_vendas(X, y, feature_names, modelo_nome)
                self.models_cache[modelo_nome] = modelo_info
            else:
                modelo_info = self.models_cache[modelo_nome]
            
            # Gera predições
            predicoes = await self._gerar_predicoes_vendas(
                modelo_info,
                predicao.data_inicio,
                predicao.data_fim,
                predicao.parametros,
                df_vendas
            )
            
            # Calcula métricas de confiança
            metricas = self._calcular_metricas_confianca(
                modelo_info['model'],
                X,
                y
            )
            
            return {
                'predicoes': predicoes,
                'metricas': metricas,
                'confianca': metricas.get('r2_score', 0) * 100,
                'modelo_utilizado': 'RandomForest',
                'modelo_versao': '1.0'
            }
            
        except Exception as e:
            logger.error(f"Erro na predição de vendas diárias: {e}")
            raise
    
    async def _preparar_dados_vendas(
        self,
        user_id: int,
        parametros: Dict
    ) -> pd.DataFrame:
        """
        Prepara dados de vendas para treinamento.
        """
        with get_db_context() as db:
            # Define período de dados históricos
            meses_historico = parametros.get('meses_historico', 12)
            data_inicio = datetime.now() - timedelta(days=meses_historico * 30)
            
            # Query otimizada
            query = """
                SELECT 
                    v.*,
                    dc.temperatura,
                    dc.umidade,
                    dc.precipitacao_24h,
                    dc.vento_velocidade,
                    dc.condicao_tempo
                FROM vendas v
                LEFT JOIN lateral (
                    SELECT 
                        temperatura,
                        umidade,
                        precipitacao_24h,
                        vento_velocidade,
                        condicao_tempo
                    FROM dados_climaticos dc
                    INNER JOIN estacoes_meteorologicas e 
                        ON dc.estacao_id = e.id
                    WHERE e.cidade = v.cidade
                    AND e.estado = v.estado
                    AND DATE(dc.data_hora) = DATE(v.data_venda)
                    AND EXTRACT(hour FROM dc.data_hora) = v.hora
                    ORDER BY ABS(EXTRACT(epoch FROM (dc.data_hora - v.data_venda)))
                    LIMIT 1
                ) dc ON true
                WHERE v.user_id = :user_id
                AND v.data_venda >= :data_inicio
                ORDER BY v.data_venda
            """
            
            df = pd.read_sql(
                query,
                db.bind,
                params={'user_id': user_id, 'data_inicio': data_inicio}
            )
            
            # Converte colunas de data
            df['data_venda'] = pd.to_datetime(df['data_venda'])
            
            # Preenche dados faltantes de clima
            df['temperatura'].fillna(df['temperatura'].mean(), inplace=True)
            df['umidade'].fillna(df['umidade'].mean(), inplace=True)
            df['precipitacao_24h'].fillna(0, inplace=True)
            df['vento_velocidade'].fillna(df['vento_velocidade'].mean(), inplace=True)
            
            return df
    
    def _preparar_features_vendas(
        self,
        df: pd.DataFrame
    ) -> Tuple[np.ndarray, np.ndarray, List[str]]:
        """
        Prepara features para modelo de vendas.
        """
        # Cria features temporais
        df['dia_ano'] = df['data_venda'].dt.dayofyear
        df['dia_mes'] = df['data_venda'].dt.day
        df['dia_semana'] = df['data_venda'].dt.dayofweek
        df['mes'] = df['data_venda'].dt.month
        df['trimestre'] = df['data_venda'].dt.quarter
        df['is_fim_semana'] = df['dia_semana'].isin([5, 6]).astype(int)
        
        # Features de lag (valores passados)
        for lag in [1, 7, 30]:
            df[f'vendas_lag_{lag}'] = df['valor_total'].shift(lag)
            df[f'itens_lag_{lag}'] = df['quantidade_itens'].shift(lag)
        
        # Médias móveis
        for window in [7, 30]:
            df[f'media_movel_{window}'] = df['valor_total'].rolling(window).mean()
            df[f'desvio_movel_{window}'] = df['valor_total'].rolling(window).std()
        
        # Features climáticas
        df['temp_squared'] = df['temperatura'] ** 2
        df['temp_umidade_interaction'] = df['temperatura'] * df['umidade']
        df['chuva_binary'] = (df['precipitacao_24h'] > 0).astype(int)
        
        # Features categóricas (one-hot encoding)
        categoria_dummies = pd.get_dummies(df['categoria'], prefix='categoria')
        canal_dummies = pd.get_dummies(df['canal'], prefix='canal')
        
        # Remove NaN criados por lag e rolling
        df.dropna(inplace=True)
        
        # Define features
        feature_cols = [
            'dia_ano', 'dia_mes', 'dia_semana', 'mes', 'trimestre',
            'is_fim_semana', 'feriado',
            'temperatura', 'temp_squared', 'umidade', 'precipitacao_24h',
            'vento_velocidade', 'temp_umidade_interaction', 'chuva_binary',
            'vendas_lag_1', 'vendas_lag_7', 'vendas_lag_30',
            'itens_lag_1', 'itens_lag_7', 'itens_lag_30',
            'media_movel_7', 'media_movel_30',
            'desvio_movel_7', 'desvio_movel_30'
        ]
        
        # Adiciona dummies
        df = pd.concat([df, categoria_dummies, canal_dummies], axis=1)
        feature_cols.extend(categoria_dummies.columns.tolist())
        feature_cols.extend(canal_dummies.columns.tolist())
        
        X = df[feature_cols].values
        y = df['valor_total'].values
        
        return X, y, feature_cols
    
    async def _treinar_modelo_vendas(
        self,
        X: np.ndarray,
        y: np.ndarray,
        feature_names: List[str],
        modelo_nome: str
    ) -> Dict:
        """
        Treina modelo de predição de vendas.
        """
        # Divide dados usando TimeSeriesSplit
        tscv = TimeSeriesSplit(n_splits=5)
        
        # Normaliza features
        scaler = StandardScaler()
        X_scaled = scaler.fit_transform(X)
        
        # Treina modelo RandomForest
        modelo = RandomForestRegressor(
            n_estimators=100,
            max_depth=15,
            min_samples_split=10,
            min_samples_leaf=5,
            random_state=42,
            n_jobs=-1
        )
        
        # Validação cruzada temporal
        cv_scores = cross_val_score(
            modelo, X_scaled, y, 
            cv=tscv, 
            scoring='r2',
            n_jobs=-1
        )
        
        # Treina modelo final
        modelo.fit(X_scaled, y)
        
        # Avalia modelo no conjunto de teste (últimos 20%)
        test_size = int(len(X) * 0.2)
        X_test, y_test = X_scaled[-test_size:], y[-test_size:]
        y_pred = modelo.predict(X_test)
        
        mae = mean_absolute_error(y_test, y_pred)
        rmse = np.sqrt(mean_squared_error(y_test, y_pred))
        r2 = r2_score(y_test, y_pred)
        
        # Feature importance
        feature_importance = dict(zip(feature_names, modelo.feature_importances_))
        feature_importance = dict(sorted(
            feature_importance.items(), 
            key=lambda x: x[1], 
            reverse=True
        )[:20])  # Top 20 features
        
        # Salva modelo
        modelo_info = {
            'model': modelo,
            'scaler': scaler,
            'feature_names': feature_names,
            'metrics': {
                'mae': float(mae),
                'rmse': float(rmse),
                'r2_score': float(r2),
                'cv_scores': cv_scores.tolist(),
                'cv_score_mean': float(cv_scores.mean()),
                'cv_score_std': float(cv_scores.std())
            },
            'feature_importance': feature_importance,
            'trained_at': datetime.now()
        }
        
        # Salva no banco e disco
        await self._salvar_modelo_db(modelo_nome, modelo_info)
        
        return modelo_info
    
    async def _gerar_predicoes_vendas(
        self,
        modelo_info: Dict,
        data_inicio: datetime,
        data_fim: datetime,
        parametros: Dict,
        df_historico: pd.DataFrame
    ) -> List[Dict]:
        """
        Gera predições de vendas para o período especificado.
        """
        modelo = modelo_info['model']
        scaler = modelo_info['scaler']
        feature_names = modelo_info['feature_names']
        
        # Prepara DataFrame para predições
        dates = pd.date_range(data_inicio, data_fim, freq='D')
        predicoes = []
        
        # Última linha de dados históricos para features de lag
        ultimo_registro = df_historico.iloc[-1]
        
        for date in dates:
            # Cria features para a data
            features = self._criar_features_predicao(
                date, 
                df_historico, 
                ultimo_registro,
                parametros
            )
            
            # Garante que temos todas as features necessárias
            features_array = []
            for fname in feature_names:
                if fname in features:
                    features_array.append(features[fname])
                else:
                    # Para features categóricas one-hot
                    features_array.append(0)
            
            # Normaliza
            features_scaled = scaler.transform([features_array])
            
            # Predição
            valor_previsto = modelo.predict(features_scaled)[0]
            
            # Intervalo de confiança (usando árvores individuais)
            if hasattr(modelo, 'estimators_'):
                predictions = np.array([tree.predict(features_scaled)[0] for tree in modelo.estimators_])
                intervalo_inferior = np.percentile(predictions, 5)
                intervalo_superior = np.percentile(predictions, 95)
            else:
                # Fallback simples
                intervalo_inferior = valor_previsto * 0.9
                intervalo_superior = valor_previsto * 1.1
            
            predicao = {
                'data': date.isoformat(),
                'valor_previsto': round(float(valor_previsto), 2),
                'intervalo_confianca_inferior': round(float(intervalo_inferior), 2),
                'intervalo_confianca_superior': round(float(intervalo_superior), 2),
                'dia_semana': date.strftime('%A'),
                'features_utilizadas': features
            }
            
            predicoes.append(predicao)
            
            # Atualiza último registro para próxima iteração (simula lag)
            ultimo_registro = pd.Series({
                'valor_total': valor_previsto,
                'data_venda': date
            })
        
        return predicoes
    
    def _criar_features_predicao(
        self,
        date: datetime,
        df_historico: pd.DataFrame,
        ultimo_registro: pd.Series,
        parametros: Dict
    ) -> Dict:
        """
        Cria features para uma data específica de predição.
        """
        features = {}
        
        # Features temporais
        features['dia_ano'] = date.timetuple().tm_yday
        features['dia_mes'] = date.day
        features['dia_semana'] = date.weekday()
        features['mes'] = date.month
        features['trimestre'] = (date.month - 1) // 3 + 1
        features['is_fim_semana'] = 1 if date.weekday() >= 5 else 0
        
        # Verifica feriados (simplificado)
        features['feriado'] = 0  # TODO: Implementar calendário de feriados
        
        # Features climáticas (usar previsão ou média histórica)
        if 'previsao_clima' in parametros:
            clima = parametros['previsao_clima'].get(date.date(), {})
            features['temperatura'] = clima.get('temperatura', 25)
            features['umidade'] = clima.get('umidade', 70)
            features['precipitacao_24h'] = clima.get('precipitacao', 0)
            features['vento_velocidade'] = clima.get('vento', 10)
        else:
            # Usa médias históricas para o mês
            mes_historico = df_historico[df_historico['mes'] == date.month]
            features['temperatura'] = mes_historico['temperatura'].mean() if len(mes_historico) > 0 else 25
            features['umidade'] = mes_historico['umidade'].mean() if len(mes_historico) > 0 else 70
            features['precipitacao_24h'] = 0
            features['vento_velocidade'] = 10
        
        # Features derivadas
        features['temp_squared'] = features['temperatura'] ** 2
        features['temp_umidade_interaction'] = features['temperatura'] * features['umidade']
        features['chuva_binary'] = 1 if features['precipitacao_24h'] > 0 else 0
        
        # Lags (simplificado - usar últimos valores conhecidos)
        features['vendas_lag_1'] = float(ultimo_registro['valor_total'])
        features['vendas_lag_7'] = float(df_historico.tail(7)['valor_total'].mean())
        features['vendas_lag_30'] = float(df_historico.tail(30)['valor_total'].mean())
        
        features['itens_lag_1'] = 50  # Valor padrão
        features['itens_lag_7'] = 50
        features['itens_lag_30'] = 50
        
        # Médias móveis
        features['media_movel_7'] = float(df_historico.tail(7)['valor_total'].mean())
        features['media_movel_30'] = float(df_historico.tail(30)['valor_total'].mean())
        features['desvio_movel_7'] = float(df_historico.tail(7)['valor_total'].std())
        features['desvio_movel_30'] = float(df_historico.tail(30)['valor_total'].std())
        
        # Categoria e canal mais frequentes (para one-hot)
        categoria_mais_frequente = df_historico['categoria'].mode()[0] if len(df_historico) > 0 else 'outros'
        canal_mais_frequente = df_historico['canal'].mode()[0] if len(df_historico) > 0 else 'loja_fisica'
        
        features[f'categoria_{categoria_mais_frequente}'] = 1
        features[f'canal_{canal_mais_frequente}'] = 1
        
        return features
    
    def _calcular_metricas_confianca(
        self,
        modelo: Any,
        X: np.ndarray,
        y: np.ndarray
    ) -> Dict:
        """
        Calcula métricas de confiança do modelo.
        """
        # Cross-validation temporal
        tscv = TimeSeriesSplit(n_splits=3)
        
        cv_scores = cross_val_score(
            modelo, X, y, 
            cv=tscv, 
            scoring='r2', 
            n_jobs=-1
        )
        
        # Calcula MAPE (Mean Absolute Percentage Error)
        y_pred = modelo.predict(X)
        mape = np.mean(np.abs((y - y_pred) / y)) * 100
        
        return {
            'r2_score': float(np.mean(cv_scores)),
            'r2_std': float(np.std(cv_scores)),
            'cv_scores': cv_scores.tolist(),
            'mape': float(mape),
            'samples_used': len(y)
        }
    
    async def _salvar_modelo_db(self, modelo_nome: str, modelo_info: Dict):
        """
        Salva modelo no banco de dados e disco.
        """
        try:
            # Salva arquivos
            modelo_path = os.path.join(settings.MODEL_PATH, f"{modelo_nome}_model.pkl")
            scaler_path = os.path.join(settings.MODEL_PATH, f"{modelo_nome}_scaler.pkl")
            
            joblib.dump(modelo_info['model'], modelo_path)
            joblib.dump(modelo_info['scaler'], scaler_path)
            
            with get_db_context() as db:
                # Verifica se modelo já existe
                modelo_db = db.query(ModeloML).filter(
                    ModeloML.nome == modelo_nome
                ).first()
                
                if not modelo_db:
                    modelo_db = ModeloML(
                        nome=modelo_nome,
                        versao="1.0",
                        tipo="series_temporais",
                        algoritmo="RandomForest",
                        descricao="Modelo de predição de vendas diárias"
                    )
                    db.add(modelo_db)
                
                # Atualiza informações
                modelo_db.caminho_modelo = modelo_path
                modelo_db.caminho_scaler = scaler_path
                modelo_db.features_entrada = modelo_info['feature_names']
                modelo_db.features_importancia = modelo_info['feature_importance']
                modelo_db.metricas_treino = modelo_info['metrics']
                modelo_db.hiperparametros = {
                    'n_estimators': 100,
                    'max_depth': 15,
                    'min_samples_split': 10,
                    'min_samples_leaf': 5
                }
                modelo_db.ativo = True
                modelo_db.em_producao = True
                modelo_db.treinado_em = modelo_info['trained_at']
                
                db.commit()
                
        except Exception as e:
            logger.error(f"Erro ao salvar modelo: {e}")
    
    async def obter_feature_importance(
        self,
        modelo_nome: str
    ) -> Dict[str, float]:
        """
        Retorna importância das features de um modelo.
        """
        if modelo_nome in self.models_cache:
            return self.models_cache[modelo_nome].get('feature_importance', {})
        
        # Busca no banco
        with get_db_context() as db:
            modelo = db.query(ModeloML).filter(
                ModeloML.nome == modelo_nome
            ).first()
            
            if modelo and modelo.features_importancia:
                return modelo.features_importancia
        
        return {}
    
    async def retreinar_modelos(self, user_id: Optional[int] = None):
        """
        Retreina modelos com dados mais recentes.
        """
        try:
            modelos_para_retreinar = []
            
            if user_id:
                # Retreina apenas modelos do usuário
                modelos_para_retreinar = [
                    nome for nome in self.models_cache.keys()
                    if f"user_{user_id}" in nome
                ]
            else:
                # Retreina todos os modelos
                modelos_para_retreinar = list(self.models_cache.keys())
            
            for modelo_nome in modelos_para_retreinar:
                logger.info(f"Retreinando modelo {modelo_nome}")
                
                # Extrai user_id do nome do modelo
                if "user_" in modelo_nome:
                    user_id_modelo = int(modelo_nome.split("user_")[1].split("_")[0])
                    
                    # Prepara dados atualizados
                    df_vendas = await self._preparar_dados_vendas(
                        user_id_modelo,
                        {'meses_historico': 12}
                    )
                    
                    if len(df_vendas) >= settings.MIN_TRAINING_SAMPLES:
                        # Prepara features
                        X, y, feature_names = self._preparar_features_vendas(df_vendas)
                        
                        # Retreina
                        modelo_info = await self._treinar_modelo_vendas(
                            X, y, feature_names, modelo_nome
                        )
                        
                        # Atualiza cache
                        self.models_cache[modelo_nome] = modelo_info
                        
                        logger.info(f"Modelo {modelo_nome} retreinado com sucesso")
                
        except Exception as e:
            logger.error(f"Erro ao retreinar modelos: {e}")
    
    async def analisar_performance_modelo(
        self,
        modelo_nome: str,
        periodo_dias: int = 30
    ) -> Dict:
        """
        Analisa performance histórica de um modelo.
        """
        try:
            with get_db_context() as db:
                # Busca predições do modelo
                data_inicio = datetime.now() - timedelta(days=periodo_dias)
                
                query = """
                    SELECT 
                        hp.data_referencia,
                        hp.valor_previsto,
                        hp.valor_realizado,
                        hp.erro_absoluto,
                        hp.erro_percentual
                    FROM historico_predicoes hp
                    JOIN predicoes p ON hp.predicao_id = p.id
                    WHERE p.modelo_nome = :modelo_nome
                    AND hp.data_referencia >= :data_inicio
                    AND hp.valor_realizado IS NOT NULL
                    ORDER BY hp.data_referencia
                """
                
                df = pd.read_sql(query, db.bind, params={
                    'modelo_nome': modelo_nome,
                    'data_inicio': data_inicio
                })
                
                if df.empty:
                    return {'erro': 'Sem dados históricos para análise'}
                
                # Calcula métricas
                mae = df['erro_absoluto'].mean()
                rmse = np.sqrt((df['erro_absoluto'] ** 2).mean())
                mape = df['erro_percentual'].abs().mean()
                
                # Análise temporal
                df['data_referencia'] = pd.to_datetime(df['data_referencia'])
                df['dia_semana'] = df['data_referencia'].dt.dayofweek
                
                erro_por_dia_semana = df.groupby('dia_semana')['erro_percentual'].mean()
                
                return {
                    'periodo_analisado': periodo_dias,
                    'total_predicoes': len(df),
                    'metricas': {
                        'mae': float(mae),
                        'rmse': float(rmse),
                        'mape': float(mape)
                    },
                    'erro_por_dia_semana': erro_por_dia_semana.to_dict(),
                    'tendencia_erro': self._analisar_tendencia_erro(df)
                }
                
        except Exception as e:
            logger.error(f"Erro ao analisar performance: {e}")
            return {'erro': str(e)}
    
    def _analisar_tendencia_erro(self, df: pd.DataFrame) -> str:
        """
        Analisa se o erro do modelo está aumentando ou diminuindo.
        """
        if len(df) < 10:
            return "Dados insuficientes"
        
        # Divide em duas metades
        meio = len(df) // 2
        erro_primeira_metade = df.iloc[:meio]['erro_percentual'].abs().mean()
        erro_segunda_metade = df.iloc[meio:]['erro_percentual'].abs().mean()
        
        if erro_segunda_metade < erro_primeira_metade * 0.9:
            return "Melhorando"
        elif erro_segunda_metade > erro_primeira_metade * 1.1:
            return "Piorando"
        else:
            return "Estável"

# Instância global do serviço
ml_service = MLService()