"""
Módulo de contexto thread-local para gerenciamento de tenant.

Permite armazenar o tenant atual em uma thread-local storage,
garantindo isolamento automático de dados nas queries.
"""

import threading
from typing import Optional
from uuid import UUID


# Thread-local storage para armazenar o tenant atual
_context = threading.local()


def set_current_tenant(tenant_id: Optional[UUID]) -> None:
    """
    Define o tenant atual para a thread atual.
    
    Args:
        tenant_id: UUID do tenant ou None para limpar o contexto
    """
    _context.tenant_id = tenant_id


def get_current_tenant() -> Optional[UUID]:
    """
    Retorna o tenant atual da thread atual.
    
    Returns:
        UUID do tenant ou None se não houver tenant definido
    """
    return getattr(_context, 'tenant_id', None)


def clear_tenant() -> None:
    """
    Limpa o tenant atual da thread.
    """
    if hasattr(_context, 'tenant_id'):
        delattr(_context, 'tenant_id')


