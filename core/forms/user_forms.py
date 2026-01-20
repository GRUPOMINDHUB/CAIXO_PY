"""
Formulários para gestão de Usuários.

Apenas ADMIN_MASTER pode criar/editar usuários.
"""

from django import forms
from django.contrib.auth.forms import UserCreationForm, PasswordChangeForm
from django.core.exceptions import ValidationError

from core.models.user import User, UserRole
from core.models.tenant import Tenant, TenantStatus


class UserForm(forms.ModelForm):
    """
    Formulário para criar/editar usuários (Gestores e Operadores).
    
    Permite associar múltiplos tenants ao usuário (ManyToMany).
    """
    
    password1 = forms.CharField(
        label='Senha',
        widget=forms.PasswordInput(attrs={
            'class': 'w-full px-4 py-2 rounded-lg outline-none transition',
            'style': 'border: 1px solid #E9E4DB; color: #2D2926; background-color: #FFFFFF;',
            'onfocus': "this.style.borderColor='#D4AF37'; this.style.boxShadow='0 0 0 3px rgba(212, 175, 55, 0.1)';",
            'onblur': "this.style.borderColor='#E9E4DB'; this.style.boxShadow='none';"
        }),
        required=False,
        help_text='Deixe em branco para manter a senha atual (ao editar)'
    )
    
    password2 = forms.CharField(
        label='Confirmar Senha',
        widget=forms.PasswordInput(attrs={
            'class': 'w-full px-4 py-2 rounded-lg outline-none transition',
            'style': 'border: 1px solid #E9E4DB; color: #2D2926; background-color: #FFFFFF;',
            'onfocus': "this.style.borderColor='#D4AF37'; this.style.boxShadow='0 0 0 3px rgba(212, 175, 55, 0.1)';",
            'onblur': "this.style.borderColor='#E9E4DB'; this.style.boxShadow='none';"
        }),
        required=False,
        help_text='Repita a senha para confirmar'
    )
    
    tenants = forms.ModelMultipleChoiceField(
        queryset=Tenant.objects.filter(status=TenantStatus.ACTIVE),
        widget=forms.CheckboxSelectMultiple(attrs={
            'class': 'space-y-2'
        }),
        required=False,
        label='Lojas/Empresas',
        help_text='Selecione as lojas às quais este usuário terá acesso'
    )
    
    class Meta:
        model = User
        fields = [
            'email',
            'first_name',
            'last_name',
            'role',
            'whatsapp_number',
            'is_active',
        ]
        widgets = {
            'email': forms.EmailInput(attrs={
                'class': 'w-full px-4 py-2 rounded-lg outline-none transition',
                'style': 'border: 1px solid #E9E4DB; color: #2D2926; background-color: #FFFFFF;',
                'onfocus': "this.style.borderColor='#D4AF37'; this.style.boxShadow='0 0 0 3px rgba(212, 175, 55, 0.1)';",
                'onblur': "this.style.borderColor='#E9E4DB'; this.style.boxShadow='none';"
            }),
            'first_name': forms.TextInput(attrs={
                'class': 'w-full px-4 py-2 rounded-lg outline-none transition',
                'style': 'border: 1px solid #E9E4DB; color: #2D2926; background-color: #FFFFFF;',
                'onfocus': "this.style.borderColor='#D4AF37'; this.style.boxShadow='0 0 0 3px rgba(212, 175, 55, 0.1)';",
                'onblur': "this.style.borderColor='#E9E4DB'; this.style.boxShadow='none';"
            }),
            'last_name': forms.TextInput(attrs={
                'class': 'w-full px-4 py-2 rounded-lg outline-none transition',
                'style': 'border: 1px solid #E9E4DB; color: #2D2926; background-color: #FFFFFF;',
                'onfocus': "this.style.borderColor='#D4AF37'; this.style.boxShadow='0 0 0 3px rgba(212, 175, 55, 0.1)';",
                'onblur': "this.style.borderColor='#E9E4DB'; this.style.boxShadow='none';"
            }),
            'role': forms.Select(attrs={
                'class': 'w-full px-4 py-2 rounded-lg outline-none transition',
                'style': 'border: 1px solid #E9E4DB; color: #2D2926; background-color: #FFFFFF;',
                'onfocus': "this.style.borderColor='#D4AF37'; this.style.boxShadow='0 0 0 3px rgba(212, 175, 55, 0.1)';",
                'onblur': "this.style.borderColor='#E9E4DB'; this.style.boxShadow='none';"
            }),
            'whatsapp_number': forms.TextInput(attrs={
                'class': 'w-full px-4 py-2 rounded-lg outline-none transition',
                'style': 'border: 1px solid #E9E4DB; color: #2D2926; background-color: #FFFFFF;',
                'placeholder': '5541999999999',
                'onfocus': "this.style.borderColor='#D4AF37'; this.style.boxShadow='0 0 0 3px rgba(212, 175, 55, 0.1)';",
                'onblur': "this.style.borderColor='#E9E4DB'; this.style.boxShadow='none';"
            }),
            'is_active': forms.CheckboxInput(attrs={
                'class': 'w-5 h-5 rounded',
                'style': 'accent-color: #D4AF37;'
            }),
        }
        labels = {
            'email': 'Email',
            'first_name': 'Nome',
            'last_name': 'Sobrenome',
            'role': 'Função',
            'whatsapp_number': 'Número WhatsApp',
            'is_active': 'Ativo',
        }
    
    def __init__(self, *args, **kwargs):
        """Inicializa o formulário com tenants do usuário (se editando)."""
        super().__init__(*args, **kwargs)
        
        # Se estiver editando, carrega tenants do usuário
        if self.instance and self.instance.pk:
            self.fields['tenants'].initial = self.instance.tenants.all()
            # Torna senha opcional na edição
            self.fields['password1'].required = False
            self.fields['password2'].required = False
    
    def clean(self):
        """Validação adicional do formulário."""
        cleaned_data = super().clean()
        
        role = cleaned_data.get('role')
        tenants = cleaned_data.get('tenants', [])
        
        # Valida se ADMIN_MASTER não tem tenants
        if role == UserRole.ADMIN_MASTER and tenants:
            raise ValidationError({
                'tenants': 'Administradores Master não podem ter tenants associados.'
            })
        
        # Valida se usuário não-master tem tenants
        if role != UserRole.ADMIN_MASTER and not tenants:
            raise ValidationError({
                'tenants': 'Usuários não-master devem ter pelo menos um tenant associado.'
            })
        
        # Valida senhas (apenas se fornecidas)
        password1 = cleaned_data.get('password1')
        password2 = cleaned_data.get('password2')
        
        if password1 or password2:
            if password1 != password2:
                raise ValidationError({
                    'password2': 'As senhas não coincidem.'
                })
            if len(password1) < 8:
                raise ValidationError({
                    'password1': 'A senha deve ter pelo menos 8 caracteres.'
                })
        
        return cleaned_data
    
    def save(self, commit=True):
        """Salva o usuário e associa tenants."""
        user = super().save(commit=False)
        
        if commit:
            user.save()
            # Associa tenants via ManyToMany
            if 'tenants' in self.cleaned_data:
                user.tenants.set(self.cleaned_data['tenants'])
        
        return user


class CustomPasswordChangeForm(PasswordChangeForm):
    """
    Formulário personalizado para alteração de senha.
    
    Baseado no PasswordChangeForm do Django, mas com validações adicionais
    e estilização compatível com o tema Caixô.
    """
    
    def __init__(self, *args, **kwargs):
        """Inicializa o formulário com estilos do tema Caixô."""
        super().__init__(*args, **kwargs)
        
        # Estiliza todos os campos de senha
        for field_name, field in self.fields.items():
            field.widget.attrs.update({
                'class': 'w-full px-4 py-2 rounded-lg outline-none transition',
                'style': 'border: 1px solid #E9E4DB; color: #2D2926; background-color: #FFFFFF;',
                'onfocus': "this.style.borderColor='#D4AF37'; this.style.boxShadow='0 0 0 3px rgba(212, 175, 55, 0.1)';",
                'onblur': "this.style.borderColor='#E9E4DB'; this.style.boxShadow='none';"
            })
    
    def clean_new_password1(self):
        """Validação adicional da nova senha."""
        new_password1 = self.cleaned_data.get('new_password1')
        
        # Verifica se a nova senha é diferente da atual
        if self.user.check_password(new_password1):
            raise ValidationError(
                'A nova senha deve ser diferente da senha atual.',
                code='password_same_as_old'
            )
        
        # Validação de complexidade mínima
        if len(new_password1) < 8:
            raise ValidationError(
                'A senha deve ter pelo menos 8 caracteres.',
                code='password_too_short'
            )
        
        # Verifica se contém pelo menos uma letra e um número
        has_letter = any(c.isalpha() for c in new_password1)
        has_number = any(c.isdigit() for c in new_password1)
        
        if not (has_letter and has_number):
            raise ValidationError(
                'A senha deve conter pelo menos uma letra e um número.',
                code='password_weak'
            )
        
        return new_password1
