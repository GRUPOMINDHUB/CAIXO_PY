"""
URLs do app core.

Define as rotas da API REST e webhooks do sistema Caixô.
"""

from django.urls import path

from core.views import webhooks

app_name = 'core'

urlpatterns = [
    # Webhooks da Evolution API
    path('webhooks/evolution/', webhooks.evolution_webhook, name='evolution_webhook'),
    path('webhooks/evolution/buttons/', webhooks.evolution_buttons_webhook, name='evolution_buttons_webhook'),
]

