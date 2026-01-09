"""
Views de webhooks para integração com Evolution API (WhatsApp).

Recebe mensagens e callbacks de botões da Evolution API e processa
de forma assíncrona utilizando tasks do Celery.

Endpoints:
- POST /api/v1/webhooks/evolution/ - Recebe mensagens
- POST /api/v1/webhooks/evolution/buttons/ - Recebe callbacks de botões
"""

import json
import logging
from typing import Dict, Any
from uuid import UUID

from django.http import JsonResponse, HttpRequest
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.utils.decorators import method_decorator
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework import status

from core.models import User
from core.models.finance import ParsingSession, ParsingSessionStatus, Transaction, Installment
from core.models.finance import Category, Subcategory
from core.tasks import process_incoming_message
from core.utils.tenant_context import set_current_tenant, clear_tenant

logger = logging.getLogger(__name__)


@api_view(['POST'])
@permission_classes([AllowAny])
@csrf_exempt
def evolution_webhook(request: HttpRequest) -> Response:
    """
    Webhook para receber mensagens da Evolution API.
    
    Endpoint: POST /api/v1/webhooks/evolution/
    
    Valida se o remetente (número do WhatsApp) pertence a um usuário ativo
    e dispara task assíncrona para processar a mensagem com IA.
    
    Responde 200 OK imediatamente para não travar a Evolution API.
    
    Payload esperado da Evolution API:
    {
        "data": {
            "key": {...},
            "message": {
                "conversation": "texto da mensagem",
                ...
            },
            "pushName": "Nome",
            "participant": "5541999999999@s.whatsapp.net"
        },
        "event": "messages.upsert"
    }
    
    Returns:
        Response 200 OK sempre (para não travar Evolution API)
    """
    try:
        logger.info('[WEBHOOK] Mensagem recebida da Evolution API')
        logger.debug(f'[WEBHOOK] Payload recebido: {json.dumps(request.data, indent=2)}')
        
        # Extrai dados do payload da Evolution API
        payload = request.data
        
        # Valida estrutura básica do payload
        if 'data' not in payload:
            logger.warning('[WEBHOOK] Payload inválido: campo "data" não encontrado')
            return Response({'status': 'error', 'message': 'Payload inválido'}, status=400)
        
        data = payload.get('data', {})
        event = payload.get('event', '')
        
        # Processa apenas eventos de mensagem nova
        # Evolution API envia diferentes tipos de eventos, processamos apenas mensagens
        if event not in ['messages.upsert', 'messages.create']:
            logger.info(f'[WEBHOOK] Evento ignorado: {event}')
            return Response({'status': 'ignored', 'event': event}, status=200)
        
        # Extrai informações da mensagem
        participant = data.get('participant', '')
        message_obj = data.get('message', {})
        
        # Extrai texto da mensagem (pode estar em diferentes campos dependendo do tipo)
        text = None
        if 'conversation' in message_obj:
            text = message_obj['conversation']
        elif 'extendedTextMessage' in message_obj:
            text = message_obj['extendedTextMessage'].get('text', '')
        elif 'imageMessage' in message_obj:
            # Para imagens, extrai caption se houver
            text = message_obj['imageMessage'].get('caption', '')
        
        if not text or not text.strip():
            logger.warning('[WEBHOOK] Mensagem sem texto encontrada')
            return Response({'status': 'ignored', 'reason': 'no_text'}, status=200)
        
        # Extrai número do WhatsApp (JID sem @s.whatsapp.net)
        whatsapp_number = participant.split('@')[0] if '@' in participant else participant
        
        logger.info(f'[WEBHOOK] Mensagem de {whatsapp_number}: {text[:50]}...')
        
        # Busca usuário pelo número do WhatsApp
        try:
            user = User.objects.get(whatsapp_number=whatsapp_number, is_active=True)
            logger.info(f'[WEBHOOK] Usuário encontrado: {user.email}, Tenant: {user.tenant_id}')
        except User.DoesNotExist:
            logger.warning(f'[WEBHOOK] Usuário não encontrado ou inativo para número: {whatsapp_number}')
            return Response({
                'status': 'ignored',
                'reason': 'user_not_found'
            }, status=200)  # Responde 200 para não travar Evolution API
        
        except User.MultipleObjectsReturned:
            logger.error(f'[WEBHOOK] Múltiplos usuários encontrados para número: {whatsapp_number}')
            # Usa o primeiro usuário ativo
            user = User.objects.filter(whatsapp_number=whatsapp_number, is_active=True).first()
            if not user:
                return Response({'status': 'error'}, status=200)
        
        # Dispara task assíncrona para processar a mensagem
        try:
            task = process_incoming_message.delay(str(user.id), text)
            logger.info(f'[WEBHOOK] Task disparada: {task.id} para usuário {user.id}')
        except Exception as e:
            logger.error(f'[WEBHOOK] Erro ao disparar task: {str(e)}')
            # Não retorna erro - apenas loga, para não travar Evolution API
        
        # Responde 200 OK imediatamente (não espera processamento)
        return Response({
            'status': 'received',
            'message': 'Mensagem recebida e em processamento'
        }, status=200)
        
    except Exception as e:
        logger.error(f'[WEBHOOK] Erro inesperado: {str(e)}', exc_info=True)
        # Sempre retorna 200 para não travar Evolution API
        return Response({'status': 'error', 'message': str(e)}, status=200)


@api_view(['POST'])
@permission_classes([AllowAny])
@csrf_exempt
def evolution_buttons_webhook(request: HttpRequest) -> Response:
    """
    Webhook para receber callbacks de botões interativos da Evolution API.
    
    Endpoint: POST /api/v1/webhooks/evolution/buttons/
    
    Processa quando o usuário clica em [✅ Confirmar] ou [❌ Cancelar]
    nos botões enviados após o parsing da IA.
    
    Payload esperado:
    {
        "data": {
            "selectedButtonId": "confirm_{session_id}" ou "cancel_{session_id}",
            "participant": "5541999999999@s.whatsapp.net",
            ...
        }
    }
    
    Returns:
        Response 200 OK
    """
    try:
        logger.info('[WEBHOOK] Callback de botão recebido da Evolution API')
        logger.debug(f'[WEBHOOK] Payload: {json.dumps(request.data, indent=2)}')
        
        payload = request.data
        
        if 'data' not in payload:
            logger.warning('[WEBHOOK] Payload inválido para callback de botão')
            return Response({'status': 'error'}, status=400)
        
        data = payload.get('data', {})
        selected_button_id = data.get('selectedButtonId', '')
        participant = data.get('participant', '')
        
        # Extrai ação e session_id do button_id
        # Formato esperado: "confirm_{uuid}" ou "cancel_{uuid}"
        if not selected_button_id:
            logger.warning('[WEBHOOK] Button ID não encontrado no payload')
            return Response({'status': 'ignored'}, status=200)
        
        parts = selected_button_id.split('_', 1)
        if len(parts) != 2:
            logger.warning(f'[WEBHOOK] Formato de Button ID inválido: {selected_button_id}')
            return Response({'status': 'ignored'}, status=200)
        
        action = parts[0]  # "confirm" ou "cancel"
        session_id_str = parts[1]  # UUID da ParsingSession
        
        # Valida UUID
        try:
            session_id = UUID(session_id_str)
        except ValueError:
            logger.warning(f'[WEBHOOK] UUID inválido no Button ID: {session_id_str}')
            return Response({'status': 'ignored'}, status=200)
        
        # Busca usuário pelo número do WhatsApp
        whatsapp_number = participant.split('@')[0] if '@' in participant else participant
        
        try:
            user = User.objects.get(whatsapp_number=whatsapp_number, is_active=True)
        except User.DoesNotExist:
            logger.warning(f'[WEBHOOK] Usuário não encontrado: {whatsapp_number}')
            return Response({'status': 'ignored'}, status=200)
        
        # Busca ParsingSession
        try:
            parsing_session = ParsingSession.objects.get(id=session_id, tenant=user.tenant)
        except ParsingSession.DoesNotExist:
            logger.warning(f'[WEBHOOK] ParsingSession não encontrada: {session_id}')
            return Response({'status': 'ignored'}, status=200)
        
        # Define tenant no contexto
        set_current_tenant(user.tenant_id)
        
        try:
            if action == 'confirm':
                # Usuário confirmou - cria Transaction e Installment
                logger.info(f'[WEBHOOK] Confirmação recebida para session {session_id}')
                transaction = create_transaction_from_session(parsing_session, user)
                parsing_session.confirm(transaction)
                
                # Envia mensagem de confirmação
                from core.services.whatsapp_service import WhatsAppService
                whatsapp_service = WhatsAppService()
                whatsapp_service.send_text_message(
                    user.whatsapp_number,
                    "✅ *Transação confirmada e registrada com sucesso!*"
                )
                
            elif action == 'cancel':
                # Usuário cancelou
                logger.info(f'[WEBHOOK] Cancelamento recebido para session {session_id}')
                parsing_session.cancel()
                
                # Envia mensagem de cancelamento
                from core.services.whatsapp_service import WhatsAppService
                whatsapp_service = WhatsAppService()
                whatsapp_service.send_text_message(
                    user.whatsapp_number,
                    "❌ *Transação cancelada. Os dados não foram salvos.*"
                )
            else:
                logger.warning(f'[WEBHOOK] Ação desconhecida: {action}')
                return Response({'status': 'ignored'}, status=200)
                
        finally:
            clear_tenant()
        
        return Response({'status': 'processed', 'action': action}, status=200)
        
    except Exception as e:
        logger.error(f'[WEBHOOK] Erro ao processar callback de botão: {str(e)}', exc_info=True)
        return Response({'status': 'error'}, status=200)  # Sempre 200 para não travar Evolution API


def create_transaction_from_session(parsing_session: ParsingSession, user: User) -> Transaction:
    """
    Cria Transaction e Installment a partir de uma ParsingSession confirmada.
    
    Esta função implementa a lógica de negócio para criar os registros
    financeiros definitivos após confirmação do usuário.
    
    Args:
        parsing_session: ParsingSession confirmada
        user: Usuário que confirmou
        
    Returns:
        Transaction criada
        
    Raises:
        ValueError: Se dados da sessão forem inválidos
    """
    from datetime import date
    from decimal import Decimal
    
    extracted_data = parsing_session.extracted_json
    
    # Busca categoria e subcategoria (tenta globais primeiro, depois tenant)
    category_name = extracted_data.get('categoria_sugerida')
    subcategory_name = extracted_data.get('subcategoria_sugerida')
    
    if not category_name or not subcategory_name:
        raise ValueError('Categoria ou subcategoria não encontrada nos dados extraídos')
    
    # Busca categoria (global ou do tenant)
    try:
        category = Category.objects.filter(
            name=category_name,
            tenant__isnull=True
        ).first()
        
        if not category:
            category = Category.objects.get(
                name=category_name,
                tenant=user.tenant
            )
    except Category.DoesNotExist:
        raise ValueError(f'Categoria não encontrada: {category_name}')
    
    # Busca subcategoria
    try:
        subcategory = Subcategory.objects.filter(
            name=subcategory_name,
            category=category,
            tenant__isnull=True
        ).first()
        
        if not subcategory:
            subcategory = Subcategory.objects.get(
                name=subcategory_name,
                category=category,
                tenant=user.tenant
            )
    except Subcategory.DoesNotExist:
        raise ValueError(f'Subcategoria não encontrada: {subcategory_name}')
    
    # Parse das datas
    try:
        data_competencia = date.fromisoformat(extracted_data['data_competencia'])
        data_caixa = date.fromisoformat(extracted_data['data_caixa'])
    except (KeyError, ValueError) as e:
        raise ValueError(f'Data inválida nos dados extraídos: {str(e)}')
    
    # Cria Transaction (Competência - Fato Gerador)
    transaction = Transaction.objects.create(
        tenant=user.tenant,
        description=extracted_data.get('descricao', 'Transação sem descrição'),
        amount=Decimal(str(extracted_data['valor'])),
        category=category,
        subcategory=subcategory,
        competence_date=data_competencia,
        supplier=extracted_data.get('fornecedor')
    )
    
    # Cria Installment (Caixa - Movimentação Real)
    Installment.objects.create(
        tenant=user.tenant,
        transaction=transaction,
        due_date=data_caixa,  # Data de vencimento (mesma da data de caixa)
        payment_date=data_caixa,  # Data de pagamento (assume que já foi pago se chegou aqui)
        amount=Decimal(str(extracted_data['valor'])),
        penalty_amount=Decimal('0.00'),
        status='PAGO'  # Se confirmou, assume que já foi pago
    )
    
    logger.info(f'[WEBHOOK] Transaction criada: {transaction.id} com Installment')
    
    return transaction

