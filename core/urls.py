"""
URLs do app core.

Define as rotas da API REST e webhooks do sistema Caixô.
"""

from django.urls import path

from core.views import webhooks

app_name = 'core'

urlpatterns = [
    # Webhooks da Evolution API
    # Nota: evolution_webhook agora processa tanto mensagens quanto respostas de botões
    path('webhooks/evolution/', webhooks.evolution_webhook, name='evolution_webhook'),
]

