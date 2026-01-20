"""
Modelos do domínio financeiro do Caixô.

Implementa a estrutura completa para gestão financeira multi-tenant:
- Category e Subcategory: Hierarquia de categorias de despesas
- Transaction: Fato gerador (Competência/DRE)
- Installment: Movimentação financeira (Caixa/Fluxo)
- ParsingSession: Sessão temporária de parsing pela IA
- LearnedRule: Regras aprendidas por tenant para categorização automática

Características:
- Todos os modelos herdam de TenantModel (isolamento automático)
- UUID como chave primária (não sequencial)
- Dualidade contábil rigorosa (Competência vs Caixa)
- Documentação completa em Português-BR
"""

import uuid
from decimal import Decimal
from typing import Optional
from datetime import date

from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models
from django.utils import timezone

from core.models.base import TenantModel


class CategoryType(models.TextChoices):
    """Tipos de categoria de despesa."""
    FIXA = 'FIXA', 'Despesa Fixa'
    VARIAVEL = 'VARIAVEL', 'Despesa Variável'
    INVESTIMENTO = 'INVESTIMENTO', 'Investimento'
    ESTOQUE = 'ESTOQUE', 'Estoque'


class InstallmentStatus(models.TextChoices):
    """Status da parcela."""
    PENDENTE = 'PENDENTE', 'Pendente'
    PAGO = 'PAGO', 'Pago'


class TransactionType(models.TextChoices):
    """Tipo de transação financeira."""
    RECEITA = 'RECEITA', 'Receita'
    DESPESA = 'DESPESA', 'Despesa'


class SalesChannel(TenantModel):
    """
    Canal de Venda - Usado para categorizar receitas.
    
    Representa os diferentes canais pelos quais a empresa recebe receitas.
    Exemplos: Delivery (iFood, Uber Eats), Balcão, Mesa, Delivery Próprio, etc.
    
    Características:
    - Pode ser global (tenant=None) ou específico do tenant
    - Usado apenas para transações de receita
    """
    
    name = models.CharField(
        max_length=255,
        db_index=True,
        verbose_name='Nome',
        help_text='Nome do canal de venda (ex: iFood, Balcão, Delivery Próprio)'
    )
    
    description = models.TextField(
        blank=True,
        null=True,
        verbose_name='Descrição',
        help_text='Descrição adicional do canal de venda'
    )
    
    # Sobrescreve tenant do TenantModel para permitir canais globais
    tenant = models.ForeignKey(
        'core.Tenant',
        on_delete=models.CASCADE,
        related_name='sales_channels',
        null=True,
        blank=True,
        verbose_name='Tenant',
        help_text='Tenant proprietário (None para canais globais)',
        db_index=True
    )
    
    active = models.BooleanField(
        default=True,
        verbose_name='Ativo',
        help_text='Se o canal está ativo e pode ser usado'
    )
    
    class Meta:
        verbose_name = 'Canal de Venda'
        verbose_name_plural = 'Canais de Venda'
        ordering = ['name']
        indexes = [
            models.Index(fields=['tenant', 'active']),
            models.Index(fields=['name']),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=['tenant', 'name'],
                name='unique_sales_channel_per_tenant',
                condition=models.Q(tenant__isnull=False)
            ),
            models.UniqueConstraint(
                fields=['name'],
                name='unique_global_sales_channel',
                condition=models.Q(tenant__isnull=True)
            ),
        ]
    
    def __str__(self) -> str:
        """Representação string do canal de venda."""
        tenant_info = f" [{self.tenant.name}]" if self.tenant else " [GLOBAL]"
        return f"{self.name}{tenant_info}"


class Category(TenantModel):
    """
    Categoria de despesa no sistema.
    
    Representa o nível superior da hierarquia de categorização
    de despesas. Pode ser global (tenant=None) ou específica de um tenant.
    
    Características:
    - tenant pode ser None para categorias globais do Glossário
    - Tipo definido por CategoryType (FIXA, VARIAVEL, INVESTIMENTO, ESTOQUE)
    - Usado para agrupamento no DRE e análises financeiras
    """
    
    name = models.CharField(
        max_length=255,
        db_index=True,
        verbose_name='Nome',
        help_text='Nome da categoria (ex: Despesa Fixa, Estoque)'
    )
    
    type = models.CharField(
        max_length=20,
        choices=CategoryType.choices,
        verbose_name='Tipo',
        help_text='Tipo de categoria para classificação financeira'
    )
    
    # Sobrescreve tenant do TenantModel para permitir categorias globais
    tenant = models.ForeignKey(
        'core.Tenant',
        on_delete=models.CASCADE,
        related_name='categories',
        null=True,
        blank=True,
        verbose_name='Tenant',
        help_text='Tenant proprietário (None para categorias globais do Glossário)',
        db_index=True
    )
    
    class Meta:
        verbose_name = 'Categoria'
        verbose_name_plural = 'Categorias'
        ordering = ['type', 'name']
        indexes = [
            models.Index(fields=['tenant', 'type']),
            models.Index(fields=['type', 'name']),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=['tenant', 'name'],
                name='unique_category_per_tenant',
                condition=models.Q(tenant__isnull=False)
            ),
            models.UniqueConstraint(
                fields=['name'],
                name='unique_global_category',
                condition=models.Q(tenant__isnull=True)
            ),
        ]
    
    def __str__(self) -> str:
        """Representação string da categoria."""
        tenant_info = f" [{self.tenant.name}]" if self.tenant else " [GLOBAL]"
        return f"{self.name} ({self.get_type_display()}){tenant_info}"


class Subcategory(TenantModel):
    """
    Subcategoria de despesa no sistema.
    
    Representa o nível inferior da hierarquia, vinculada a uma Category.
    Permite categorização mais detalhada das despesas.
    
    Exemplo:
    - Category: "Despesa Fixa"
      - Subcategory: "Aluguel"
      - Subcategory: "Luz"
      - Subcategory: "Água"
    
    Características:
    - tenant pode ser None para subcategorias globais do Glossário
    - Vinculada a uma Category obrigatória
    """
    
    name = models.CharField(
        max_length=255,
        db_index=True,
        verbose_name='Nome',
        help_text='Nome da subcategoria (ex: Aluguel, Luz, Água)'
    )
    
    category = models.ForeignKey(
        Category,
        on_delete=models.CASCADE,
        related_name='subcategories',
        verbose_name='Categoria',
        help_text='Categoria pai desta subcategoria'
    )
    
    # Sobrescreve tenant do TenantModel para permitir subcategorias globais
    tenant = models.ForeignKey(
        'core.Tenant',
        on_delete=models.CASCADE,
        related_name='subcategories',
        null=True,
        blank=True,
        verbose_name='Tenant',
        help_text='Tenant proprietário (None para subcategorias globais do Glossário)',
        db_index=True
    )
    
    class Meta:
        verbose_name = 'Subcategoria'
        verbose_name_plural = 'Subcategorias'
        ordering = ['category', 'name']
        indexes = [
            models.Index(fields=['tenant', 'category']),
            models.Index(fields=['category', 'name']),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=['tenant', 'category', 'name'],
                name='unique_subcategory_per_tenant',
                condition=models.Q(tenant__isnull=False)
            ),
            models.UniqueConstraint(
                fields=['category', 'name'],
                name='unique_global_subcategory',
                condition=models.Q(tenant__isnull=True)
            ),
        ]
    
    def clean(self):
        """Validação adicional do modelo."""
        super().clean()
        # Garante que se a categoria é global, a subcategoria também seja
        if self.category.tenant is None and self.tenant is not None:
            raise ValidationError({
                'tenant': 'Subcategorias de categorias globais devem ser globais também.'
            })
        # Garante que subcategorias de tenant tenham mesma categoria do tenant
        if self.tenant and self.category.tenant and self.category.tenant != self.tenant:
            raise ValidationError({
                'category': 'A categoria deve pertencer ao mesmo tenant da subcategoria.'
            })
    
    def __str__(self) -> str:
        """Representação string da subcategoria."""
        tenant_info = f" [{self.tenant.name}]" if self.tenant else " [GLOBAL]"
        return f"{self.name} -> {self.category.name}{tenant_info}"


class Transaction(TenantModel):
    """
    Transação financeira - Fato Gerador (Competência/DRE).
    
    Representa o fato econômico, independente do fluxo de caixa.
    Usado para construção do DRE (Demonstração de Resultado do Exercício).
    
    Características:
    - competence_date: Data de competência (mês/ano) para DRE
    - Pode ter múltiplas Installments (parcelas)
    - Valor bruto da transação
    - Categorização obrigatória (Category + Subcategory)
    
    Dualidade Contábil:
    - Transaction = Competência (quando ocorreu o fato gerador)
    - Installment = Caixa (quando houve movimentação bancária)
    
    Exemplo:
    - Transaction: Conta de luz de janeiro (competence_date: 2025-01-01)
      - Installment 1: Vencimento 05/02, Pago em 03/02
      - Installment 2: Vencimento 05/03, Pago em 10/03
    """
    
    description = models.TextField(
        verbose_name='Descrição',
        help_text='Descrição detalhada da transação',
        blank=True,
        null=True
    )
    
    amount = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0.01'))],
        verbose_name='Valor Bruto',
        help_text='Valor total bruto da transação'
    )
    
    transaction_type = models.CharField(
        max_length=10,
        choices=TransactionType.choices,
        default=TransactionType.DESPESA,  # Default temporário para migration
        verbose_name='Tipo de Transação',
        help_text='Se é uma receita ou despesa'
    )
    
    category = models.ForeignKey(
        Category,
        on_delete=models.PROTECT,
        related_name='transactions',
        null=True,
        blank=True,
        verbose_name='Categoria',
        help_text='Categoria da transação (apenas para despesas)'
    )
    
    subcategory = models.ForeignKey(
        Subcategory,
        on_delete=models.PROTECT,
        related_name='transactions',
        null=True,
        blank=True,
        verbose_name='Subcategoria',
        help_text='Subcategoria detalhada da transação (apenas para despesas)'
    )
    
    sales_channel = models.ForeignKey(
        'SalesChannel',
        on_delete=models.PROTECT,
        related_name='transactions',
        null=True,
        blank=True,
        verbose_name='Canal de Venda',
        help_text='Canal de venda da receita (apenas para receitas)'
    )
    
    competence_date = models.DateField(
        verbose_name='Data de Competência',
        help_text='Data de competência (mês/ano) para DRE - Quando ocorreu o fato gerador. Para receitas, é a data de início do período.'
    )
    
    competence_date_end = models.DateField(
        null=True,
        blank=True,
        verbose_name='Data de Fim do Período',
        help_text='Data de fim do período de competência (apenas para receitas). Se não informada, considera apenas a data de início.'
    )
    
    cash_date = models.DateField(
        null=True,
        blank=True,
        verbose_name='Data de Caixa',
        help_text='Data em que o dinheiro entrou/saiu (apenas para receitas, se diferente da competência)'
    )
    
    supplier = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        db_index=True,
        verbose_name='Fornecedor',
        help_text='Nome do fornecedor/prestador de serviço (apenas para despesas)'
    )
    
    class Meta:
        verbose_name = 'Transação'
        verbose_name_plural = 'Transações'
        ordering = ['-competence_date', '-created_at']
        indexes = [
            models.Index(fields=['tenant', '-competence_date']),
            models.Index(fields=['tenant', 'transaction_type']),
            models.Index(fields=['tenant', 'category']),
            models.Index(fields=['tenant', 'subcategory']),
            models.Index(fields=['tenant', 'sales_channel']),
            models.Index(fields=['competence_date']),
        ]
    
    def clean(self):
        """Validação adicional do modelo."""
        super().clean()
        
        # Validações específicas por tipo de transação
        if self.transaction_type == TransactionType.DESPESA:
            # Despesas devem ter categoria e subcategoria
            if not self.category:
                raise ValidationError({
                    'category': 'Categoria é obrigatória para despesas.'
                })
            if not self.subcategory:
                raise ValidationError({
                    'subcategory': 'Subcategoria é obrigatória para despesas.'
                })
            # Garante que subcategoria pertença à categoria informada
            if self.subcategory and self.category and self.subcategory.category != self.category:
                raise ValidationError({
                    'subcategory': 'A subcategoria deve pertencer à categoria informada.'
                })
            # Despesas não devem ter canal de venda
            if self.sales_channel:
                raise ValidationError({
                    'sales_channel': 'Canal de venda não deve ser usado para despesas.'
                })
        
        elif self.transaction_type == TransactionType.RECEITA:
            # Receitas devem ter canal de venda
            if not self.sales_channel:
                raise ValidationError({
                    'sales_channel': 'Canal de venda é obrigatório para receitas.'
                })
            # Receitas não devem ter categoria/subcategoria
            # Limpa os campos se vierem preenchidos (em vez de levantar erro)
            if self.category:
                self.category = None
            if self.subcategory:
                self.subcategory = None
            # Valida que data de fim seja maior ou igual à data de início
            if self.competence_date_end and self.competence_date:
                if self.competence_date_end < self.competence_date:
                    raise ValidationError({
                        'competence_date_end': 'A data de fim do período deve ser maior ou igual à data de início.'
                    })
    
    @property
    def total_installments(self) -> Decimal:
        """
        Calcula o valor total de todas as parcelas.
        
        Returns:
            Decimal com o valor total das parcelas
        """
        return self.installments.aggregate(
            total=models.Sum('amount')
        )['total'] or Decimal('0.00')
    
    @property
    def total_paid(self) -> Decimal:
        """
        Calcula o valor total já pago (parcelas com status PAGO).
        
        Returns:
            Decimal com o valor total pago
        """
        return self.installments.filter(status='PAGO').aggregate(
            total=models.Sum('amount')
        )['total'] or Decimal('0.00')
    
    def __str__(self) -> str:
        """Representação string da transação."""
        desc = self.description or "Sem descrição"
        return f"{desc} - R$ {self.amount} ({self.competence_date.strftime('%m/%Y')})"


class Installment(TenantModel):
    """
    Parcela financeira - Movimentação de Caixa (Fluxo de Caixa).
    
    Representa uma parcela da Transaction, com data de vencimento e pagamento.
    Usado para construção do Fluxo de Caixa.
    
    Características:
    - due_date: Data de vencimento (caixa esperado)
    - payment_date: Data de pagamento efetivo (caixa realizado)
    - amount: Valor líquido da parcela
    - penalty_amount: Multas e juros (se houver)
    - status: PENDENTE ou PAGO
    
    Dualidade Contábil:
    - Transaction.competence_date = Quando ocorreu (DRE)
    - Installment.payment_date = Quando pagou (Caixa)
    
    Exemplo:
    - Transaction: Aluguel de janeiro
      - Installment: Vencimento 05/01, Pago em 03/01, Status: PAGO
    """
    
    transaction = models.ForeignKey(
        Transaction,
        on_delete=models.CASCADE,
        related_name='installments',
        verbose_name='Transação',
        help_text='Transação à qual esta parcela pertence'
    )
    
    due_date = models.DateField(
        verbose_name='Data de Vencimento',
        help_text='Data em que a parcela vence (caixa esperado)'
    )
    
    payment_date = models.DateField(
        null=True,
        blank=True,
        verbose_name='Data de Pagamento',
        help_text='Data em que a parcela foi paga (caixa realizado)'
    )
    
    amount = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0.01'))],
        verbose_name='Valor Líquido',
        help_text='Valor líquido da parcela (sem multas/juros)'
    )
    
    penalty_amount = models.DecimalField(
        max_digits=15,
        decimal_places=2,
        default=Decimal('0.00'),
        validators=[MinValueValidator(Decimal('0.00'))],
        verbose_name='Multas e Juros',
        help_text='Valor de multas e juros pagos nesta parcela'
    )
    
    status = models.CharField(
        max_length=10,
        choices=InstallmentStatus.choices,
        default=InstallmentStatus.PENDENTE,
        verbose_name='Status',
        help_text='Status atual da parcela'
    )
    
    class Meta:
        verbose_name = 'Parcela'
        verbose_name_plural = 'Parcelas'
        ordering = ['due_date', '-created_at']
        indexes = [
            models.Index(fields=['tenant', 'due_date']),
            models.Index(fields=['tenant', 'payment_date']),
            models.Index(fields=['tenant', 'status']),
            models.Index(fields=['due_date', 'status']),
        ]
    
    def clean(self):
        """Validação adicional do modelo."""
        super().clean()
        # Se está pago, deve ter data de pagamento
        if self.status == InstallmentStatus.PAGO and not self.payment_date:
            raise ValidationError({
                'payment_date': 'Parcelas pagas devem ter data de pagamento informada.'
            })
        # Se não está pago, não deve ter data de pagamento
        if self.status == InstallmentStatus.PENDENTE and self.payment_date:
            raise ValidationError({
                'payment_date': 'Parcelas pendentes não devem ter data de pagamento.'
            })
        # Data de pagamento não pode ser anterior ao vencimento (em geral)
        # (mas permitimos para casos especiais de pagamento antecipado)
        if self.payment_date and self.due_date and self.payment_date < self.due_date:
            # Não levantamos erro, apenas avisamos (pode ser pagamento antecipado)
            pass
    
    def save(self, *args, **kwargs):
        """
        Sobrescreve save para sincronizar status com payment_date.
        
        Se payment_date for definido, automaticamente marca como PAGO.
        Se payment_date for removido, marca como PENDENTE.
        """
        # Sincroniza status com payment_date
        if self.payment_date and self.status == InstallmentStatus.PENDENTE:
            self.status = InstallmentStatus.PAGO
        elif not self.payment_date and self.status == InstallmentStatus.PAGO:
            self.status = InstallmentStatus.PENDENTE
        
        super().save(*args, **kwargs)
    
    def is_overdue(self) -> bool:
        """
        Verifica se a parcela está vencida.
        
        Uma parcela está vencida se:
        - A data atual é maior que a data de vencimento
        - E o status é PENDENTE (não foi paga)
        
        Returns:
            True se a parcela está vencida, False caso contrário
        """
        if self.status == InstallmentStatus.PAGO:
            return False
        
        today = timezone.now().date()
        return today > self.due_date
    
    def mark_as_paid(self, payment_date: date, paid_amount: Optional[Decimal] = None) -> None:
        """
        Marca a parcela como paga, calculando automaticamente multas/juros se necessário.
        
        Se o valor pago for maior que o valor líquido da parcela, a diferença
        é automaticamente atribuída como penalty_amount (multas/juros).
        
        Args:
            payment_date: Data em que o pagamento foi efetuado
            paid_amount: Valor total pago (se None, usa o amount original)
            
        Raises:
            ValidationError: Se payment_date for inválida ou paid_amount for negativo
        """
        if payment_date is None:
            raise ValidationError('Data de pagamento é obrigatória.')
        
        if paid_amount is not None and paid_amount < Decimal('0.00'):
            raise ValidationError('Valor pago não pode ser negativo.')
        
        # Define a data de pagamento
        self.payment_date = payment_date
        
        # Se foi informado um valor pago, calcula a diferença como multa/juros
        if paid_amount is not None:
            if paid_amount >= self.amount:
                # Se pagou mais que o valor líquido, a diferença é multa/juros
                self.penalty_amount = paid_amount - self.amount
            else:
                # Se pagou menos, ajusta o amount (pode ser desconto negociado)
                self.amount = paid_amount
                self.penalty_amount = Decimal('0.00')
        else:
            # Se não foi informado valor, usa o amount original
            # e mantém penalty_amount como está (ou zero se não foi definido)
            if self.penalty_amount is None:
                self.penalty_amount = Decimal('0.00')
        
        # Marca como pago
        self.status = InstallmentStatus.PAGO
        
        # Salva as alterações
        self.save()
    
    @property
    def total_amount(self) -> Decimal:
        """
        Calcula o valor total da parcela (valor líquido + multas/juros).
        
        Returns:
            Decimal com o valor total (amount + penalty_amount)
        """
        return self.amount + self.penalty_amount
    
    def __str__(self) -> str:
        """Representação string da parcela."""
        status_icon = "✓" if self.status == InstallmentStatus.PAGO else "⏳"
        desc = self.transaction.description or "Sem descrição"
        return f"{status_icon} {desc} - R$ {self.amount} (Venc: {self.due_date.strftime('%d/%m/%Y')})"


class ParsingSessionStatus(models.TextChoices):
    """Status da sessão de parsing."""
    PENDING = 'PENDING', 'Pendente'
    CONFIRMED = 'CONFIRMED', 'Confirmado'
    CANCELED = 'CANCELED', 'Cancelado'


def invoice_upload_path(instance, filename: str) -> str:
    """
    Gera o caminho para armazenar comprovantes/invoices por tenant.
    
    Estrutura: media/tenants/{tenant_id}/invoices/{session_id}_{filename}
    
    Nota: Esta função é chamada automaticamente pelo Django quando um arquivo
    é salvo no campo ImageField. O Django cria a estrutura de pastas automaticamente.
    
    Args:
        instance: Instância do ParsingSession (deve ter id e tenant_id)
        filename: Nome original do arquivo
        
    Returns:
        Caminho relativo para armazenamento do arquivo (sem o prefixo MEDIA_ROOT)
    """
    # Extrai extensão do arquivo
    extension = filename.split('.')[-1] if '.' in filename else 'jpg'
    
    # Gera nome único baseado no session_id
    # Se instance ainda não tem id (ainda não foi salvo), usa timestamp
    if hasattr(instance, 'id') and instance.id:
        session_id = str(instance.id)
        # Usa apenas os primeiros 8 caracteres do UUID para nome mais curto
        session_id_short = session_id.replace('-', '')[:8]
        unique_filename = f"{session_id_short}.{extension}"
    else:
        # Fallback: usa timestamp se ainda não tiver ID
        from django.utils import timezone
        timestamp = timezone.now().strftime('%Y%m%d_%H%M%S')
        unique_filename = f"{timestamp}.{extension}"
    
    return f"tenants/{instance.tenant_id}/invoices/{unique_filename}"


class ParsingSession(TenantModel):
    """
    Sessão temporária de parsing pela IA.
    
    Armazena o resultado do parsing de uma mensagem (WhatsApp) antes
    da confirmação do usuário. Permite revisão e correção antes de
    criar Transaction e Installment definitivos.
    
    Características:
    - raw_text: Texto original recebido (via WhatsApp) ou transcrito (de áudio)
    - extracted_json: JSON extraído pela IA com os dados estruturados
    - image_url: URL da imagem enviada (comprovante/nota fiscal) - opcional
    - image_file: Arquivo de imagem armazenado localmente - opcional
    - audio_url: URL do áudio enviado (mensagem de voz) - opcional
    - status: Status da sessão (PENDING, CONFIRMED, CANCELED)
    - expires_at: Data de expiração da sessão (limpeza automática)
    """
    
    raw_text = models.TextField(
        verbose_name='Texto Original',
        help_text='Texto original da mensagem recebida (WhatsApp) ou transcrito de áudio'
    )
    
    extracted_json = models.JSONField(
        verbose_name='JSON Extraído',
        help_text='Dados estruturados extraídos pela IA (formato JSON)'
    )
    
    image_url = models.URLField(
        max_length=500,
        null=True,
        blank=True,
        verbose_name='URL da Imagem',
        help_text='URL da imagem (comprovante/nota fiscal) recebida via WhatsApp'
    )
    
    image_file = models.ImageField(
        upload_to=invoice_upload_path,
        null=True,
        blank=True,
        verbose_name='Arquivo de Imagem',
        help_text='Arquivo de imagem armazenado localmente em media/tenants/{tenant_id}/invoices/'
    )
    
    audio_url = models.URLField(
        max_length=500,
        null=True,
        blank=True,
        verbose_name='URL do Áudio',
        help_text='URL do áudio (mensagem de voz) recebido via WhatsApp'
    )
    
    status = models.CharField(
        max_length=10,
        choices=ParsingSessionStatus.choices,
        default=ParsingSessionStatus.PENDING,
        verbose_name='Status',
        help_text='Status atual da sessão de parsing'
    )
    
    expires_at = models.DateTimeField(
        verbose_name='Expira em',
        help_text='Data e hora de expiração desta sessão (para limpeza automática)'
    )
    
    confirmed_transaction = models.ForeignKey(
        Transaction,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='parsing_sessions',
        verbose_name='Transação Confirmada',
        help_text='Transação criada após confirmação (se houver)'
    )
    
    class Meta:
        verbose_name = 'Sessão de Parsing'
        verbose_name_plural = 'Sessões de Parsing'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['tenant', '-created_at']),
            models.Index(fields=['tenant', 'status']),
            models.Index(fields=['expires_at']),
        ]
    
    def confirm(self, transaction: Transaction) -> None:
        """
        Confirma a sessão e vincula à transação criada.
        
        Args:
            transaction: Instância da Transaction criada após confirmação
        """
        self.status = ParsingSessionStatus.CONFIRMED
        self.confirmed_transaction = transaction
        self.save()
    
    def cancel(self) -> None:
        """
        Cancela a sessão de parsing.
        """
        self.status = ParsingSessionStatus.CANCELED
        self.save()
    
    @property
    def is_confirmed(self) -> bool:
        """
        Verifica se a sessão foi confirmada.
        
        Returns:
            True se o status for CONFIRMED, False caso contrário
        """
        return self.status == ParsingSessionStatus.CONFIRMED
    
    def __str__(self) -> str:
        """Representação string da sessão."""
        status_display = self.get_status_display()
        return f"Sessão {self.id} - {status_display} ({self.created_at.strftime('%d/%m/%Y %H:%M')})"


class LearnedRule(TenantModel):
    """
    Regra aprendida para categorização automática.
    
    Armazena associações customizadas de cada tenant para categorização
    automática de transações. Aprendida através do uso do sistema.
    
    Exemplo:
    - Se fornecedor = "Supermercado X" -> sempre categorizar como "Estoque"
    - Se palavra-chave = "aluguel" -> sempre categorizar como "Aluguel" (Despesa Fixa)
    
    Características:
    - keyword: Palavra-chave ou nome de fornecedor para matching
    - category/subcategory: Categoria e subcategoria sugeridas automaticamente
    - hit_count: Contador de acertos (para machine learning futuro)
    - active: Flag para desativar regras antigas
    """
    
    keyword = models.CharField(
        max_length=255,
        db_index=True,
        verbose_name='Palavra-chave',
        help_text='Palavra-chave ou nome de fornecedor para matching automático'
    )
    
    category = models.ForeignKey(
        Category,
        on_delete=models.CASCADE,
        related_name='learned_rules',
        verbose_name='Categoria',
        help_text='Categoria sugerida automaticamente'
    )
    
    subcategory = models.ForeignKey(
        Subcategory,
        on_delete=models.CASCADE,
        related_name='learned_rules',
        verbose_name='Subcategoria',
        help_text='Subcategoria sugerida automaticamente'
    )
    
    hit_count = models.IntegerField(
        default=0,
        verbose_name='Contador de Acertos',
        help_text='Número de vezes que esta regra foi aplicada com sucesso'
    )
    
    active = models.BooleanField(
        default=True,
        verbose_name='Ativa',
        help_text='Indica se a regra está ativa (pode ser desativada se não funcionar bem)'
    )
    
    class Meta:
        verbose_name = 'Regra Aprendida'
        verbose_name_plural = 'Regras Aprendidas'
        ordering = ['-hit_count', 'keyword']
        indexes = [
            models.Index(fields=['tenant', 'keyword']),
            models.Index(fields=['tenant', 'active']),
            models.Index(fields=['keyword', 'active']),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=['tenant', 'keyword'],
                name='unique_rule_per_tenant_keyword'
            ),
        ]
    
    def clean(self):
        """Validação adicional do modelo."""
        super().clean()
        # Garante que subcategoria pertença à categoria informada
        if self.subcategory.category != self.category:
            raise ValidationError({
                'subcategory': 'A subcategoria deve pertencer à categoria informada.'
            })
    
    def increment_hit(self) -> None:
        """
        Incrementa o contador de acertos.
        
        Chamado quando a regra é aplicada com sucesso pelo usuário.
        """
        self.hit_count += 1
        self.save(update_fields=['hit_count'])
    
    def __str__(self) -> str:
        """Representação string da regra."""
        status = "✓" if self.active else "✗"
        return f"{status} {self.keyword} -> {self.subcategory.name} (hits: {self.hit_count})"

