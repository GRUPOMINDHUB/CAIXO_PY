from django.apps import AppConfig


class CoreConfig(AppConfig):
    """Configuração do app core do Caixô."""
    default_auto_field = 'django.db.models.UUIDField'
    name = 'core'
    verbose_name = 'Core - Núcleo do Sistema'

