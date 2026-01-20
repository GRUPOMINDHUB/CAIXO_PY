"""
Views de Administração - Gestão de Empresas e Usuários.

Apenas acessível para ADMIN_MASTER.
Implementa CRUD completo de Tenants e Users com validações de plano.
"""

import logging
from typing import Optional

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.db import transaction as db_transaction
from django.db.models import Q
from django.shortcuts import render, redirect, get_object_or_404
from django.views.decorators.http import require_http_methods, require_POST

from core.models.tenant import Tenant, TenantPlan, TenantStatus
from core.models.user import User, UserRole
from core.forms.tenant_forms import TenantForm
from core.forms.user_forms import UserForm

logger = logging.getLogger(__name__)


def is_admin_master(user):
    """Verifica se o usuário é ADMIN_MASTER."""
    return user.is_authenticated and user.is_master


@login_required
@require_http_methods(['GET', 'POST'])
def switch_tenant(request):
    """
    Troca o tenant ativo na sessão do usuário.
    
    Valida se o usuário tem permissão para acessar o tenant selecionado.
    ADMIN_MASTER pode acessar qualquer tenant.
    """
    if request.method == 'POST':
        tenant_id = request.POST.get('tenant_id')
        
        if not tenant_id:
            messages.error(request, 'Tenant não informado.')
            return redirect('dashboard')
        
        try:
            tenant = Tenant.objects.get(id=tenant_id)
            
            # Valida permissão
            if not request.user.is_master:
                # Usuário comum: verifica se tem acesso ao tenant
                if not request.user.tenants.filter(id=tenant.id).exists():
                    # Fallback: verifica campo legado
                    if request.user.tenant_id != tenant.id:
                        messages.error(request, 'Você não tem permissão para acessar esta empresa.')
                        return redirect('dashboard')
            
            # Define na sessão
            request.session['tenant_id'] = str(tenant.id)
            messages.success(request, f'Ambiente alterado para: {tenant.name}')
            
        except Tenant.DoesNotExist:
            messages.error(request, 'Empresa não encontrada.')
        except Exception as e:
            logger.error(f'Erro ao trocar tenant: {str(e)}', exc_info=True)
            messages.error(request, 'Erro ao trocar de empresa. Tente novamente.')
    
    return redirect(request.META.get('HTTP_REFERER', 'dashboard'))


@login_required
@require_http_methods(['GET', 'POST'])
def user_create(request):
    """
    Cria um novo usuário (Gestor ou Operador).
    
    Apenas ADMIN_MASTER pode criar usuários.
    """
    if not is_admin_master(request.user):
        messages.error(request, 'Acesso negado. Apenas Administradores Master podem criar usuários.')
        return redirect('dashboard')
    
    if request.method == 'POST':
        form = UserForm(request.POST)
        
        if form.is_valid():
            try:
                with db_transaction.atomic():
                    # Cria o usuário
                    tenants = form.cleaned_data.get('tenants', [])
                    user = User.objects.create_user(
                        email=form.cleaned_data['email'],
                        password=form.cleaned_data['password1'],
                        tenants=tenants,
                        role=form.cleaned_data['role'],
                    )
                    
                    messages.success(request, f'Usuário {user.email} criado com sucesso!')
                    return redirect('user_list')
                    
            except Exception as e:
                logger.error(f'Erro ao criar usuário: {str(e)}', exc_info=True)
                messages.error(request, f'Erro ao criar usuário: {str(e)}')
    else:
        form = UserForm()
    
    context = {
        'form': form,
        'tenants': Tenant.objects.filter(status=TenantStatus.ACTIVE).order_by('name'),
    }
    
    return render(request, 'core/admin/user_form.html', context)


@login_required
@require_http_methods(['GET', 'POST'])
def user_edit(request, pk):
    """
    Edita um usuário existente.
    
    Apenas ADMIN_MASTER pode editar usuários.
    """
    if not is_admin_master(request.user):
        messages.error(request, 'Acesso negado. Apenas Administradores Master podem editar usuários.')
        return redirect('dashboard')
    
    user = get_object_or_404(User, pk=pk)
    
    if request.method == 'POST':
        form = UserForm(request.POST, instance=user)
        
        if form.is_valid():
            try:
                with db_transaction.atomic():
                    # Atualiza o usuário
                    user = form.save()
                    
                    # Atualiza tenants (ManyToMany)
                    if 'tenants' in form.cleaned_data:
                        user.tenants.set(form.cleaned_data['tenants'])
                    
                    # Atualiza senha se fornecida
                    if form.cleaned_data.get('password1'):
                        user.set_password(form.cleaned_data['password1'])
                        user.save()
                    
                    messages.success(request, f'Usuário {user.email} atualizado com sucesso!')
                    return redirect('user_list')
                    
            except Exception as e:
                logger.error(f'Erro ao editar usuário: {str(e)}', exc_info=True)
                messages.error(request, f'Erro ao atualizar usuário: {str(e)}')
    else:
        form = UserForm(instance=user)
    
    context = {
        'form': form,
        'user': user,
        'tenants': Tenant.objects.filter(status=TenantStatus.ACTIVE).order_by('name'),
    }
    
    return render(request, 'core/admin/user_form.html', context)


@login_required
def user_list(request):
    """
    Lista todos os usuários do sistema.
    
    Apenas ADMIN_MASTER pode ver a lista de usuários.
    """
    if not is_admin_master(request.user):
        messages.error(request, 'Acesso negado. Apenas Administradores Master podem ver usuários.')
        return redirect('dashboard')
    
    users = User.objects.all().prefetch_related('tenants').order_by('email')
    
    # Filtro de busca
    search_query = request.GET.get('search', '').strip()
    if search_query:
        users = users.filter(
            Q(email__icontains=search_query) |
            Q(first_name__icontains=search_query) |
            Q(last_name__icontains=search_query)
        )
    
    context = {
        'users': users,
        'search_query': search_query,
    }
    
    return render(request, 'core/admin/user_list.html', context)
