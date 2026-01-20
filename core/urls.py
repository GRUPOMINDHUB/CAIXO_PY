"""
URLs do app core.

Define as rotas da API REST, webhooks e views do sistema Caixô.
"""

from django.urls import path

from core.views import webhooks, dashboard_view, tenants, finance_views, admin_views, settings_views, projections

# app_name removido para evitar conflito de namespace
# URLs principais (dashboard) não têm namespace
# URLs de API usam namespace 'api' quando incluídas em caixo/urls.py

urlpatterns = [
    # Dashboard (rota raiz)
    path('', dashboard_view, name='dashboard'),
    
    # Projeções Financeiras
    path('projecoes/', projections.projections_view, name='projections'),
    
    # CRUD de Tenants (Empresas)
    path('tenants/', tenants.tenant_list, name='tenant_list'),
    path('tenants/create/', tenants.tenant_create, name='tenant_create'),
    path('tenants/<uuid:tenant_id>/edit/', tenants.tenant_edit, name='tenant_edit'),
    path('tenants/<uuid:tenant_id>/delete/', tenants.tenant_delete, name='tenant_delete'),
    
    # Webhooks da Evolution API
    # Nota: evolution_webhook agora processa tanto mensagens quanto respostas de botões
    path('webhooks/evolution/', webhooks.evolution_webhook, name='evolution_webhook'),
    
    # Movimentações Financeiras
    path('movimentacoes/', finance_views.movement_list, name='movement_list'),
    # Despesas
    path('movimentacoes/nova-despesa/', finance_views.expense_create, name='expense_create'),
    path('movimentacoes/editar-despesa/<uuid:pk>/', finance_views.expense_edit, name='expense_edit'),
    # Receitas
    path('movimentacoes/nova-receita/', finance_views.revenue_create, name='revenue_create'),
    path('movimentacoes/editar-receita/<uuid:pk>/', finance_views.revenue_edit, name='revenue_edit'),
    # Ações gerais
    path('movimentacoes/excluir/<uuid:pk>/', finance_views.movement_delete, name='movement_delete'),
    path('movimentacoes/parcela/<uuid:pk>/marcar-pago/', finance_views.installment_mark_paid, name='installment_mark_paid'),
    
    # API para subcategorias (AJAX)
    path('movimentacoes/api/subcategories/all/', finance_views.get_all_subcategories, name='get_all_subcategories'),
    path('movimentacoes/api/categories/<uuid:category_id>/subcategories/', finance_views.get_subcategories, name='get_subcategories'),
    path('movimentacoes/api/categories/create/', finance_views.create_category_ajax, name='create_category_ajax'),
    path('movimentacoes/api/subcategories/create/', finance_views.create_subcategory_ajax, name='create_subcategory_ajax'),
    path('movimentacoes/api/subcategories/<uuid:subcategory_id>/', finance_views.get_subcategory_detail, name='get_subcategory_detail'),
    path('movimentacoes/api/subcategories/<uuid:subcategory_id>/edit/', finance_views.edit_subcategory_ajax, name='edit_subcategory_ajax'),
    path('movimentacoes/api/subcategories/<uuid:subcategory_id>/delete/', finance_views.delete_subcategory_ajax, name='delete_subcategory_ajax'),
    path('movimentacoes/api/sales-channels/create/', finance_views.create_sales_channel_ajax, name='create_sales_channel_ajax'),
    
    # Troca de Tenant (Sessão)
    path('switch-tenant/', admin_views.switch_tenant, name='switch_tenant'),
    
    # Gestão de Usuários (Admin Master)
    path('admin/users/', admin_views.user_list, name='user_list'),
    path('admin/users/create/', admin_views.user_create, name='user_create'),
    path('admin/users/<uuid:pk>/edit/', admin_views.user_edit, name='user_edit'),
    
    # Configurações
    path('configuracoes/', settings_views.settings_view, name='settings'),
    path('configuracoes/alterar-senha/', settings_views.change_password_view, name='change_password'),
]

