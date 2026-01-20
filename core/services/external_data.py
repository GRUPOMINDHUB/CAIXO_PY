"""
Service para integração com APIs externas e fontes de dados.

Fornece dados de:
- Previsão do tempo (OpenWeatherMap)
- Feriados nacionais e regionais (python-holidays)
- Eventos locais (via OpenAI GPT-4o-mini)
"""

import logging
import os
from datetime import date, timedelta
from decimal import Decimal
from typing import Dict, List, Optional, Tuple
from django.core.cache import cache
from django.conf import settings
import requests
import holidays
from openai import OpenAI

logger = logging.getLogger(__name__)


class ExternalDataService:
    """
    Service para buscar dados externos que impactam o faturamento.
    
    Utiliza cache para otimizar chamadas de API e reduzir custos.
    """
    
    def __init__(self):
        self.openweather_api_key = os.getenv('OPENWEATHER_API_KEY')
        self.openai_client = OpenAI(api_key=os.getenv('OPENAI_API_KEY')) if os.getenv('OPENAI_API_KEY') else None
    
    def get_weather_forecast(
        self,
        city: str,
        neighborhood: Optional[str] = None,
        start_date: date = None,
        end_date: date = None
    ) -> Dict:
        """
        Busca previsão do tempo para uma localidade.
        
        Args:
            city: Nome da cidade
            neighborhood: Nome do bairro (opcional, usado para refinamento)
            start_date: Data inicial da previsão
            end_date: Data final da previsão
            
        Returns:
            Dict com previsão do tempo e alertas relevantes
        """
        if not self.openweather_api_key:
            logger.warning('OPENWEATHER_API_KEY não configurada. Retornando dados mockados.')
            return self._get_mock_weather()
        
        if not city:
            return {'error': 'Cidade não informada', 'forecast': [], 'alerts': []}
        
        # Cache key baseado na localidade e período
        cache_key = f'weather_{city}_{neighborhood}_{start_date}_{end_date}'
        cached_data = cache.get(cache_key)
        if cached_data:
            logger.info(f'Retornando previsão do tempo do cache para {city}')
            return cached_data
        
        try:
            # Busca coordenadas da cidade (geocoding)
            geocoding_url = 'http://api.openweathermap.org/geo/1.0/direct'
            geocoding_params = {
                'q': f"{city},BR",
                'limit': 1,
                'appid': self.openweather_api_key
            }
            
            geocoding_response = requests.get(geocoding_url, params=geocoding_params, timeout=10)
            geocoding_response.raise_for_status()
            geocoding_data = geocoding_response.json()
            
            if not geocoding_data:
                logger.warning(f'Cidade {city} não encontrada na API do OpenWeatherMap')
                return self._get_mock_weather()
            
            lat = geocoding_data[0]['lat']
            lon = geocoding_data[0]['lon']
            
            # Busca previsão do tempo (5 dias)
            forecast_url = 'https://api.openweathermap.org/data/2.5/forecast'
            forecast_params = {
                'lat': lat,
                'lon': lon,
                'appid': self.openweather_api_key,
                'units': 'metric',
                'lang': 'pt_br'
            }
            
            forecast_response = requests.get(forecast_url, params=forecast_params, timeout=10)
            forecast_response.raise_for_status()
            forecast_data = forecast_response.json()
            
            # Processa previsão e gera alertas
            alerts = []
            forecast_list = []
            
            for item in forecast_data.get('list', [])[:40]:  # Próximas 40 previsões (5 dias)
                forecast_date = date.fromtimestamp(item['dt'])
                if start_date and forecast_date < start_date:
                    continue
                if end_date and forecast_date > end_date:
                    continue
                
                weather_main = item['weather'][0]['main']
                weather_desc = item['weather'][0]['description']
                temp = item['main']['temp']
                rain = item.get('rain', {}).get('3h', 0)  # Chuva em mm nas últimas 3h
                
                forecast_list.append({
                    'date': forecast_date,
                    'main': weather_main,
                    'description': weather_desc,
                    'temp': temp,
                    'rain_mm': rain
                })
                
                # Lógica de negócio: alerta para chuva intensa no final de semana
                weekday = forecast_date.weekday()
                is_weekend = weekday >= 5  # Sábado = 5, Domingo = 6
                
                if is_weekend and rain > 5.0:  # Chuva > 5mm
                    alerts.append({
                        'type': 'rain',
                        'date': forecast_date,
                        'message': f'Previsão de chuva intensa ({rain:.1f}mm) no final de semana: Atenção ao estoque de delivery!',
                        'severity': 'warning'
                    })
            
            result = {
                'forecast': forecast_list,
                'alerts': alerts,
                'location': {
                    'city': city,
                    'neighborhood': neighborhood,
                    'coordinates': {'lat': lat, 'lon': lon}
                }
            }
            
            # Cache por 6 horas
            cache.set(cache_key, result, timeout=6 * 60 * 60)
            
            return result
            
        except requests.RequestException as e:
            logger.error(f'Erro ao buscar previsão do tempo: {str(e)}', exc_info=True)
            return self._get_mock_weather()
        except Exception as e:
            logger.error(f'Erro inesperado ao buscar previsão do tempo: {str(e)}', exc_info=True)
            return self._get_mock_weather()
    
    def _get_mock_weather(self) -> Dict:
        """Retorna dados mockados quando a API não está disponível."""
        return {
            'forecast': [],
            'alerts': [],
            'location': {'city': 'Não disponível', 'neighborhood': None},
            'error': 'API de clima não configurada'
        }
    
    def get_holidays(
        self,
        state: str = 'BR',
        start_date: date = None,
        end_date: date = None
    ) -> List[Dict]:
        """
        Busca feriados nacionais e estaduais no período.
        
        Args:
            state: Sigla do estado (ex: 'SP', 'RJ') ou 'BR' para apenas nacionais
            start_date: Data inicial
            end_date: Data final
            
        Returns:
            Lista de feriados com data e descrição
        """
        if not start_date:
            start_date = date.today()
        if not end_date:
            end_date = start_date + timedelta(days=30)
        
        # Cache key
        cache_key = f'holidays_{state}_{start_date}_{end_date}'
        cached_data = cache.get(cache_key)
        if cached_data:
            return cached_data
        
        try:
            # Cria objeto de feriados brasileiros
            br_holidays = holidays.Brazil(state=state if state != 'BR' else None)
            
            holidays_list = []
            current_date = start_date
            while current_date <= end_date:
                holiday_name = br_holidays.get(current_date)
                if holiday_name:
                    holidays_list.append({
                        'date': current_date,
                        'name': holiday_name,
                        'type': 'nacional' if state == 'BR' else 'estadual'
                    })
                current_date += timedelta(days=1)
            
            # Cache por 24 horas (feriados não mudam com frequência)
            cache.set(cache_key, holidays_list, timeout=24 * 60 * 60)
            
            return holidays_list
            
        except Exception as e:
            logger.error(f'Erro ao buscar feriados: {str(e)}', exc_info=True)
            return []
    
    def get_local_events(
        self,
        city: str,
        neighborhood: Optional[str] = None,
        start_date: date = None,
        end_date: date = None
    ) -> List[Dict]:
        """
        Busca eventos locais que impactam o fluxo de pessoas na região.
        
        Utiliza OpenAI GPT-4o-mini para "pesquisar" eventos conhecidos.
        
        Args:
            city: Nome da cidade
            neighborhood: Nome do bairro
            start_date: Data inicial
            end_date: Data final
            
        Returns:
            Lista de eventos com data, nome e descrição
        """
        if not self.openai_client:
            logger.warning('OpenAI não configurada. Retornando lista vazia de eventos.')
            return []
        
        if not city:
            return []
        
        if not start_date:
            start_date = date.today()
        if not end_date:
            end_date = start_date + timedelta(days=30)
        
        # Cache key
        cache_key = f'events_{city}_{neighborhood}_{start_date}_{end_date}'
        cached_data = cache.get(cache_key)
        if cached_data:
            return cached_data
        
        try:
            location_query = f"{neighborhood}, {city}" if neighborhood else city
            
            prompt = f"""Você é um assistente especializado em identificar eventos que geram fluxo de pessoas em estabelecimentos comerciais.

Pesquise eventos (jogos de futebol, shows, feiras, festivais, eventos esportivos, convenções, etc.) que acontecerão em {location_query} entre {start_date.strftime('%d/%m/%Y')} e {end_date.strftime('%d/%m/%Y')}.

Foque em eventos que geram "fluxo de pessoas" - ou seja, eventos que fazem a região ficar mais movimentada ou mais vazia do que o normal.

Retorne APENAS um JSON array com objetos no formato:
[
  {{
    "date": "DD/MM/YYYY",
    "name": "Nome do evento",
    "description": "Descrição breve do evento e seu impacto no fluxo",
    "impact": "alto" ou "médio" ou "baixo"
  }}
]

Se não houver eventos conhecidos, retorne uma lista vazia [].
NÃO invente eventos. Seja realista e baseado em conhecimento geral."""

            response = self.openai_client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": "Você é um assistente especializado em eventos e cultura local brasileira. Retorne APENAS JSON válido, sem explicações."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.3,
                max_tokens=1000
            )
            
            content = response.choices[0].message.content.strip()
            
            # Remove markdown code blocks se houver
            if content.startswith('```'):
                lines = content.split('\n')
                content = '\n'.join(lines[1:-1]) if len(lines) > 2 else content
            
            import json
            events = json.loads(content)
            
            # Converte datas para objetos date
            for event in events:
                try:
                    event['date'] = date.strptime(event['date'], '%d/%m/%Y')
                except (ValueError, KeyError):
                    continue
            
            # Cache por 6 horas
            cache.set(cache_key, events, timeout=6 * 60 * 60)
            
            logger.info(f'Encontrados {len(events)} eventos para {location_query}')
            return events
            
        except Exception as e:
            logger.error(f'Erro ao buscar eventos locais via OpenAI: {str(e)}', exc_info=True)
            return []


def get_external_data_service() -> ExternalDataService:
    """
    Factory function para obter instância do ExternalDataService.
    
    Returns:
        Instância configurada do service
    """
    return ExternalDataService()
