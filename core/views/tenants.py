"""
Views para gerenciamento de Tenants (Empresas).

Implementa CRUD completo para cadastro, listagem, edição e exclusão de tenants.
Apenas usuários ADMIN_MASTER podem acessar estas views.
"""

import logging
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.shortcuts import render, redirect, get_object_or_404
from django.core.paginator import Paginator
from django.core.exceptions import ValidationError
from django.db.models import Q

from core.models import Tenant
from core.models.tenant import TenantStatus, TenantPlan
from core.forms import TenantForm
from core.models.user import UserRole

logger = logging.getLogger(__name__)


@login_required
def tenant_list(request):
    """
    Lista todos os tenants cadastrados no sistema.
    
    Apenas ADMIN_MASTER pode acessar esta view.
    Inclui busca por nome ou CNPJ e paginação.
    
    Args:
        request: HttpRequest com usuário autenticado
        
    Returns:
        HttpResponse com template de listagem de tenants
    """
    # Verifica se é ADMIN_MASTER
    if not (hasattr(request.user, 'is_master') and request.user.is_master):
        messages.error(request, 'Apenas Administradores Master podem acessar esta página.')
        return redirect('dashboard')
    
    # Busca e filtros
    search_query = request.GET.get('search', '').strip()
    status_filter = request.GET.get('status', '')
    plan_filter = request.GET.get('plan', '')
    
    # Query base
    tenants = Tenant.objects.all()
    
    # Aplica filtros
    if search_query:
        tenants = tenants.filter(
            Q(name__icontains=search_query) |
            Q(cnpj__icontains=search_query)
        )
    
    if status_filter:
        tenants = tenants.filter(status=status_filter)
    
    if plan_filter:
        tenants = tenants.filter(plan=plan_filter)
    
    # Ordena por nome
    tenants = tenants.order_by('name')
    
    # Paginação
    paginator = Paginator(tenants, 20)  # 20 tenants por página
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    context = {
        'tenants': page_obj,
        'search_query': search_query,
        'status_filter': status_filter,
        'plan_filter': plan_filter,
        'status_choices': TenantStatus.choices,
        'plan_choices': TenantPlan.choices,
    }
    
    return render(request, 'core/tenants/list.html', context)


@login_required
def tenant_create(request):
    """
    Cria um novo tenant no sistema.
    
    Apenas ADMIN_MASTER pode acessar esta view.
    Valida CNPJ e cria o tenant com os dados fornecidos.
    
    Args:
        request: HttpRequest com dados do formulário
        
    Returns:
        HttpResponse com formulário ou redirecionamento após criação
    """
    # Verifica se é ADMIN_MASTER
    if not (hasattr(request.user, 'is_master') and request.user.is_master):
        messages.error(request, 'Apenas Administradores Master podem criar empresas.')
        return redirect('dashboard')
    
    if request.method == 'POST':
        form = TenantForm(request.POST)
        if form.is_valid():
            try:
                tenant = form.save()
                messages.success(request, f'Empresa "{tenant.name}" cadastrada com sucesso!')
                logger.info(f'Tenant criado: {tenant.id} - {tenant.name} por {request.user.email}')
                return redirect('tenant_list')
            except ValidationError as e:
                # Captura erros de validação do modelo
                for field, errors in e.error_dict.items():
                    for error in errors:
                        messages.error(request, f'{field}: {error}')
            except Exception as e:
                logger.error(f'Erro ao criar tenant: {str(e)}', exc_info=True)
                messages.error(request, f'Erro ao cadastrar empresa: {str(e)}')
    else:
        form = TenantForm()
    
    context = {
        'form': form,
        'title': 'Cadastrar Nova Empresa',
        'action': 'Criar',
    }
    
    return render(request, 'core/tenants/form.html', context)


@login_required
def tenant_edit(request, tenant_id):
    """
    Edita um tenant existente.
    
    Apenas ADMIN_MASTER pode acessar esta view.
    
    Args:
        request: HttpRequest com dados do formulário
        tenant_id: UUID do tenant a ser editado
        
    Returns:
        HttpResponse com formulário ou redirecionamento após edição
    """
    # Verifica se é ADMIN_MASTER
    if not (hasattr(request.user, 'is_master') and request.user.is_master):
        messages.error(request, 'Apenas Administradores Master podem editar empresas.')
        return redirect('dashboard')
    
    tenant = get_object_or_404(Tenant, id=tenant_id)
    
    if request.method == 'POST':
        form = TenantForm(request.POST, instance=tenant)
        if form.is_valid():
            try:
                tenant = form.save()
                messages.success(request, f'Empresa "{tenant.name}" atualizada com sucesso!')
                logger.info(f'Tenant editado: {tenant.id} - {tenant.name} por {request.user.email}')
                return redirect('tenant_list')
            except ValidationError as e:
                # Captura erros de validação do modelo
                for field, errors in e.error_dict.items():
                    for error in errors:
                        messages.error(request, f'{field}: {error}')
            except Exception as e:
                logger.error(f'Erro ao editar tenant: {str(e)}', exc_info=True)
                messages.error(request, f'Erro ao atualizar empresa: {str(e)}')
    else:
        form = TenantForm(instance=tenant)
    
    context = {
        'form': form,
        'tenant': tenant,
        'title': f'Editar Empresa: {tenant.name}',
        'action': 'Salvar',
    }
    
    return render(request, 'core/tenants/form.html', context)


@login_required
def tenant_delete(request, tenant_id):
    """
    Deleta um tenant do sistema.
    
    Apenas ADMIN_MASTER pode acessar esta view.
    Verifica se há usuários vinculados antes de deletar.
    
    Args:
        request: HttpRequest
        tenant_id: UUID do tenant a ser deletado
        
    Returns:
        HttpResponse com confirmação ou redirecionamento
    """
    # Verifica se é ADMIN_MASTER
    if not (hasattr(request.user, 'is_master') and request.user.is_master):
        messages.error(request, 'Apenas Administradores Master podem deletar empresas.')
        return redirect('dashboard')
    
    tenant = get_object_or_404(Tenant, id=tenant_id)
    
    if request.method == 'POST':
        # Verifica se há usuários vinculados (agora via ManyToMany)
        from core.models import User
        users_count = tenant.users.count()
        
        if users_count > 0:
            messages.error(
                request,
                f'Não é possível deletar a empresa "{tenant.name}" porque existem {users_count} usuário(s) vinculado(s) a ela.'
            )
            return redirect('tenant_list')
        
        try:
            tenant_name = tenant.name
            tenant.delete()
            messages.success(request, f'Empresa "{tenant_name}" deletada com sucesso!')
            logger.info(f'Tenant deletado: {tenant_id} - {tenant_name} por {request.user.email}')
        except Exception as e:
            logger.error(f'Erro ao deletar tenant: {str(e)}', exc_info=True)
            messages.error(request, f'Erro ao deletar empresa: {str(e)}')
        
        return redirect('tenant_list')
    
    # GET - Mostra página de confirmação
    context = {
        'tenant': tenant,
    }
    
    return render(request, 'core/tenants/delete.html', context)
