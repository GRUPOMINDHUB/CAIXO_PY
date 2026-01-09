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
        
        Se o usuário estiver autenticado e possuir um tenant_id,
        define automaticamente no contexto thread-local para que
        todas as queries subsequentes sejam filtradas automaticamente.
        
        Args:
            request: HttpRequest com o usuário autenticado (se houver)
        """
        # Limpa qualquer contexto anterior (segurança extra)
        clear_tenant()
        
        # Verifica se o usuário está autenticado
        if hasattr(request, 'user') and request.user.is_authenticated:
            user = request.user
            
            # Verifica se o usuário tem tenant_id
            # ADMIN_MASTER não tem tenant (None)
            if hasattr(user, 'tenant_id') and user.tenant_id is not None:
                # Define o tenant no contexto thread-local
                set_current_tenant(user.tenant_id)
    
    def process_response(self, request, response) -> None:
        """
        Processa a resposta e limpa o contexto de tenant.
        
        Garante que o contexto seja sempre limpo ao final da requisição,
        evitando vazamento de dados entre requisições de diferentes usuários
        ou tenants em ambientes multi-threaded.
        
        Args:
            request: HttpRequest original
            response: HttpResponse gerada
            
        Returns:
            HttpResponse com contexto limpo
        """
        # Limpa o contexto de tenant ao final da requisição
        # Isso é crítico para evitar vazamento de dados entre threads
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

