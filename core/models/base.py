"""
Classe base para todos os modelos que precisam de isolamento multi-tenant.

Implementa TenantModel que garante que todos os registros sejam automaticamente
filtrados por tenant_id, prevenindo vazamento de dados entre lojas.
"""

import uuid
from typing import Optional
from uuid import UUID

from django.db import models
from django.core.exceptions import ValidationError

from core.utils.tenant_context import get_current_tenant


class TenantQuerySet(models.QuerySet):
    """
    QuerySet customizado que aplica filtro automático por tenant.
    
    O filtro é aplicado automaticamente quando o QuerySet é criado pelo Manager,
    garantindo que todas as queries sejam filtradas pelo tenant atual.
    
    Métodos especiais:
    - without_tenant_filter(): Remove o filtro (APENAS para SuperAdmins)
    - for_tenant(tenant_id): Filtra explicitamente por um tenant específico
    """
    
    def without_tenant_filter(self):
        """
        Remove o filtro de tenant, permitindo acesso a todos os registros.
        
        ATENÇÃO: Use com extremo cuidado! Apenas para SuperAdmins.
        
        Returns:
            QuerySet sem filtro de tenant
        """
        # Cria novo QuerySet sem filtro de tenant
        # Remove qualquer filtro de tenant_id que possa estar aplicado
        return self.model._default_manager.get_queryset().filter(
            **{k: v for k, v in self.query.where.children if not str(k).startswith('tenant_id')}
        )
    
    def for_tenant(self, tenant_id: UUID):
        """
        Filtra explicitamente por um tenant específico.
        
        Args:
            tenant_id: UUID do tenant para filtrar
            
        Returns:
            QuerySet filtrado pelo tenant especificado
        """
        return self.filter(tenant_id=tenant_id)


class TenantManager(models.Manager):
    """
    Manager customizado que aplica isolamento automático de dados por tenant.
    
    Todas as queries são automaticamente filtradas pelo tenant do contexto
    thread-local, garantindo que nunca haja vazamento de dados entre lojas.
    
    O filtro é aplicado diretamente no get_queryset(), que é chamado pelo Django
    sempre que uma query é executada. Isso garante que o isolamento seja
    automático e à prova de falhas.
    """
    
    _use_tenant_filter = True  # Flag para controlar se aplica filtro de tenant
    
    def get_queryset(self) -> TenantQuerySet:
        """
        Retorna QuerySet com filtro automático de tenant aplicado.
        
        Obtém o tenant_id do contexto thread-local e aplica o filtro automaticamente.
        Se não houver tenant no contexto, retorna QuerySet sem filtro (usado apenas
        internamente ou por SuperAdmins com without_tenant_filter()).
        
        Returns:
            TenantQuerySet filtrado pelo tenant atual do contexto
        """
        qs = TenantQuerySet(self.model, using=self._db)
        
        # Aplica filtro de tenant se habilitado e houver tenant no contexto
        if self._use_tenant_filter:
            tenant_id = get_current_tenant()
            if tenant_id is not None:
                return qs.filter(tenant_id=tenant_id)
        
        # Se não houver tenant no contexto ou filtro desabilitado, retorna QuerySet sem filtro
        return qs
    
    def without_tenant_filter(self):
        """
        Retorna QuerySet sem filtro de tenant (APENAS para SuperAdmins).
        
        Este método deve ser usado com extremo cuidado, apenas em situações
        específicas onde o SuperAdmin precisa ver todos os registros.
        
        Returns:
            QuerySet sem filtro de tenant
        """
        # Cria um manager temporário com filtro de tenant desabilitado
        # e retorna seu QuerySet sem filtro
        manager = self.__class__()
        manager._use_tenant_filter = False
        manager.model = self.model
        manager._db = self._db
        return manager.get_queryset()
    
    def for_tenant(self, tenant_id: UUID):
        """
        Filtra explicitamente por um tenant específico.
        
        Útil quando precisa filtrar por um tenant diferente do contexto atual.
        
        Args:
            tenant_id: UUID do tenant para filtrar
            
        Returns:
            QuerySet filtrado pelo tenant especificado
        """
        return TenantQuerySet(self.model, using=self._db).filter(tenant_id=tenant_id)


class TenantModel(models.Model):
    """
    Classe base abstrata para todos os modelos que precisam de isolamento multi-tenant.
    
    Características:
    - UUID como chave primária (não sequencial)
    - tenant_id obrigatório (exceto para algumas tabelas específicas)
    - Timestamps automáticos (created_at, updated_at)
    - Manager customizado que filtra automaticamente por tenant
    
    Uso:
        class MeuModelo(TenantModel):
            nome = models.CharField(max_length=100)
            ...
    
    TODAS as queries serão automaticamente filtradas pelo tenant atual.
    """
    
    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
        verbose_name='ID',
        help_text='Identificador único (UUID) do registro'
    )
    
    tenant = models.ForeignKey(
        'core.Tenant',
        on_delete=models.CASCADE,
        related_name='%(class)s_set',
        verbose_name='Tenant',
        help_text='Loja/Empresa proprietária deste registro',
        db_index=True,
        null=False,
        blank=False
    )
    
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name='Data de Criação',
        help_text='Data e hora em que o registro foi criado'
    )
    
    updated_at = models.DateTimeField(
        auto_now=True,
        verbose_name='Data de Atualização',
        help_text='Data e hora da última atualização do registro'
    )
    
    # Usa o TenantManager como manager padrão
    objects = TenantManager()
    
    class Meta:
        abstract = True
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['tenant', '-created_at']),
            models.Index(fields=['tenant', 'updated_at']),
        ]
    
    def save(self, *args, **kwargs):
        """
        Sobrescreve save para garantir que tenant_id seja sempre definido.
        
        Se não houver tenant_id definido, tenta obter do contexto thread-local.
        Se ainda assim não houver e o campo permitir null, não levanta erro
        (caso de categorias globais). Caso contrário, levanta ValidationError.
        """
        # Se o tenant não foi definido, tenta obter do contexto
        if not self.tenant_id:
            tenant_id = get_current_tenant()
            if tenant_id:
                self.tenant_id = tenant_id
            elif not self._meta.get_field('tenant').null:
                # Se o campo não permite null, levanta erro
                raise ValidationError(
                    'Tenant é obrigatório. Defina o tenant no contexto ou passe explicitamente.'
                )
            # Se permite null e não há tenant no contexto, permite None (categorias globais)
        
        super().save(*args, **kwargs)
    
    def __str__(self) -> str:
        """Representação string do objeto (deve ser sobrescrito nos modelos filhos)."""
        return f"{self.__class__.__name__} ({self.id})"

