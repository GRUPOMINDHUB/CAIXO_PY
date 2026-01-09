"""
Tasks assíncronas do Celery para processamento de mensagens.

Define as tasks que serão executadas em background para processar
mensagens recebidas via WhatsApp, utilizando IA para extração de dados
e salvamento em ParsingSession.

Características:
- Processamento assíncrono para não travar o webhook
- Isolamento automático por tenant via set_current_tenant
- Logs detalhados de cada etapa
- Tratamento robusto de erros
"""

import logging
from typing import Optional
from uuid import UUID
from datetime import timedelta

from django.utils import timezone

# Importa Celery
from celery import shared_task

from core.models import User
from core.models.finance import (
    Category, Subcategory, ParsingSession, ParsingSessionStatus
)
from core.services.ia_processor import IAProcessor
from core.services.whatsapp_service import WhatsAppService
from core.utils.tenant_context import set_current_tenant, clear_tenant

logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=3)
def process_incoming_message(
    self,
    user_id: UUID,
    text: str,
    image_url: Optional[str] = None,
    audio_url: Optional[str] = None
) -> Optional[UUID]:
    """
    Task assíncrona para processar mensagem recebida via WhatsApp.
    
    Suporta mensagens de texto, imagens (comprovantes/notas fiscais) e áudio (voz).
    
    Fluxo de execução:
    1. Recupera o usuário e define o tenant no contexto
    2. Transcreve áudio se houver (Whisper API)
    3. Busca categorias globais e LearnedRules do tenant
    4. Processa a mensagem/imagem com IA (IAProcessor multimodal)
    5. Baixa e armazena imagem localmente (se houver)
    6. Salva resultado em ParsingSession
    7. Envia card de confirmação via WhatsApp
    
    Args:
        user_id: UUID do usuário que enviou a mensagem
        text: Texto da mensagem recebida ou caption da imagem
        image_url: URL da imagem (comprovante/nota fiscal) - opcional
        audio_url: URL do áudio (mensagem de voz) - opcional
        
    Returns:
        UUID da ParsingSession criada ou None em caso de erro
        
    Raises:
        Exception: Se houver erro crítico (retry automático até 3 vezes)
    """
    parsing_session_id = None
    
    try:
        logger.info(f'[TASK] Iniciando processamento de mensagem. User: {user_id}, Text: {text[:50]}...')
        
        # Passo 1: Recupera o usuário e define o tenant no contexto
        try:
            user = User.objects.get(id=user_id)
            logger.info(f'[TASK] Usuário encontrado: {user.email}, Tenant: {user.tenant_id}')
        except User.DoesNotExist:
            logger.error(f'[TASK] Usuário não encontrado: {user_id}')
            return None
        
        # Define o tenant no contexto thread-local para isolamento automático
        if user.tenant_id:
            set_current_tenant(user.tenant_id)
            logger.info(f'[TASK] Tenant definido no contexto: {user.tenant_id}')
        else:
            logger.warning(f'[TASK] Usuário {user.email} não possui tenant associado')
            clear_tenant()
            return None
        
        # Passo 2: Transcreve áudio se houver (antes de processar com IA)
        transcribed_text = text
        if audio_url:
            try:
                logger.info(f'[TASK] Transcrevendo áudio de: {audio_url}')
                ia_processor = IAProcessor()
                transcribed_text = ia_processor.transcribe_audio(audio_url)
                logger.info(f'[TASK] Áudio transcrito: {transcribed_text[:100]}...')
                
                # Se não houver texto original, usa a transcrição
                if not text.strip():
                    text = transcribed_text
            except ValueError as e:
                logger.error(f'[TASK] Erro ao transcrever áudio: {str(e)}')
                # Envia mensagem de erro ao usuário
                whatsapp_service = WhatsAppService()
                whatsapp_jid = user.whatsapp_number
                if whatsapp_jid:
                    error_msg = "Não consegui entender o áudio. Pode enviar novamente ou escrever o texto?"
                    whatsapp_service.send_text_message(whatsapp_jid, error_msg)
                return None
        
        # Passo 3: Busca categorias globais e LearnedRules do tenant
        try:
            categories_context = get_categories_for_ia(user.tenant_id)
            logger.info(f'[TASK] {len(categories_context)} categorias carregadas para contexto da IA')
            
            # Busca LearnedRules (regras aprendidas) do tenant
            from core.models.finance import LearnedRule
            learned_rules = LearnedRule.objects.filter(
                tenant=user.tenant,
                active=True
            ).select_related('category', 'subcategory').values(
                'keyword', 'category__name', 'subcategory__name'
            )
            
            # Converte para formato esperado pelo IAProcessor
            learned_rules_list = []
            for rule in learned_rules:
                learned_rules_list.append({
                    'keyword': rule['keyword'],
                    'category': rule['category__name'],
                    'subcategory': rule['subcategory__name']
                })
            
            logger.info(f'[TASK] {len(learned_rules_list)} LearnedRules encontradas para melhorar categorização')
        except Exception as e:
            logger.error(f'[TASK] Erro ao buscar categorias/LearnedRules: {str(e)}')
            raise
        
        # Passo 4: Processa a mensagem/imagem com IA (multimodal se houver imagem)
        try:
            ia_processor = IAProcessor()
            
            # Baixa imagem e converte para base64 se houver
            image_base64 = None
            if image_url:
                try:
                    import requests
                    import base64
                    from io import BytesIO
                    
                    logger.info(f'[TASK] Baixando imagem de: {image_url}')
                    img_response = requests.get(image_url, timeout=30)
                    img_response.raise_for_status()
                    
                    # Converte para base64
                    image_base64 = base64.b64encode(img_response.content).decode('utf-8')
                    logger.info(f'[TASK] Imagem baixada e convertida para base64 ({len(image_base64)} caracteres)')
                except Exception as e:
                    logger.error(f'[TASK] Erro ao baixar imagem: {str(e)}')
                    # Continua sem imagem, mas loga o erro
            
            extracted_data = ia_processor.parse_financial_message(
                text=transcribed_text if transcribed_text else text,
                context_categories=categories_context,
                image_url=image_url if not image_base64 else None,  # Usa URL se não conseguiu baixar
                image_base64=image_base64,
                learned_rules=learned_rules_list if learned_rules_list else None
            )
            logger.info(f'[TASK] Dados extraídos pela IA: {extracted_data}')
        except ValueError as e:
            # Erro na IA - envia mensagem de erro ao usuário
            logger.error(f'[TASK] Erro no parsing pela IA: {str(e)}')
            whatsapp_service = WhatsAppService()
            whatsapp_jid = user.whatsapp_number
            if whatsapp_jid:
                error_msg = "Não consegui entender os dados. Pode enviar novamente de forma mais clara?"
                whatsapp_service.send_error_message(whatsapp_jid, error_msg)
            return None
        except Exception as e:
            logger.error(f'[TASK] Erro inesperado no IAProcessor: {str(e)}')
            raise
        
        # Passo 5: Salva resultado em ParsingSession
        try:
            # Cria ParsingSession com os dados extraídos
            expires_at = timezone.now() + timedelta(hours=24)  # Expira em 24 horas
            
            # Determina texto final (transcrito ou original)
            final_text = transcribed_text if transcribed_text and transcribed_text != text else text
            
            parsing_session = ParsingSession(
                tenant=user.tenant,
                raw_text=final_text,
                extracted_json=extracted_data,
                status=ParsingSessionStatus.PENDING,
                expires_at=expires_at,
                image_url=image_url if image_url else None,
                audio_url=audio_url if audio_url else None
            )
            
            # Salva para obter o ID
            parsing_session.save()
            
            # Baixa e armazena arquivo de imagem localmente (se houver)
            if image_url and image_base64:
                try:
                    import requests
                    from django.core.files.base import ContentFile
                    
                    img_response = requests.get(image_url, timeout=30)
                    img_response.raise_for_status()
                    
                    # Determina extensão baseada no Content-Type
                    content_type = img_response.headers.get('Content-Type', 'image/jpeg')
                    extension = 'jpg'
                    if 'png' in content_type:
                        extension = 'png'
                    elif 'pdf' in content_type:
                        extension = 'pdf'
                    
                    # Salva o arquivo usando upload_to (invoice_upload_path)
                    image_content = ContentFile(img_response.content)
                    parsing_session.image_file.save(
                        f"{parsing_session.id}.{extension}",
                        image_content
                    )
                    parsing_session.save()
                    logger.info(f'[TASK] Imagem armazenada em: {parsing_session.image_file.path}')
                except Exception as e:
                    logger.error(f'[TASK] Erro ao baixar/salvar arquivo de imagem: {str(e)}')
                    # Continua sem arquivo, mas mantém URL
            
            parsing_session_id = parsing_session.id
            logger.info(f'[TASK] ParsingSession criada: {parsing_session_id}')
        except Exception as e:
            logger.error(f'[TASK] Erro ao criar ParsingSession: {str(e)}')
            raise
        
        # Passo 5: Envia card de confirmação via WhatsApp
        try:
            whatsapp_service = WhatsAppService()
            whatsapp_jid = user.whatsapp_number
            
            if not whatsapp_jid:
                logger.warning(f'[TASK] Usuário {user.email} não possui WhatsApp JID configurado')
                return parsing_session_id
            
            # Formata resumo da transação extraída
            summary_text = format_extraction_summary(extracted_data)
            
            # Envia mensagem com botões de confirmação
            success = whatsapp_service.send_confirmation_buttons(
                to_jid=whatsapp_jid,
                session_id=parsing_session_id,
                summary_text=summary_text
            )
            
            if success:
                logger.info(f'[TASK] Card de confirmação enviado com sucesso para {whatsapp_jid}')
            else:
                logger.error(f'[TASK] Falha ao enviar card de confirmação para {whatsapp_jid}')
        
        except Exception as e:
            logger.error(f'[TASK] Erro ao enviar card de confirmação: {str(e)}')
            # Não levanta exceção - a ParsingSession já foi criada, pode ser confirmada depois
        
        logger.info(f'[TASK] Processamento concluído com sucesso. Session ID: {parsing_session_id}')
        return parsing_session_id
        
    except Exception as e:
        logger.error(f'[TASK] Erro crítico no processamento: {str(e)}', exc_info=True)
        # Limpa o contexto mesmo em caso de erro
        clear_tenant()
        
        # Retry automático (até 3 vezes, configurado no decorador @shared_task)
        # Se for última tentativa, não faz retry
        if self.request.retries < self.max_retries:
            raise self.retry(exc=e, countdown=60)  # Retry após 60 segundos
        else:
            logger.error(f'[TASK] Máximo de tentativas excedido. Task falhou definitivamente.')
            raise
    
    finally:
        # Garante que o contexto seja sempre limpo
        clear_tenant()


def get_categories_for_ia(tenant_id: Optional[UUID]) -> list:
    """
    Busca categorias globais e do tenant para contexto da IA.
    
    Retorna lista de dicionários com categoria e subcategoria
    formatadas para inclusão no prompt da IA.
    
    Usa select_related e prefetch_related para otimizar queries.
    
    Args:
        tenant_id: UUID do tenant (None para buscar apenas globais)
        
    Returns:
        Lista de dicionários: [{'category': '...', 'subcategory': '...'}, ...]
    """
    categories_list = []
    
    # Busca categorias globais (tenant=None) com otimização de queries
    global_categories = Category.objects.filter(
        tenant__isnull=True
    ).prefetch_related('subcategories').all()
    
    for category in global_categories:
        # Usa prefetch_related para evitar queries N+1
        subcategories = category.subcategories.filter(tenant__isnull=True)
        
        for subcategory in subcategories:
            categories_list.append({
                'category': category.name,
                'subcategory': subcategory.name
            })
    
    # Busca categorias do tenant (se houver)
    if tenant_id:
        tenant_categories = Category.objects.filter(
            tenant_id=tenant_id
        ).prefetch_related('subcategories').all()
        
        for category in tenant_categories:
            subcategories = category.subcategories.filter(tenant_id=tenant_id)
            
            for subcategory in subcategories:
                categories_list.append({
                    'category': category.name,
                    'subcategory': subcategory.name
                })
    
    logger.debug(f'Categorias carregadas para IA: {len(categories_list)} itens')
    
    return categories_list


def format_extraction_summary(extracted_data: dict) -> str:
    """
    Formata os dados extraídos pela IA em um resumo legível para o usuário.
    
    Se a confiança for baixa (< 0.8), adiciona um aviso para o usuário conferir
    a categorização sugerida.
    
    Args:
        extracted_data: Dicionário com dados extraídos pela IA
        
    Returns:
        String formatada com resumo da transação
    """
    from decimal import Decimal
    
    valor = extracted_data.get('valor', Decimal('0.00'))
    # Converte para Decimal se for string
    if isinstance(valor, str):
        valor = Decimal(valor)
    elif not isinstance(valor, Decimal):
        valor = Decimal(str(valor))
    
    descricao = extracted_data.get('descricao', 'N/A')
    data_caixa = extracted_data.get('data_caixa', 'N/A')
    data_competencia = extracted_data.get('data_competencia', 'N/A')
    categoria = extracted_data.get('categoria_sugerida', 'N/A')
    subcategoria = extracted_data.get('subcategoria_sugerida', 'N/A')
    fornecedor = extracted_data.get('fornecedor')
    confianca = extracted_data.get('confianca', 0.8)
    aviso_categoria = extracted_data.get('aviso_categoria')
    pagamento_realizado = extracted_data.get('pagamento_realizado', False)
    
    # Formata valor em formato brasileiro (R$ 500,00)
    valor_str = f"R$ {valor:,.2f}".replace(',', 'X').replace('.', ',').replace('X', '.')
    
    summary = f"""💰 *Valor:* {valor_str}
📝 *Descrição:* {descricao}
📅 *Data de Pagamento:* {data_caixa}
📊 *Data de Competência:* {data_competencia}
🏷️ *Categoria:* {categoria}
📌 *Subcategoria:* {subcategoria}"""
    
    if fornecedor:
        summary += f"\n🏢 *Fornecedor:* {fornecedor}"
    
    # Adiciona aviso se confiança for baixa
    if confianca < 0.8 and aviso_categoria:
        summary += f"\n\n⚠️ *Aviso:* {aviso_categoria}\nPor favor, confira se a categoria está correta!"
    elif confianca < 0.8:
        summary += f"\n\n⚠️ *Atenção:* Não tenho 100% de certeza sobre a categorização. Por favor, confira!"
    
    # Adiciona informação sobre pagamento realizado
    if pagamento_realizado:
        summary += f"\n✅ *Pagamento já realizado*"
        valor_pago = extracted_data.get('valor_pago')
        if valor_pago and valor_pago != float(valor):
            valor_pago_str = f"R$ {valor_pago:,.2f}".replace(',', 'X').replace('.', ',').replace('X', '.')
            summary += f" (Valor pago: {valor_pago_str})"
    
    return summary

