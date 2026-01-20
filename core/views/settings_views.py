"""
Views de Configurações - Personalização e Segurança.

Implementa:
- Seletor de tema (Claro, Escuro, Sistema)
- Alteração de senha do usuário
- Outras configurações futuras
"""

import logging
from django.contrib import messages
from django.contrib.auth import update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect
from django.views.decorators.http import require_http_methods

from core.forms.user_forms import CustomPasswordChangeForm

logger = logging.getLogger(__name__)


@login_required
@require_http_methods(['GET', 'POST'])
def settings_view(request):
    """
    View principal de configurações.
    
    Exibe as seções:
    - Aparência (Seletor de Tema)
    - Segurança (Alteração de Senha)
    
    Args:
        request: HttpRequest com request.user
        
    Returns:
        HttpResponse com template de configurações renderizado
    """
    # Inicializa formulário de senha vazio para exibição
    password_form = CustomPasswordChangeForm(user=request.user)
    
    context = {
        'user': request.user,
        'tenant': getattr(request, 'tenant', None),
        'password_form': password_form,
    }
    
    return render(request, 'settings/settings_home.html', context)


@login_required
@require_http_methods(['GET', 'POST'])
def change_password_view(request):
    """
    View para alteração de senha do usuário logado.
    
    Processa o formulário de alteração de senha e atualiza a sessão
    para evitar logout automático após a mudança.
    
    Segurança: Usa update_session_auth_hash() para manter o usuário logado
    após a alteração da senha (padrão profissional de SaaS).
    
    Args:
        request: HttpRequest com request.user
        
    Returns:
        HttpResponse com template de configurações ou redirect
    """
    if request.method == 'POST':
        form = CustomPasswordChangeForm(user=request.user, data=request.POST)
        
        if form.is_valid():
            try:
                # Salva a nova senha
                user = form.save()
                
                # CRÍTICO: Atualiza o hash da sessão para evitar logout automático
                # Isso é o que diferencia sistemas amadores de profissionais
                update_session_auth_hash(request, user)
                
                messages.success(
                    request,
                    'Senha alterada com sucesso!'
                )
                
                logger.info(f'Usuário {request.user.email} alterou a senha com sucesso.')
                
                # Redireciona para a página de configurações
                return redirect('settings')
                
            except Exception as e:
                logger.error(f'Erro ao alterar senha do usuário {request.user.email}: {str(e)}', exc_info=True)
                messages.error(
                    request,
                    'Erro ao alterar senha. Tente novamente mais tarde.'
                )
        else:
            # Exibe erros de validação
            for field, errors in form.errors.items():
                for error in errors:
                    messages.error(request, f'{form.fields[field].label}: {error}')
    else:
        form = CustomPasswordChangeForm(user=request.user)
    
    context = {
        'user': request.user,
        'tenant': getattr(request, 'tenant', None),
        'password_form': form,
    }
    
    return render(request, 'settings/settings_home.html', context)
