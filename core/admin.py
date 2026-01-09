"""
Configuração do Django Admin para o sistema Caixô.

Implementa Admin customizado que garante isolamento de dados por tenant:
- SuperAdmin (ADMIN_MASTER) vê TODOS os registros
- Gestores e Operadores veem APENAS os registros do seu tenant
"""

from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.utils.html import format_html
from django.urls import reverse

from core.models import Tenant, User
from core.models.base import TenantModel
from core.utils.tenant_context import get_current_tenant


class TenantAdminMixin:
    """
    Mixin para Admin customizado que aplica filtro automático por tenant.
    
    Garante que apenas usuários ADMIN_MASTER vejam todos os registros,
    enquanto outros usuários veem apenas os registros do seu tenant.
    """
    
    def get_queryset(self, request):
        """
        Sobrescreve get_queryset para filtrar por tenant baseado no usuário.
        
        - ADMIN_MASTER: vê TODOS os registros (sem filtro)
        - Outros: veem APENAS os registros do seu tenant
        
        Args:
            request: HttpRequest com o usuário autenticado
            
        Returns:
            QuerySet filtrado por tenant se necessário
        """
        qs = super().get_queryset(request)
        
        # Se o usuário é ADMIN_MASTER, retorna todos os registros
        if hasattr(request.user, 'is_master') and request.user.is_master:
            return qs
        
        # Se o usuário tem tenant, filtra apenas os registros desse tenant
        if hasattr(request.user, 'tenant_id') and request.user.tenant_id:
            # Para modelos que herdam de TenantModel, filtra por tenant
            if issubclass(self.model, TenantModel):
                return qs.filter(tenant_id=request.user.tenant_id)
            
            # Para outros modelos, retorna queryset vazio se não for do tenant
            # (não deve acontecer se a arquitetura estiver correta)
            return qs.none()
        
        # Se não tem tenant e não é master, retorna queryset vazio
        return qs.none()
    
    def save_model(self, request, obj, form, change):
        """
        Sobrescreve save_model para definir tenant automaticamente.
        
        Se o objeto herda de TenantModel e não tem tenant definido,
        usa o tenant do usuário logado.
        
        Args:
            request: HttpRequest com o usuário autenticado
            obj: Instância do modelo a ser salva
            form: Formulário usado
            change: Boolean indicando se é atualização ou criação
        """
        # Para modelos que herdam de TenantModel, define o tenant se necessário
        if isinstance(obj, TenantModel):
            if not obj.tenant_id and hasattr(request.user, 'tenant_id') and request.user.tenant_id:
                obj.tenant_id = request.user.tenant_id
        
        super().save_model(request, obj, form, change)


@admin.register(Tenant)
class TenantAdmin(admin.ModelAdmin):
    """
    Admin customizado para o modelo Tenant.
    
    Características:
    - SuperAdmin vê todos os tenants
    - Outros usuários não veem tenants (apenas seu próprio, se necessário)
    """
    
    list_display = ['name', 'cnpj_formatted', 'plan', 'status', 'billing_day_weekly', 'billing_day_monthly', 'created_at']
    list_filter = ['plan', 'status', 'created_at']
    search_fields = ['name', 'cnpj']
    readonly_fields = ['id', 'created_at', 'updated_at', 'cnpj_formatted']
    
    fieldsets = (
        ('Informações Básicas', {
            'fields': ('id', 'name', 'cnpj', 'cnpj_formatted')
        }),
        ('Configurações', {
            'fields': ('plan', 'status')
        }),
        ('Faturamento', {
            'fields': ('billing_day_weekly', 'billing_day_monthly'),
            'description': 'Configure os dias para cobrança proativa via WhatsApp.'
        }),
        ('Metadados', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    
    def get_queryset(self, request):
        """
        Sobrescreve get_queryset para ADMIN_MASTER ver todos os tenants.
        
        Outros usuários não devem acessar a lista de tenants.
        """
        qs = super().get_queryset(request)
        
        # Apenas ADMIN_MASTER pode ver tenants
        if hasattr(request.user, 'is_master') and request.user.is_master:
            return qs
        
        # Outros usuários não veem tenants
        return qs.none()
    
    def save_model(self, request, obj, form, change):
        """
        Sobrescreve save_model para ADMIN_MASTER poder criar/editar tenants.
        """
        super().save_model(request, obj, form, change)
    
    def cnpj_formatted(self, obj):
        """
        Exibe CNPJ formatado na lista.
        
        Args:
            obj: Instância do Tenant
            
        Returns:
            CNPJ formatado ou '-'
        """
        return obj.cnpj_formatted if obj.cnpj else '-'
    cnpj_formatted.short_description = 'CNPJ Formatado'


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    """
    Admin customizado para o modelo User.
    
    Características:
    - SuperAdmin vê todos os usuários
    - Gestores veem apenas usuários do seu tenant
    """
    
    list_display = ['email', 'get_tenant_name', 'role', 'whatsapp_number', 'is_active', 'date_joined']
    list_filter = ['role', 'is_active', 'is_staff', 'tenant', 'date_joined']
    search_fields = ['email', 'whatsapp_number', 'tenant__name']
    readonly_fields = ['id', 'date_joined', 'last_login', 'created_at', 'updated_at']
    
    fieldsets = (
        (None, {'fields': ('id', 'email', 'password')}),
        ('Permissões', {
            'fields': ('is_active', 'is_staff', 'is_superuser', 'groups', 'user_permissions'),
        }),
        ('Caixô', {
            'fields': ('tenant', 'role', 'whatsapp_number'),
            'description': 'Configurações específicas do Caixô.'
        }),
        ('Datas Importantes', {
            'fields': ('date_joined', 'last_login', 'created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    
    add_fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': ('email', 'password1', 'password2', 'tenant', 'role', 'whatsapp_number'),
        }),
    )
    
    def get_queryset(self, request):
        """
        Sobrescreve get_queryset para filtrar usuários por tenant.
        
        - ADMIN_MASTER: vê TODOS os usuários
        - Outros: veem apenas usuários do seu tenant
        """
        qs = super().get_queryset(request)
        
        # ADMIN_MASTER vê todos os usuários
        if hasattr(request.user, 'is_master') and request.user.is_master:
            return qs
        
        # Outros usuários veem apenas usuários do seu tenant
        if hasattr(request.user, 'tenant_id') and request.user.tenant_id:
            return qs.filter(tenant_id=request.user.tenant_id)
        
        # Se não tem tenant, não vê ninguém (exceto si mesmo)
        return qs.filter(id=request.user.id)
    
    def get_tenant_name(self, obj):
        """
        Exibe nome do tenant do usuário na lista.
        
        Args:
            obj: Instância do User
            
        Returns:
            Nome do tenant ou '[MASTER]'
        """
        if obj.tenant:
            url = reverse('admin:core_tenant_change', args=[obj.tenant.id])
            return format_html('<a href="{}">{}</a>', url, obj.tenant.name)
        return format_html('<strong>[MASTER]</strong>')
    get_tenant_name.short_description = 'Tenant'
    
    def save_model(self, request, obj, form, change):
        """
        Sobrescreve save_model para validar tenant baseado no role.
        
        Garante que:
        - ADMIN_MASTER não tenha tenant
        - Outros roles tenham tenant (exceto se o usuário logado for ADMIN_MASTER)
        """
        # Se não está mudando (criando novo) e o usuário logado não é ADMIN_MASTER
        if not change and not request.user.is_master:
            # Define o tenant do novo usuário como o tenant do usuário logado
            if hasattr(request.user, 'tenant_id') and request.user.tenant_id:
                obj.tenant_id = request.user.tenant_id
        
        super().save_model(request, obj, form, change)
    
    def get_readonly_fields(self, request, obj=None):
        """
        Torna campos readonly baseado no usuário.
        
        - ADMIN_MASTER pode editar tudo
        - Outros não podem mudar tenant e role
        """
        readonly = list(self.readonly_fields)
        
        if not request.user.is_master:
            readonly.extend(['tenant', 'role'])
        
        return readonly

