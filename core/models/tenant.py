"""
Modelo Tenant - Representa uma Loja/Empresa no sistema.

Cada tenant é isolado completamente no sistema, sendo a base
do multi-tenancy do Caixô.
"""

import uuid
from django.core.exceptions import ValidationError
from django.db import models
from django.core.validators import MinValueValidator, MaxValueValidator

from core.utils.cnpj import validate_cnpj, clean_cnpj, format_cnpj


class TenantPlan(models.TextChoices):
    """Planos disponíveis para os tenants."""
    BASIC = 'BASIC', 'Básico'
    PRO = 'PRO', 'Profissional'


class TenantStatus(models.TextChoices):
    """Status do tenant no sistema."""
    ACTIVE = 'ACTIVE', 'Ativo'
    INACTIVE = 'INACTIVE', 'Inativo'
    TRIAL = 'TRIAL', 'Período de Teste'


def validate_cnpj_field(cnpj: str) -> None:
    """
    Validador customizado para o campo CNPJ.
    
    Args:
        cnpj: CNPJ para validação
        
    Raises:
        ValidationError: Se o CNPJ for inválido
    """
    if not validate_cnpj(cnpj):
        raise ValidationError('CNPJ inválido. Verifique o número informado.')


class Tenant(models.Model):
    """
    Modelo que representa uma Loja/Empresa (Tenant) no sistema.
    
    Cada tenant possui isolamento total de dados e configurações
    próprias de faturamento e plano.
    
    Características:
    - UUID como chave primária (não sequencial para segurança)
    - CNPJ único e validado
    - Configurações de faturamento (semanal e mensal)
    - Status e plano de assinatura
    """
    
    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
        verbose_name='ID',
        help_text='Identificador único (UUID) do tenant'
    )
    
    name = models.CharField(
        max_length=255,
        verbose_name='Razão Social',
        help_text='Nome completo da empresa/loja'
    )
    
    cnpj = models.CharField(
        max_length=18,
        unique=True,
        db_index=True,
        validators=[validate_cnpj_field],
        verbose_name='CNPJ',
        help_text='CNPJ da empresa (será validado automaticamente)'
    )
    
    plan = models.CharField(
        max_length=10,
        choices=TenantPlan.choices,
        default=TenantPlan.BASIC,
        verbose_name='Plano',
        help_text='Plano de assinatura do tenant'
    )
    
    status = models.CharField(
        max_length=10,
        choices=TenantStatus.choices,
        default=TenantStatus.ACTIVE,
        verbose_name='Status',
        help_text='Status atual do tenant no sistema'
    )
    
    billing_day_weekly = models.IntegerField(
        default=1,
        validators=[MinValueValidator(0), MaxValueValidator(6)],
        verbose_name='Dia da Semana para Faturamento Semanal',
        help_text='0=Domingo, 1=Segunda, 2=Terça, ..., 6=Sábado'
    )
    
    billing_day_monthly = models.IntegerField(
        default=5,
        validators=[MinValueValidator(1), MaxValueValidator(31)],
        verbose_name='Dia do Mês para Faturamento Mensal',
        help_text='Dia do mês (1-31) para solicitação de faturamento mensal'
    )
    
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name='Data de Criação',
        help_text='Data e hora em que o tenant foi criado'
    )
    
    updated_at = models.DateTimeField(
        auto_now=True,
        verbose_name='Data de Atualização',
        help_text='Data e hora da última atualização do tenant'
    )
    
    class Meta:
        verbose_name = 'Tenant'
        verbose_name_plural = 'Tenants'
        ordering = ['name']
        indexes = [
            models.Index(fields=['cnpj']),
            models.Index(fields=['status']),
            models.Index(fields=['plan']),
        ]
    
    def clean(self):
        """
        Validação adicional do modelo antes de salvar.
        
        Garante que o CNPJ seja limpo e validado.
        """
        super().clean()
        if self.cnpj:
            # Limpa o CNPJ removendo caracteres especiais
            self.cnpj = clean_cnpj(self.cnpj)
            # Valida o CNPJ
            if not validate_cnpj(self.cnpj):
                raise ValidationError({'cnpj': 'CNPJ inválido. Verifique o número informado.'})
    
    def save(self, *args, **kwargs):
        """
        Sobrescreve save para garantir que o CNPJ seja limpo antes de salvar.
        """
        self.full_clean()  # Chama clean() que valida e limpa o CNPJ
        super().save(*args, **kwargs)
    
    @property
    def cnpj_formatted(self) -> str:
        """
        Retorna o CNPJ formatado (XX.XXX.XXX/XXXX-XX).
        
        Returns:
            CNPJ formatado
        """
        return format_cnpj(self.cnpj)
    
    def __str__(self) -> str:
        """Representação string do tenant."""
        return f"{self.name} ({self.cnpj_formatted})"

