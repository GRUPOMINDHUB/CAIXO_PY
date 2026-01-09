# Caixô - Sistema de Gestão Financeira Multi-tenant

# Importa Celery app para garantir que seja carregado quando Django iniciar
from .celery import app as celery_app

__all__ = ('celery_app',)

