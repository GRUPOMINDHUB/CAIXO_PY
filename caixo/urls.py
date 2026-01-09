"""
URL configuration for caixo project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.0/topics/http/urls/
"""

from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static

urlpatterns = [
    path('admin/', admin.site.urls),
    # API REST e Webhooks
    path('api/v1/', include('core.urls')),
]

# Configuração do título do Admin
admin.site.site_header = 'Caixô - Sistema de Gestão Financeira'
admin.site.site_title = 'Caixô Admin'
admin.site.index_title = 'Painel de Administração'

# Serve arquivos de mídia em desenvolvimento
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)

