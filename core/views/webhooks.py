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
from core.models.finance import Category, Subcategory, InstallmentStatus
from core.tasks import process_incoming_message
from core.utils.tenant_context import set_current_tenant, clear_tenant
from core.services.whatsapp_service import WhatsAppService

logger = logging.getLogger(__name__)


@api_view(['POST'])
@permission_classes([AllowAny])
@csrf_exempt
def evolution_webhook(request: HttpRequest) -> Response:
    """
    Webhook para receber mensagens da Evolution API.
    
    Endpoint: POST /api/v1/webhooks/evolution/
    
    Valida se o remetente (número do WhatsApp) pertence a um usuário ativo
    e processa a mensagem conforme o tipo:
    - Mensagem normal: dispara task assíncrona para parsing com IA
    - Comando "Saldo" ou "Resumo": retorna resumo financeiro imediato
    - Resposta de botão/enquete: processa confirmação/cancelamento
    
    Responde 200 OK imediatamente para não travar a Evolution API.
    
    Payload esperado da Evolution API:
    {
        "data": {
            "key": {...},
            "message": {
                "conversation": "texto da mensagem",
                "buttonsResponseMessage": {...},  # Resposta de botão
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
        
        # Extrai número do WhatsApp (JID sem @s.whatsapp.net)
        whatsapp_number = participant.split('@')[0] if '@' in participant else participant
        
        # Busca usuário pelo número do WhatsApp
        try:
            user = User.objects.get(whatsapp_number=whatsapp_number, is_active=True)
            logger.info(f'[WEBHOOK] Usuário encontrado: {user.email}, Tenant: {user.tenant_id}')
        except User.DoesNotExist:
            logger.warning(f'[WEBHOOK] Usuário não encontrado ou inativo para número: {whatsapp_number}')
            return Response({
                'status': 'ignored',
                'reason': 'user_not_found'
            }, status=200)
        
        except User.MultipleObjectsReturned:
            logger.error(f'[WEBHOOK] Múltiplos usuários encontrados para número: {whatsapp_number}')
            user = User.objects.filter(whatsapp_number=whatsapp_number, is_active=True).first()
            if not user:
                return Response({'status': 'error'}, status=200)
        
        # Verifica se é resposta de botão/enquete
        if 'buttonsResponseMessage' in message_obj:
            # Processa resposta de botão diretamente (não dispara task)
            button_response = message_obj['buttonsResponseMessage']
            selected_button_id = button_response.get('selectedButtonId', '')
            
            logger.info(f'[WEBHOOK] Resposta de botão detectada: {selected_button_id}')
            
            # Processa callback de botão diretamente
            return handle_button_response(selected_button_id, user)
        
        # Extrai tipo de mídia e dados
        text = None
        image_url = None
        audio_url = None
        media_type = 'text'
        
        # Detecta tipo de mensagem e extrai dados
        if 'conversation' in message_obj:
            text = message_obj['conversation']
            media_type = 'text'
        elif 'extendedTextMessage' in message_obj:
            text = message_obj['extendedTextMessage'].get('text', '')
            media_type = 'text'
        elif 'imageMessage' in message_obj:
            # Mensagem com imagem (comprovante/nota fiscal)
            image_msg = message_obj['imageMessage']
            text = image_msg.get('caption', '')  # Caption opcional
            # Extrai URL da imagem da Evolution API
            image_url = image_msg.get('url') or image_msg.get('directPath')
            # Se não houver URL, tenta obter do contexto (Evolution API às vezes envia assim)
            if not image_url and 'key' in data:
                # Constrói URL da Evolution API para download
                from django.conf import settings
                evolution_api_url = getattr(settings, 'EVOLUTION_API_URL', 'http://localhost:8080')
                instance_name = getattr(settings, 'EVOLUTION_INSTANCE_NAME', 'caixo_instance')
                media_id = image_msg.get('id') or data.get('key', {}).get('id')
                if media_id:
                    image_url = f"{evolution_api_url}/message/downloadMedia/{instance_name}/{media_id}"
            media_type = 'image'
            logger.info(f'[WEBHOOK] Imagem detectada: {image_url}')
        elif 'audioMessage' in message_obj or 'pttMessage' in message_obj:
            # Mensagem de áudio (voice message)
            audio_msg = message_obj.get('audioMessage') or message_obj.get('pttMessage', {})
            # Extrai URL do áudio da Evolution API
            audio_url = audio_msg.get('url') or audio_msg.get('directPath')
            # Se não houver URL, tenta obter do contexto
            if not audio_url and 'key' in data:
                from django.conf import settings
                evolution_api_url = getattr(settings, 'EVOLUTION_API_URL', 'http://localhost:8080')
                instance_name = getattr(settings, 'EVOLUTION_INSTANCE_NAME', 'caixo_instance')
                media_id = audio_msg.get('id') or data.get('key', {}).get('id')
                if media_id:
                    audio_url = f"{evolution_api_url}/message/downloadMedia/{instance_name}/{media_id}"
            media_type = 'audio'
            text = ""  # Texto será gerado pela transcrição
            logger.info(f'[WEBHOOK] Áudio detectado: {audio_url}')
        elif 'videoMessage' in message_obj:
            # Vídeo pode ter caption
            text = message_obj['videoMessage'].get('caption', '')
            media_type = 'video'
            logger.info('[WEBHOOK] Vídeo detectado (não suportado, usando apenas caption)')
        
        # Valida que há conteúdo para processar
        if not text and not image_url and not audio_url:
            logger.warning('[WEBHOOK] Mensagem sem conteúdo processável encontrada')
            return Response({'status': 'ignored', 'reason': 'no_content'}, status=200)
        
        text = text.strip() if text else ""
        
        logger.info(f'[WEBHOOK] Mensagem de {whatsapp_number} (tipo: {media_type}): {text[:50] if text else "sem texto"}...')
        
        # Verifica se é comando de saldo/resumo (apenas se for texto)
        if text and text.upper() in ['SALDO', 'RESUMO', 'SALDO ATUAL', 'RESUMO FINANCEIRO']:
            logger.info(f'[WEBHOOK] Comando de saldo/resumo detectado')
            return handle_balance_request(user)
        
        # Dispara task assíncrona para processar a mensagem com IA
        # Passa imagem/áudio se houver
        try:
            task = process_incoming_message.delay(
                str(user.id),
                text or "",
                image_url=image_url,
                audio_url=audio_url
            )
            logger.info(f'[WEBHOOK] Task disparada: {task.id} para usuário {user.id} (tipo: {media_type})')
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


def handle_button_response(selected_button_id: str, user: User) -> Response:
    """
    Processa resposta de botão/enquete da Evolution API.
    
    Extrai o session_id e a ação (confirm/cancel) do button_id
    e processa a confirmação ou cancelamento da ParsingSession.
    
    Args:
        selected_button_id: ID do botão selecionado (formato: "confirm_{uuid}" ou "cancel_{uuid}")
        user: Usuário que clicou no botão
        
    Returns:
        Response 200 OK
    """
    try:
        # Extrai ação e session_id do button_id
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
        
        # Busca ParsingSession e valida que pertence ao usuário
        try:
            parsing_session = ParsingSession.objects.get(id=session_id, tenant=user.tenant)
        except ParsingSession.DoesNotExist:
            logger.warning(f'[WEBHOOK] ParsingSession não encontrada: {session_id}')
            return Response({'status': 'ignored'}, status=200)
        
        # Valida que a sessão ainda está pendente
        if parsing_session.status != ParsingSessionStatus.PENDING:
            logger.warning(
                f'[WEBHOOK] ParsingSession {session_id} já foi processada (status: {parsing_session.status})'
            )
            return Response({'status': 'ignored', 'reason': 'already_processed'}, status=200)
        
        # Define tenant no contexto
        set_current_tenant(user.tenant_id)
        
        try:
            
            if action == 'confirm':
                # Usuário confirmou - cria Transaction e Installment
                logger.info(f'[WEBHOOK] [CONFIRMAÇÃO] Iniciando processo de persistência para session {session_id}')
                
                # Cria Transaction e Installment de forma transacional
                transaction = create_transaction_from_session(parsing_session, user)
                
                # Atualiza status da sessão para CONFIRMED
                parsing_session.confirm(transaction)
                
                # Log crítico: momento em que dinheiro "entra no sistema"
                logger.info(
                    f'[WEBHOOK] [CONFIRMAÇÃO] ✅ LANÇAMENTO OFICIALIZADO! '
                    f'Session {session_id} -> Transaction {transaction.id} -> Installment criado. '
                    f'Valor: R$ {transaction.amount}, Competência: {transaction.competence_date}'
                )
                
                # APRENDIZADO AUTOMÁTICO: Cria/atualiza LearnedRule se fornecedor existir
                # Se a subcategoria confirmada pelo usuário for diferente da sugerida inicialmente,
                # ou se houver fornecedor, cria/atualiza uma regra aprendida
                try:
                    from core.models.finance import LearnedRule
                    extracted_data = parsing_session.extracted_json
                    fornecedor = extracted_data.get('fornecedor') or transaction.supplier
                    
                    # Subcategoria sugerida inicialmente pela IA
                    subcategoria_sugerida_inicial = extracted_data.get('subcategoria_sugerida', '')
                    
                    # Subcategoria confirmada (final)
                    subcategoria_confirmada = transaction.subcategory.name
                    
                    # Se houver fornecedor e a subcategoria confirmada for diferente da sugerida inicialmente,
                    # cria/atualiza LearnedRule para aprender com o feedback do usuário
                    if fornecedor and fornecedor.strip():
                        keyword = fornecedor.strip().lower()
                        
                        # Busca regra existente para este fornecedor
                        learned_rule, created = LearnedRule.objects.get_or_create(
                            tenant=user.tenant,
                            keyword=keyword,
                            defaults={
                                'category': transaction.category,
                                'subcategory': transaction.subcategory,
                                'active': True,
                                'hit_count': 0
                            }
                        )
                        
                        if not created:
                            # Regra já existia - atualiza categoria/subcategoria e incrementa hit_count
                            learned_rule.category = transaction.category
                            learned_rule.subcategory = transaction.subcategory
                            learned_rule.hit_count += 1
                            learned_rule.active = True
                            learned_rule.save()
                            logger.info(
                                f'[APRENDIZADO] LearnedRule atualizada para "{keyword}": '
                                f'{transaction.category.name} -> {transaction.subcategory.name} '
                                f'(hit_count: {learned_rule.hit_count})'
                            )
                        else:
                            # Nova regra criada
                            learned_rule.hit_count = 1
                            learned_rule.save()
                            logger.info(
                                f'[APRENDIZADO] Nova LearnedRule criada para "{keyword}": '
                                f'{transaction.category.name} -> {transaction.subcategory.name}'
                            )
                        
                        # Se a subcategoria confirmada for diferente da sugerida inicialmente,
                        # isso indica que o usuário corrigiu a categorização
                        if subcategoria_sugerida_inicial and subcategoria_confirmada != subcategoria_sugerida_inicial:
                            logger.info(
                                f'[APRENDIZADO] Usuário corrigiu categorização: '
                                f'Sugerida: {subcategoria_sugerida_inicial} -> '
                                f'Confirmada: {subcategoria_confirmada}. '
                                f'Regra aprendida para "{keyword}".'
                            )
                except Exception as e:
                    logger.error(f'[APRENDIZADO] Erro ao criar/atualizar LearnedRule: {str(e)}')
                    # Não interrompe o fluxo - apenas loga o erro
                
                # Envia mensagem de sucesso com detalhes
                valor_str = f"R$ {transaction.amount:,.2f}".replace(',', 'X').replace('.', ',').replace('X', '.')
                success_message = f"""✅ *Lançamento de {valor_str} confirmado com sucesso!* 🚀

📝 {transaction.description}
📊 Competência: {transaction.competence_date.strftime('%m/%Y')}
🏷️ {transaction.category.name} - {transaction.subcategory.name}

Transação registrada no sistema."""
                
                whatsapp_service = WhatsAppService()
                whatsapp_service.send_text_message(user.whatsapp_number, success_message)
                
            elif action == 'cancel':
                # Usuário cancelou
                logger.info(f'[WEBHOOK] [CANCELAMENTO] Session {session_id} cancelada pelo usuário')
                parsing_session.cancel()
                
                # Envia mensagem de cancelamento
                whatsapp_service.send_text_message(
                    user.whatsapp_number,
                    "❌ *Lançamento descartado. Se precisar, é só mandar de novo!*"
                )
            else:
                logger.warning(f'[WEBHOOK] Ação desconhecida: {action}')
                return Response({'status': 'ignored'}, status=200)
                
        finally:
            clear_tenant()
        
        return Response({'status': 'processed', 'action': action}, status=200)
        
    except Exception as e:
        logger.error(f'[WEBHOOK] Erro ao processar resposta de botão: {str(e)}', exc_info=True)
        clear_tenant()
        return Response({'status': 'error'}, status=200)


def handle_balance_request(user: User) -> Response:
    """
    Processa comando de saldo/resumo financeiro.
    
    Retorna resumo financeiro do mês atual com entradas e saídas confirmadas.
    
    Args:
        user: Usuário que solicitou o resumo
        
    Returns:
        Response 200 OK (envia mensagem via WhatsApp)
    """
    try:
        from datetime import date
        from decimal import Decimal
        from django.db.models import Sum, Q
        
        # Define tenant no contexto
        set_current_tenant(user.tenant_id)
        
        try:
            # Busca Installments do mês atual com status PAGO
            today = date.today()
            first_day_month = date(today.year, today.month, 1)
            last_day_month = date(today.year, today.month + 1, 1) if today.month < 12 else date(today.year + 1, 1, 1)
            
            # Total de saídas (Installments pagos no mês atual)
            # Considera apenas Installments vinculados a Transactions do tenant
            from core.models.finance import Installment, InstallmentStatus
            
            # Total de saídas (Installments pagos no mês atual)
            # Considera apenas Installments vinculados a Transactions do tenant
            # Calcula total usando F() expressions para somar amount + penalty_amount
            from django.db.models import F
            
            saidas_query = Installment.objects.filter(
                tenant=user.tenant,
                status=InstallmentStatus.PAGO,
                payment_date__gte=first_day_month,
                payment_date__lt=last_day_month
            )
            
            # Calcula total usando annotation e Sum
            saidas_result = saidas_query.aggregate(
                total=Sum(F('amount') + F('penalty_amount'))
            )
            saidas = saidas_result['total'] or Decimal('0.00')
            
            # Total de entradas (será implementado quando houver receitas)
            # Por enquanto, apenas despesas são implementadas
            entradas = Decimal('0.00')
            
            # Saldo atual (entradas - saídas)
            saldo = entradas - saidas
            
            # Formata valores
            entradas_str = f"R$ {entradas:,.2f}".replace(',', 'X').replace('.', ',').replace('X', '.')
            saidas_str = f"R$ {saidas:,.2f}".replace(',', 'X').replace('.', ',').replace('X', '.')
            saldo_str = f"R$ {saldo:,.2f}".replace(',', 'X').replace('.', ',').replace('X', '.')
            
            # Monta mensagem de resumo
            summary_message = f"""📊 *Resumo Financeiro - {today.strftime('%m/%Y')}*

💰 *Entradas:* {entradas_str}
💸 *Saídas:* {saidas_str}
━━━━━━━━━━━━━━━━
📈 *Saldo:* {saldo_str}

*Nota:* Apenas lançamentos confirmados estão incluídos."""
            
            # Envia mensagem via WhatsApp
            whatsapp_service = WhatsAppService()
            whatsapp_service.send_text_message(user.whatsapp_number, summary_message)
            
            logger.info(f'[WEBHOOK] Resumo financeiro enviado para {user.email}')
            
        finally:
            clear_tenant()
        
        return Response({'status': 'processed', 'command': 'balance'}, status=200)
        
    except Exception as e:
        logger.error(f'[WEBHOOK] Erro ao processar comando de saldo: {str(e)}', exc_info=True)
        clear_tenant()
        return Response({'status': 'error'}, status=200)


def create_transaction_from_session(parsing_session: ParsingSession, user: User) -> Transaction:
    """
    Cria Transaction e Installment a partir de uma ParsingSession confirmada.
    
    Esta função implementa a lógica de negócio para criar os registros
    financeiros definitivos após confirmação do usuário. É o MOMENTO CRÍTICO
    onde o dinheiro "entra no sistema" de forma oficial.
    
    Utiliza transaction.atomic() para garantir que ou cria tudo ou não cria nada,
    mantendo a integridade dos dados financeiros.
    
    Se a IA detectou que o pagamento já foi realizado (ex: "Paguei hoje"),
    marca automaticamente a Installment como PAGO usando mark_as_paid().
    
    Args:
        parsing_session: ParsingSession confirmada pelo usuário
        user: Usuário que confirmou (deve ser o mesmo que originou a sessão)
        
    Returns:
        Transaction criada com Installment vinculado
        
    Raises:
        ValueError: Se dados da sessão forem inválidos
        ValidationError: Se validações do modelo falharem
    """
    from datetime import date
    from decimal import Decimal, InvalidOperation
    from django.db import transaction as db_transaction
    from django.core.exceptions import ValidationError
    from core.models.finance import InstallmentStatus
    
    # Valida que o usuário que está confirmando é o mesmo que originou a sessão
    # (Segurança adicional - parsing_session já foi validada no handle_button_response)
    
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
        data_competencia_str = extracted_data.get('data_competencia')
        data_caixa_str = extracted_data.get('data_caixa')
        
        if not data_competencia_str or not data_caixa_str:
            raise ValueError('Datas de competência ou caixa não encontradas nos dados extraídos')
        
        data_competencia = date.fromisoformat(data_competencia_str)
        data_caixa = date.fromisoformat(data_caixa_str)
    except (KeyError, ValueError) as e:
        raise ValueError(f'Data inválida nos dados extraídos: {str(e)}')
    
    # Parse do valor
    try:
        valor = Decimal(str(extracted_data['valor']))
        if valor <= Decimal('0.00'):
            raise ValueError('Valor da transação deve ser maior que zero')
    except (KeyError, ValueError, InvalidOperation) as e:
        raise ValueError(f'Valor inválido nos dados extraídos: {str(e)}')
    
    # Verifica se pagamento já foi realizado (IA detectou "paguei hoje", "já paguei", etc.)
    pagamento_realizado = extracted_data.get('pagamento_realizado', False)
    valor_pago = extracted_data.get('valor_pago', None)
    
    # Cria Transaction e Installment de forma TRANSA confidenceional
    # Garante que ou cria tudo ou não cria nada (ACID)
    with db_transaction.atomic():
        # Cria Transaction (Competência - Fato Gerador para DRE)
        fornecedor = extracted_data.get('fornecedor')
        transaction = Transaction.objects.create(
            tenant=user.tenant,
            description=extracted_data.get('descricao', 'Transação sem descrição'),
            amount=valor,
            category=category,
            subcategory=subcategory,
            competence_date=data_competencia,
            supplier=fornecedor if fornecedor else None  # None em vez de string vazia
        )
        
        logger.info(
            f'[PERSISTÊNCIA] Transaction {transaction.id} criada: '
            f'R$ {valor} - {transaction.description} - Competência: {data_competencia}'
        )
        
        # Cria Installment (Caixa - Movimentação Real para Fluxo de Caixa)
        installment = Installment.objects.create(
            tenant=user.tenant,
            transaction=transaction,
            due_date=data_caixa,  # Data de vencimento
            amount=valor,  # Valor líquido
            penalty_amount=Decimal('0.00'),  # Inicializa sem multas
            status=InstallmentStatus.PENDENTE  # Inicialmente pendente
        )
        
        # Se a IA detectou que pagamento já foi realizado, marca como pago automaticamente
        if pagamento_realizado:
            # Determina data de pagamento (usa data_caixa ou hoje se não especificado)
            payment_date = data_caixa if data_caixa <= date.today() else date.today()
            
            # Determina valor pago (usa valor_pago se fornecido, senão usa valor original)
            paid_amount = Decimal(str(valor_pago)) if valor_pago else valor
            
            # Marca como pago usando o método mark_as_paid (calcula multas automaticamente)
            installment.mark_as_paid(payment_date=payment_date, paid_amount=paid_amount)
            
            logger.info(
                f'[PERSISTÊNCIA] Installment {installment.id} marcado automaticamente como PAGO: '
                f'Data: {payment_date}, Valor pago: R$ {paid_amount}, Multas: R$ {installment.penalty_amount}'
            )
        else:
            # Pagamento não realizado - deixa como PENDENTE
            logger.info(
                f'[PERSISTÊNCIA] Installment {installment.id} criado como PENDENTE: '
                f'Vencimento: {data_caixa}'
            )
        
        # Log crítico: momento em que dinheiro "entra no sistema" de forma oficial
        logger.info(
            f'[PERSISTÊNCIA] ✅ LANÇAMENTO OFICIALIZADO! '
            f'Session {parsing_session.id} -> Transaction {transaction.id} -> Installment {installment.id} '
            f'(Status: {installment.status}, Valor: R$ {valor})'
        )
        
        return transaction

