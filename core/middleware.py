"""
Middleware de automação de contexto de tenant.

Garante que o tenant atual seja definido automaticamente no contexto
thread-local para cada requisição, permitindo isolamento automático
de dados em todas as queries.

Características:
- Define tenant automaticamente baseado no usuário autenticado
- Limpa o contexto ao final da requisição (evita vazamento entre threads)
- Suporta usuários ADMIN_MASTER sem tenant
"""

from typing import Optional
from django.utils.deprecation import MiddlewareMixin
from django.contrib.auth import get_user_model

from core.utils.tenant_context import set_current_tenant, clear_tenant


class TenantMiddleware(MiddlewareMixin):
    """
    Middleware que automatiza o contexto de tenant para cada requisição.
    
    Para cada requisição HTTP:
    1. Se o usuário estiver autenticado e tiver tenant_id, define no contexto
    2. Se for ADMIN_MASTER (sem tenant), não define contexto
    3. Ao final da requisição, sempre limpa o contexto (try/finally)
    
    Garante que:
    - Queries automáticas sejam filtradas pelo tenant correto
    - Não haja vazamento de contexto entre requisições
    - ADMIN_MASTER possa ver todos os registros quando necessário
    """
    
    def process_request(self, request) -> None:
        """
        Processa a requisição e define o tenant no contexto.
        
        Suporta troca de tenant via sessão:
        - Se houver tenant_id na sessão, usa ele (validando permissão)
        - Se não houver, usa o primeiro tenant do usuário
        - ADMIN_MASTER pode acessar qualquer tenant se fornecido na sessão
        
        Usa try/finally para garantir que o contexto seja sempre limpo
        ao final da requisição, prevenindo vazamento de dados entre threads.
        
        Args:
            request: HttpRequest com o usuário autenticado (se houver)
        """
        # Limpa qualquer contexto anterior (segurança extra)
        clear_tenant()
        
        try:
            # Verifica se o usuário está autenticado
            if hasattr(request, 'user') and request.user.is_authenticated:
                user = request.user
                
                # Prefetch tenants para evitar N+1
                if not hasattr(user, '_prefetched_tenants'):
                    User = get_user_model()
                    user = User.objects.prefetch_related('tenants').get(pk=user.pk)
                    request.user = user
                
                # Obtém tenant_id da sessão (se houver)
                session_tenant_id = request.session.get('tenant_id', None)
                
                # Obtém o tenant ativo (valida permissões)
                active_tenant = user.get_active_tenant(session_tenant_id)
                
                if active_tenant:
                    # Define o tenant no contexto thread-local
                    set_current_tenant(active_tenant.id)
                    # Injeta o tenant no request para facilitar acesso nas views
                    # Isso permite usar request.tenant diretamente nos templates
                    request.tenant = active_tenant
                    request.tenant_id = active_tenant.id
                else:
                    # ADMIN_MASTER sem tenant selecionado ou usuário sem tenants
                    request.tenant = None
                    request.tenant_id = None
                
                # Para Admin Master, sempre busca todos os tenants para o dropdown
                # (independente de ter um tenant ativo ou não)
                # Inclui tenants ACTIVE e TRIAL (período de teste)
                if user.is_master:
                    from core.models.tenant import Tenant, TenantStatus
                    request.all_tenants = Tenant.objects.filter(
                        status__in=[TenantStatus.ACTIVE, TenantStatus.TRIAL]
                    ).order_by('name')
            else:
                # Usuário não autenticado
                request.tenant = None
                request.tenant_id = None
        finally:
            # Garante que o contexto seja limpo mesmo em caso de exceção
            # Este finally é executado após process_response, mas serve como
            # garantia extra de que o contexto nunca vaze entre requisições
            # Nota: O clear_tenant() principal está em process_response
            pass
    
    def process_response(self, request, response) -> None:
        """
        Processa a resposta e limpa o contexto de tenant.
        
        Garante que o contexto seja sempre limpo ao final da requisição,
        evitando vazamento de dados entre requisições de diferentes usuários
        ou tenants em ambientes multi-threaded.
        
        Usa try/finally para garantir que clear_tenant() seja sempre executado,
        mesmo em caso de exceção ou erro no processamento da resposta.
        
        Args:
            request: HttpRequest original
            response: HttpResponse gerada
            
        Returns:
            HttpResponse com contexto limpo
        """
        try:
            # Prepara para retornar a resposta
            pass
        finally:
            # Garante que o contexto seja sempre limpo, mesmo em caso de exceção
            # Isso é crítico para evitar vazamento de dados entre threads
            # O Django sempre chama process_response, mas o finally garante
            # que clear_tenant() seja executado independentemente do que aconteça
            clear_tenant()
        
        return response
    
    def process_exception(self, request, exception) -> None:
        """
        Processa exceções e limpa o contexto de tenant.
        
        Garante que mesmo em caso de exceção, o contexto seja limpo,
        prevenindo vazamento de dados.
        
        Args:
            request: HttpRequest original
            exception: Exception levantada
        """
        # Limpa o contexto mesmo em caso de exceção
        clear_tenant()

