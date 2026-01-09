"""
Modelo User customizado - Sistema de autenticação e autorização.

Herdado de AbstractUser do Django, estende com campos específicos
do Caixô: tenant, role e whatsapp_number.
"""

import uuid
from typing import Optional
from uuid import UUID

from django.contrib.auth.models import AbstractUser, BaseUserManager
from django.core.exceptions import ValidationError
from django.db import models

from core.models.tenant import Tenant
from core.utils.tenant_context import set_current_tenant


class UserRole(models.TextChoices):
    """Roles disponíveis no sistema."""
    ADMIN_MASTER = 'ADMIN_MASTER', 'Administrador Master'
    GESTOR = 'GESTOR', 'Gestor'
    OPERADOR = 'OPERADOR', 'Operador'


class UserManager(BaseUserManager):
    """
    Manager customizado para o modelo User.
    
    Sobrescreve métodos de criação de usuários para garantir
    que o tenant seja sempre definido quando apropriado.
    """
    
    def create_user(
        self,
        email: str,
        password: Optional[str] = None,
        tenant: Optional[Tenant] = None,
        role: str = UserRole.OPERADOR,
        **extra_fields
    ):
        """
        Cria e salva um usuário comum.
        
        Args:
            email: Email do usuário (usa como username)
            password: Senha do usuário
            tenant: Tenant ao qual o usuário pertence (None apenas para ADMIN_MASTER)
            role: Role do usuário (OPERADOR por padrão)
            **extra_fields: Campos extras
            
        Returns:
            User criado
            
        Raises:
            ValidationError: Se tentar criar usuário não-master sem tenant
        """
        if not email:
            raise ValueError('O email é obrigatório')
        
        # Normaliza o email
        email = self.normalize_email(email)
        
        # Valida se usuário não-master tem tenant
        if role != UserRole.ADMIN_MASTER and not tenant:
            raise ValidationError('Usuários não-master devem ter um tenant associado.')
        
        # Se for ADMIN_MASTER, tenant deve ser None
        if role == UserRole.ADMIN_MASTER and tenant:
            raise ValidationError('Administradores Master não podem ter tenant associado.')
        
        user = self.model(
            email=email,
            username=email,  # Usa email como username
            tenant=tenant,
            role=role,
            **extra_fields
        )
        
        user.set_password(password)
        user.save(using=self._db)
        return user
    
    def create_superuser(
        self,
        email: str,
        password: Optional[str] = None,
        **extra_fields
    ):
        """
        Cria e salva um superusuário (ADMIN_MASTER).
        
        Args:
            email: Email do superusuário
            password: Senha do superusuário
            **extra_fields: Campos extras (tenant será ignorado)
            
        Returns:
            User criado como ADMIN_MASTER
        """
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        extra_fields.setdefault('role', UserRole.ADMIN_MASTER)
        extra_fields.pop('tenant', None)  # Remove tenant se existir
        
        if extra_fields.get('is_staff') is not True:
            raise ValueError('Superuser deve ter is_staff=True.')
        if extra_fields.get('is_superuser') is not True:
            raise ValueError('Superuser deve ter is_superuser=True.')
        
        return self.create_user(email, password, tenant=None, **extra_fields)


class User(AbstractUser):
    """
    Modelo User customizado herdado de AbstractUser.
    
    Estende com campos específicos do Caixô:
    - tenant: ForeignKey para Tenant (None apenas para ADMIN_MASTER)
    - role: ChoiceField com roles do sistema
    - whatsapp_number: Número do WhatsApp vinculado à Evolution API
    
    Características:
    - Usa email como username (não permite username diferente)
    - Isolamento automático por tenant nas queries
    - Validação de tenant baseada no role
    """
    
    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
        verbose_name='ID',
        help_text='Identificador único (UUID) do usuário'
    )
    
    email = models.EmailField(
        unique=True,
        db_index=True,
        verbose_name='Email',
        help_text='Email do usuário (usado como username)'
    )
    
    tenant = models.ForeignKey(
        Tenant,
        on_delete=models.PROTECT,
        related_name='users',
        null=True,
        blank=True,
        verbose_name='Tenant',
        help_text='Loja/Empresa do usuário (None apenas para ADMIN_MASTER)'
    )
    
    role = models.CharField(
        max_length=15,
        choices=UserRole.choices,
        default=UserRole.OPERADOR,
        verbose_name='Role',
        help_text='Função do usuário no sistema'
    )
    
    whatsapp_number = models.CharField(
        max_length=20,
        unique=True,
        db_index=True,
        null=True,
        blank=True,
        verbose_name='Número WhatsApp',
        help_text='Número do WhatsApp no formato internacional (ex: 5541999999999)'
    )
    
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name='Data de Criação',
        help_text='Data e hora em que o usuário foi criado'
    )
    
    updated_at = models.DateTimeField(
        auto_now=True,
        verbose_name='Data de Atualização',
        help_text='Data e hora da última atualização do usuário'
    )
    
    # Usa o manager customizado
    objects = UserManager()
    
    # Usa email como username
    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = []
    
    class Meta:
        verbose_name = 'Usuário'
        verbose_name_plural = 'Usuários'
        ordering = ['email']
        indexes = [
            models.Index(fields=['email']),
            models.Index(fields=['tenant', 'role']),
            models.Index(fields=['whatsapp_number']),
        ]
    
    def clean(self):
        """
        Validação adicional do modelo antes de salvar.
        
        Garante consistência entre role e tenant:
        - ADMIN_MASTER não pode ter tenant
        - Outros roles devem ter tenant
        """
        super().clean()
        
        if self.role == UserRole.ADMIN_MASTER and self.tenant_id:
            raise ValidationError({
                'tenant': 'Administradores Master não podem ter tenant associado.'
            })
        
        if self.role != UserRole.ADMIN_MASTER and not self.tenant_id:
            raise ValidationError({
                'tenant': 'Usuários não-master devem ter um tenant associado.'
            })
    
    def save(self, *args, **kwargs):
        """
        Sobrescreve save para garantir validações e definir username igual ao email.
        """
        # Garante que username seja igual ao email
        if not self.username or self.username != self.email:
            self.username = self.email
        
        self.full_clean()  # Chama clean() para validações
        super().save(*args, **kwargs)
    
    @property
    def is_master(self) -> bool:
        """
        Verifica se o usuário é ADMIN_MASTER.
        
        Returns:
            True se for ADMIN_MASTER, False caso contrário
        """
        return self.role == UserRole.ADMIN_MASTER
    
    def set_current_tenant(self) -> None:
        """
        Define o tenant atual no contexto thread-local.
        
        Útil para garantir que queries subsequentes sejam
        automaticamente filtradas pelo tenant do usuário.
        """
        if self.tenant_id:
            set_current_tenant(self.tenant_id)
        elif not self.is_master:
            # Se não for master e não tiver tenant, limpa o contexto
            from core.utils.tenant_context import clear_tenant
            clear_tenant()
    
    def __str__(self) -> str:
        """Representação string do usuário."""
        tenant_info = f" - {self.tenant.name}" if self.tenant else " [MASTER]"
        return f"{self.email} ({self.get_role_display()}){tenant_info}"

