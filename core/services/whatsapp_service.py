"""
Service de integração com Evolution API (WhatsApp).

Gerencia toda a comunicação com a Evolution API para envio de mensagens
textuais e interativas (botões de confirmação) via WhatsApp.

Características:
- Envio de mensagens de texto simples
- Envio de mensagens interativas com botões
- Tratamento robusto de erros
- Logs detalhados de todas as operações
"""

import logging
from typing import Optional, Dict, Any
from uuid import UUID

import requests
from django.conf import settings
from django.utils import timezone
from datetime import timedelta

logger = logging.getLogger(__name__)


class WhatsAppService:
    """
    Service para comunicação com a Evolution API (WhatsApp).
    
    Gerencia envio de mensagens textuais e interativas através da
    Evolution API, que atua como gateway para o WhatsApp Business.
    """
    
    def __init__(self):
        """
        Inicializa o service configurando as credenciais da Evolution API.
        """
        self.api_url = getattr(settings, 'EVOLUTION_API_URL', 'http://localhost:8080')
        self.api_key = getattr(settings, 'EVOLUTION_API_KEY', '')
        self.instance_name = getattr(settings, 'EVOLUTION_INSTANCE_NAME', 'caixo_instance')
        
        if not self.api_key:
            logger.warning(
                'EVOLUTION_API_KEY não configurada. Configure no arquivo .env'
            )
        
        # Headers padrão para todas as requisições
        self.headers = {
            'Content-Type': 'application/json',
            'apikey': self.api_key
        }
    
    def send_text_message(self, to_jid: str, text: str) -> bool:
        """
        Envia uma mensagem de texto simples via WhatsApp.
        
        Args:
            to_jid: JID do destinatário (formato: 5541999999999@s.whatsapp.net)
            text: Texto da mensagem a ser enviada
            
        Returns:
            True se enviado com sucesso, False caso contrário
            
        Raises:
            requests.RequestException: Se houver erro na comunicação com a API
        """
        try:
            url = f"{self.api_url}/message/sendText/{self.instance_name}"
            
            payload = {
                "number": to_jid.split('@')[0],  # Remove @s.whatsapp.net se presente
                "text": text
            }
            
            logger.info(f'Enviando mensagem de texto para {to_jid}: {text[:50]}...')
            
            response = requests.post(
                url,
                json=payload,
                headers=self.headers,
                timeout=10
            )
            
            response.raise_for_status()
            result = response.json()
            
            if result.get('status') == 'success' or result.get('key'):
                logger.info(f'Mensagem de texto enviada com sucesso para {to_jid}')
                return True
            else:
                logger.error(f'Falha ao enviar mensagem. Resposta: {result}')
                return False
                
        except requests.exceptions.Timeout:
            logger.error(f'Timeout ao enviar mensagem para {to_jid}')
            return False
        
        except requests.exceptions.RequestException as e:
            logger.error(f'Erro na requisição para Evolution API: {str(e)}')
            return False
        
        except Exception as e:
            logger.error(f'Erro inesperado ao enviar mensagem: {str(e)}')
            return False
    
    def send_confirmation_buttons(
        self,
        to_jid: str,
        session_id: UUID,
        summary_text: str
    ) -> bool:
        """
        Envia mensagem interativa com botões de confirmação.
        
        Cria uma mensagem com botões [✅ Confirmar] e [❌ Cancelar]
        usando o padrão de botões da Evolution API.
        
        O session_id (UUID da ParsingSession) é enviado no callback dos botões
        para identificar qual sessão foi confirmada/cancelada.
        
        Args:
            to_jid: JID do destinatário (formato: 5541999999999@s.whatsapp.net)
            session_id: UUID da ParsingSession para vincular aos botões
            summary_text: Texto resumo da transação extraída pela IA
            
        Returns:
            True se enviado com sucesso, False caso contrário
            
        Raises:
            requests.RequestException: Se houver erro na comunicação com a API
        """
        try:
            url = f"{self.api_url}/message/sendButtons/{self.instance_name}"
            
            # Formata o número removendo @s.whatsapp.net se presente
            number = to_jid.split('@')[0]
            
            # Texto da mensagem com resumo
            message_text = f"""📊 *Resumo do Gasto Extraído:*

{summary_text}

Por favor, confirme se os dados estão corretos:"""
            
            # Botões interativos
            # Cada botão envia um callback com o session_id e a ação
            buttons = [
                {
                    "buttonId": f"confirm_{session_id}",
                    "buttonText": {"displayText": "✅ Confirmar"},
                    "type": 1  # Tipo 1 = resposta rápida
                },
                {
                    "buttonId": f"cancel_{session_id}",
                    "buttonText": {"displayText": "❌ Cancelar"},
                    "type": 1
                }
            ]
            
            payload = {
                "number": number,
                "text": message_text,
                "buttons": buttons,
                "footer": "Caixô - Sistema de Gestão Financeira"
            }
            
            logger.info(f'Enviando mensagem com botões para {to_jid}, session_id: {session_id}')
            
            response = requests.post(
                url,
                json=payload,
                headers=self.headers,
                timeout=10
            )
            
            response.raise_for_status()
            result = response.json()
            
            if result.get('status') == 'success' or result.get('key'):
                logger.info(f'Mensagem com botões enviada com sucesso para {to_jid}')
                return True
            else:
                logger.error(f'Falha ao enviar mensagem com botões. Resposta: {result}')
                return False
                
        except requests.exceptions.Timeout:
            logger.error(f'Timeout ao enviar mensagem com botões para {to_jid}')
            return False
        
        except requests.exceptions.RequestException as e:
            logger.error(f'Erro na requisição para Evolution API: {str(e)}')
            return False
        
        except Exception as e:
            logger.error(f'Erro inesperado ao enviar mensagem com botões: {str(e)}')
            return False
    
    def send_error_message(self, to_jid: str, error_message: str) -> bool:
        """
        Envia mensagem de erro para o usuário quando o parsing falha.
        
        Args:
            to_jid: JID do destinatário
            error_message: Mensagem de erro a ser enviada
            
        Returns:
            True se enviado com sucesso, False caso contrário
        """
        text = f"❌ *Erro ao processar mensagem*\n\n{error_message}\n\nPor favor, tente enviar novamente de forma mais clara."
        return self.send_text_message(to_jid, text)


