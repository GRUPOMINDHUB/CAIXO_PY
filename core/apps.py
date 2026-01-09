from django.apps import AppConfig


class CoreConfig(AppConfig):
    """Configuração do app core do Caixô."""
    # Nota: Modelos do Caixô usam UUIDField explicitamente como pk
    # Este valor será usado apenas se algum modelo não especificar pk
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'core'
    verbose_name = 'Core - Núcleo do Sistema'

