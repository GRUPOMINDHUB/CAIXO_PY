"""
Formulários de Movimentações Financeiras.

Define formulários Django para criação e edição de Transaction e Installment.
Inclui lógica de parcelamento e validações contábeis.
"""

from datetime import date
from decimal import Decimal

from django import forms
from django.core.exceptions import ValidationError
from django.db import models

from core.models.finance import (
    Transaction, Installment, Category, Subcategory, SalesChannel,
    InstallmentStatus, TransactionType
)


class ExpenseForm(forms.ModelForm):
    """
    Formulário para criar/editar despesas (Transaction tipo DESPESA).
    
    Inclui campos extras para:
    - Parcelamento (número de parcelas)
    - Data da primeira parcela
    - Checkbox "Já pago?" para marcar primeira parcela como paga
    - Categoria e Subcategoria (obrigatórias)
    """
    
    # Campos extras para parcelamento
    num_parcelas = forms.IntegerField(
        label='Número de Parcelas',
        initial=1,
        min_value=1,
        max_value=60,
        help_text='Quantidade de parcelas (1 = à vista)',
        widget=forms.NumberInput(attrs={
            'class': 'w-full px-4 py-2 rounded-lg outline-none transition',
            'style': 'border: 1px solid #E9E4DB; color: #2D2926; background-color: #FFFFFF;',
            'onfocus': "this.style.borderColor='#D4AF37'; this.style.boxShadow='0 0 0 3px rgba(212, 175, 55, 0.1)';",
            'onblur': "this.style.borderColor='#E9E4DB'; this.style.boxShadow='none';",
            'id': 'id_num_parcelas'
        })
    )
    
    periodicidade = forms.ChoiceField(
        label='Periodicidade',
        choices=[
            ('MENSAL', 'Mensal'),
            ('SEMANAL', 'Semanal'),
            ('PERSONALIZADO', 'Personalizado'),
        ],
        initial='MENSAL',
        help_text='Frequência das parcelas',
        widget=forms.Select(attrs={
            'class': 'w-full px-4 py-2 rounded-lg outline-none transition',
            'style': 'border: 1px solid #E9E4DB; color: #2D2926; background-color: #FFFFFF;',
            'onfocus': "this.style.borderColor='#D4AF37'; this.style.boxShadow='0 0 0 3px rgba(212, 175, 55, 0.1)';",
            'onblur': "this.style.borderColor='#E9E4DB'; this.style.boxShadow='none';",
            'id': 'id_periodicidade'
        })
    )
    
    primeira_vencimento = forms.DateField(
        label='Vencimento',
        help_text='Data de vencimento da primeira parcela',
        required=False,
        widget=forms.DateInput(attrs={
            'type': 'date',
            'class': 'w-full px-4 py-2 rounded-lg outline-none transition',
            'style': 'border: 1px solid #E9E4DB; color: #2D2926; background-color: #FFFFFF;',
            'onfocus': "this.style.borderColor='#D4AF37'; this.style.boxShadow='0 0 0 3px rgba(212, 175, 55, 0.1)';",
            'onblur': "this.style.borderColor='#E9E4DB'; this.style.boxShadow='none';",
            'id': 'id_primeira_vencimento'
        })
    )
    
    ja_pago = forms.BooleanField(
        label='Já pago?',
        required=False,
        help_text='Marque se o pagamento já foi realizado (primeira parcela será marcada como paga)',
        widget=forms.CheckboxInput(attrs={
            'class': 'w-5 h-5 rounded',
            'style': 'accent-color: #D4AF37;'
        })
    )
    
    class Meta:
        model = Transaction
        fields = [
            'description',
            'amount',
            'category',
            'subcategory',
            'competence_date',
            'supplier',
        ]
        # transaction_type será definido automaticamente como DESPESA
        widgets = {
            'description': forms.Textarea(attrs={
                'rows': 3,
                'class': 'w-full px-4 py-2 rounded-lg outline-none transition',
                'style': 'border: 1px solid #E9E4DB; color: #2D2926; background-color: #FFFFFF;',
                'placeholder': 'Descrição detalhada da transação (opcional)',
                'onfocus': "this.style.borderColor='#D4AF37'; this.style.boxShadow='0 0 0 3px rgba(212, 175, 55, 0.1)';",
                'onblur': "this.style.borderColor='#E9E4DB'; this.style.boxShadow='none';"
            }),
            'amount': forms.NumberInput(attrs={
                'step': '0.01',
                'min': '0.01',
                'class': 'w-full px-4 py-2 rounded-lg outline-none transition',
                'style': 'border: 1px solid #E9E4DB; color: #2D2926; background-color: #FFFFFF;',
                'placeholder': '0.00',
                'onfocus': "this.style.borderColor='#D4AF37'; this.style.boxShadow='0 0 0 3px rgba(212, 175, 55, 0.1)';",
                'onblur': "this.style.borderColor='#E9E4DB'; this.style.boxShadow='none';"
            }),
            'category': forms.Select(attrs={
                'class': 'w-full px-4 py-2 rounded-lg outline-none transition',
                'style': 'border: 1px solid #E9E4DB; color: #2D2926; background-color: #FFFFFF;',
                'onfocus': "this.style.borderColor='#D4AF37'; this.style.boxShadow='0 0 0 3px rgba(212, 175, 55, 0.1)';",
                'onblur': "this.style.borderColor='#E9E4DB'; this.style.boxShadow='none';",
                'id': 'id_category'
            }),
            'subcategory': forms.Select(attrs={
                'class': 'w-full px-4 py-2 rounded-lg outline-none transition',
                'style': 'border: 1px solid #E9E4DB; color: #2D2926; background-color: #FFFFFF;',
                'onfocus': "this.style.borderColor='#D4AF37'; this.style.boxShadow='0 0 0 3px rgba(212, 175, 55, 0.1)';",
                'onblur': "this.style.borderColor='#E9E4DB'; this.style.boxShadow='none';",
                'id': 'id_subcategory'
            }),
            'competence_date': forms.DateInput(attrs={
                'type': 'date',
                'class': 'w-full px-4 py-2 rounded-lg outline-none transition',
                'style': 'border: 1px solid #E9E4DB; color: #2D2926; background-color: #FFFFFF;',
                'onfocus': "this.style.borderColor='#D4AF37'; this.style.boxShadow='0 0 0 3px rgba(212, 175, 55, 0.1)';",
                'onblur': "this.style.borderColor='#E9E4DB'; this.style.boxShadow='none';"
            }),
            'supplier': forms.TextInput(attrs={
                'class': 'w-full px-4 py-2 rounded-lg outline-none transition',
                'style': 'border: 1px solid #E9E4DB; color: #2D2926; background-color: #FFFFFF;',
                'placeholder': 'Nome do fornecedor/prestador (opcional)',
                'onfocus': "this.style.borderColor='#D4AF37'; this.style.boxShadow='0 0 0 3px rgba(212, 175, 55, 0.1)';",
                'onblur': "this.style.borderColor='#E9E4DB'; this.style.boxShadow='none';"
            }),
        }
        labels = {
            'description': 'Descrição',
            'amount': 'Valor Total',
            'category': 'Categoria',
            'subcategory': 'Subcategoria',
            'competence_date': 'Data de Competência',
            'supplier': 'Fornecedor',
        }
        help_texts = {
            'description': 'Descreva detalhadamente o que foi comprado/pago (opcional)',
            'amount': 'Valor total da transação (será dividido em parcelas se necessário)',
            'competence_date': 'Data de competência (mês/ano) para DRE - Quando ocorreu o fato gerador',
            'supplier': 'Nome do fornecedor ou prestador de serviço (opcional)',
        }
    
    def __init__(self, *args, tenant=None, **kwargs):
        """
        Inicializa o formulário com categorias e subcategorias do tenant.
        
        Args:
            tenant: Instância de Tenant para filtrar categorias
        """
        super().__init__(*args, **kwargs)
        
        # Armazena tenant para uso posterior
        self.tenant = tenant
        
        # Filtra apenas as 4 categorias globais pré-criadas
        # Estoque, Investimento, Despesa Fixa, Despesa Variável
        # IMPORTANTE: Usa without_tenant_filter() porque categorias globais têm tenant=None
        from core.models.finance import CategoryType
        
        categories = Category.objects.without_tenant_filter().filter(
            tenant__isnull=True,
            type__in=[
                CategoryType.ESTOQUE,
                CategoryType.INVESTIMENTO,
                CategoryType.FIXA,
                CategoryType.VARIAVEL
            ]
        ).order_by('type', 'name')
        
        # Força a avaliação do queryset para garantir que as categorias sejam carregadas
        categories_list = list(categories)  # Avalia o queryset
        
        self.fields['category'].queryset = categories
        # Define empty_label para garantir que apareça uma opção vazia
        self.fields['category'].empty_label = 'Selecione uma categoria'
        # Garante que o campo seja obrigatório apenas na validação, não no widget
        self.fields['category'].required = True
        
        # Subcategorias serão carregadas dinamicamente via JavaScript
        # IMPORTANTE: Inicializa com TODAS as subcategorias do tenant para permitir validação
        # Isso resolve o problema de validação quando o usuário seleciona uma subcategoria
        if tenant:
            # Carrega todas as subcategorias do tenant para permitir validação
            self.fields['subcategory'].queryset = Subcategory.objects.without_tenant_filter().filter(
                tenant=tenant
            ).order_by('name')
        else:
            # Se não tiver tenant, mantém vazio (não deve acontecer em uso normal)
            self.fields['subcategory'].queryset = Subcategory.objects.none()
        
        # Se estiver editando e tiver categoria, carrega subcategorias da categoria selecionada
        if self.instance and self.instance.pk:
            # Verifica se a instância tem category_id (evita acessar o relacionamento diretamente)
            if hasattr(self.instance, 'category_id') and self.instance.category_id:
                try:
                    category = self.instance.category
                    if category:
                        # Subcategorias são sempre específicas do tenant (não globais)
                        self.fields['subcategory'].queryset = Subcategory.objects.without_tenant_filter().filter(
                            tenant=tenant,
                            category=category
                        ).order_by('name')
                except (AttributeError, Transaction.category.RelatedObjectDoesNotExist):
                    # Se não tiver categoria, mantém queryset com todas as subcategorias do tenant
                    if tenant:
                        self.fields['subcategory'].queryset = Subcategory.objects.without_tenant_filter().filter(
                            tenant=tenant
                        ).order_by('name')
    
    def clean(self):
        """Validação adicional do formulário."""
        cleaned_data = super().clean()
        
        # Valida que subcategoria pertence à categoria
        category = cleaned_data.get('category')
        subcategory = cleaned_data.get('subcategory')
        
        if category and subcategory:
            # Valida que a subcategoria pertence à categoria selecionada
            if subcategory.category != category:
                raise ValidationError({
                    'subcategory': 'A subcategoria deve pertencer à categoria informada.'
                })
            
            # Valida que a subcategoria pertence ao tenant (segurança extra)
            if self.tenant and subcategory.tenant != self.tenant:
                raise ValidationError({
                    'subcategory': 'Subcategoria inválida para este tenant.'
                })
        
        return cleaned_data
    
    def save(self, commit=True):
        """Sobrescreve save para definir transaction_type como DESPESA."""
        instance = super().save(commit=False)
        instance.transaction_type = TransactionType.DESPESA
        if commit:
            instance.save()
        return instance


class RevenueForm(forms.ModelForm):
    """
    Formulário para criar/editar receitas (Transaction tipo RECEITA).
    
    Inclui campos extras para:
    - Parcelamento (número de parcelas)
    - Data da primeira parcela
    - Checkbox "Já pago?" para marcar primeira parcela como paga
    - Canal de Venda (obrigatório)
    - Data de Caixa (opcional, se diferente da competência)
    """
    
    # Campos extras para parcelamento
    num_parcelas = forms.IntegerField(
        label='Número de Parcelas',
        initial=1,
        min_value=1,
        max_value=60,
        help_text='Quantidade de parcelas mensais (1 = à vista)',
        widget=forms.NumberInput(attrs={
            'class': 'w-full px-4 py-2 rounded-lg outline-none transition',
            'style': 'border: 1px solid #E9E4DB; color: #2D2926; background-color: #FFFFFF;',
            'onfocus': "this.style.borderColor='#D4AF37'; this.style.boxShadow='0 0 0 3px rgba(212, 175, 55, 0.1)';",
            'onblur': "this.style.borderColor='#E9E4DB'; this.style.boxShadow='none';"
        })
    )
    
    primeira_vencimento = forms.DateField(
        label='Data do Primeiro Vencimento',
        initial=date.today,
        help_text='Data de vencimento da primeira parcela',
        widget=forms.DateInput(attrs={
            'type': 'date',
            'class': 'w-full px-4 py-2 rounded-lg outline-none transition',
            'style': 'border: 1px solid #E9E4DB; color: #2D2926; background-color: #FFFFFF;',
            'onfocus': "this.style.borderColor='#D4AF37'; this.style.boxShadow='0 0 0 3px rgba(212, 175, 55, 0.1)';",
            'onblur': "this.style.borderColor='#E9E4DB'; this.style.boxShadow='none';"
        })
    )
    
    ja_pago = forms.BooleanField(
        label='Já recebido?',
        required=False,
        help_text='Marque se o recebimento já foi realizado (primeira parcela será marcada como paga)',
        widget=forms.CheckboxInput(attrs={
            'class': 'w-5 h-5 rounded',
            'style': 'accent-color: #D4AF37;'
        })
    )
    
    class Meta:
        model = Transaction
        fields = [
            'description',
            'amount',
            'sales_channel',
            'competence_date',
            'competence_date_end',
            'cash_date',
        ]
        widgets = {
            'description': forms.Textarea(attrs={
                'rows': 3,
                'class': 'w-full px-4 py-2 rounded-lg outline-none transition',
                'style': 'border: 1px solid #E9E4DB; color: #2D2926; background-color: #FFFFFF;',
                'placeholder': 'Descrição detalhada da receita (opcional)',
                'onfocus': "this.style.borderColor='#D4AF37'; this.style.boxShadow='0 0 0 3px rgba(212, 175, 55, 0.1)';",
                'onblur': "this.style.borderColor='#E9E4DB'; this.style.boxShadow='none';"
            }),
            'amount': forms.NumberInput(attrs={
                'step': '0.01',
                'min': '0.01',
                'class': 'w-full px-4 py-2 rounded-lg outline-none transition',
                'style': 'border: 1px solid #E9E4DB; color: #2D2926; background-color: #FFFFFF;',
                'placeholder': '0.00',
                'onfocus': "this.style.borderColor='#D4AF37'; this.style.boxShadow='0 0 0 3px rgba(212, 175, 55, 0.1)';",
                'onblur': "this.style.borderColor='#E9E4DB'; this.style.boxShadow='none';"
            }),
            'sales_channel': forms.Select(attrs={
                'class': 'w-full px-4 py-2 rounded-lg outline-none transition',
                'style': 'border: 1px solid #E9E4DB; color: #2D2926; background-color: #FFFFFF;',
                'onfocus': "this.style.borderColor='#D4AF37'; this.style.boxShadow='0 0 0 3px rgba(212, 175, 55, 0.1)';",
                'onblur': "this.style.borderColor='#E9E4DB'; this.style.boxShadow='none';",
                'id': 'id_sales_channel'
            }),
            'competence_date': forms.DateInput(attrs={
                'type': 'date',
                'class': 'w-full px-4 py-2 rounded-lg outline-none transition',
                'style': 'border: 1px solid #E9E4DB; color: #2D2926; background-color: #FFFFFF;',
                'onfocus': "this.style.borderColor='#D4AF37'; this.style.boxShadow='0 0 0 3px rgba(212, 175, 55, 0.1)';",
                'onblur': "this.style.borderColor='#E9E4DB'; this.style.boxShadow='none';"
            }),
            'competence_date_end': forms.DateInput(attrs={
                'type': 'date',
                'class': 'w-full px-4 py-2 rounded-lg outline-none transition',
                'style': 'border: 1px solid #E9E4DB; color: #2D2926; background-color: #FFFFFF;',
                'onfocus': "this.style.borderColor='#D4AF37'; this.style.boxShadow='0 0 0 3px rgba(212, 175, 55, 0.1)';",
                'onblur': "this.style.borderColor='#E9E4DB'; this.style.boxShadow='none';"
            }),
            'cash_date': forms.DateInput(attrs={
                'type': 'date',
                'class': 'w-full px-4 py-2 rounded-lg outline-none transition',
                'style': 'border: 1px solid #E9E4DB; color: #2D2926; background-color: #FFFFFF;',
                'onfocus': "this.style.borderColor='#D4AF37'; this.style.boxShadow='0 0 0 3px rgba(212, 175, 55, 0.1)';",
                'onblur': "this.style.borderColor='#E9E4DB'; this.style.boxShadow='none';"
            }),
        }
        labels = {
            'description': 'Descrição',
            'amount': 'Valor Total',
            'sales_channel': 'Canal de Venda',
            'competence_date': 'Data de Início do Período',
            'competence_date_end': 'Data de Fim do Período',
            'cash_date': 'Data de Caixa',
        }
        help_texts = {
            'description': 'Descreva detalhadamente a receita (opcional)',
            'amount': 'Valor total da receita (será dividido em parcelas se necessário)',
            'sales_channel': 'Canal pelo qual a receita foi gerada (ex: iFood, Balcão, Delivery)',
            'competence_date': 'Data de início do período de faturamento (ex: 01/01/2025)',
            'competence_date_end': 'Data de fim do período de faturamento (ex: 31/01/2025). Deixe em branco se for apenas um dia.',
            'cash_date': 'Data em que o dinheiro entrou (opcional, se diferente da competência)',
        }
    
    def clean(self):
        """Validação adicional do formulário."""
        # Define transaction_type ANTES de chamar super().clean() para evitar erros de validação
        # Isso garante que o modelo saiba que é uma receita antes de validar
        if not hasattr(self, 'instance') or not self.instance:
            # Cria uma instância temporária se não existir
            from core.models.finance import Transaction
            self.instance = Transaction()
        
        self.instance.transaction_type = TransactionType.RECEITA
        # Garante que category e subcategory sejam None
        self.instance.category = None
        self.instance.subcategory = None
        
        cleaned_data = super().clean()
        
        # Valida que data de fim seja maior ou igual à data de início
        competence_date = cleaned_data.get('competence_date')
        competence_date_end = cleaned_data.get('competence_date_end')
        
        if competence_date and competence_date_end:
            if competence_date_end < competence_date:
                raise ValidationError({
                    'competence_date_end': 'A data de fim do período deve ser maior ou igual à data de início.'
                })
        
        return cleaned_data
    
    def __init__(self, *args, tenant=None, **kwargs):
        """
        Inicializa o formulário com canais de venda do tenant.
        
        Args:
            tenant: Instância de Tenant para filtrar canais de venda
        """
        super().__init__(*args, **kwargs)
        
        # Filtra canais de venda (globais + do tenant, apenas ativos)
        if tenant:
            sales_channels = SalesChannel.objects.filter(
                models.Q(tenant=tenant) | models.Q(tenant__isnull=True),
                active=True
            ).order_by('name')
        else:
            sales_channels = SalesChannel.objects.filter(
                tenant__isnull=True,
                active=True
            ).order_by('name')
        
        self.fields['sales_channel'].queryset = sales_channels
        
        # Se for uma nova receita (sem instância), tenta preencher primeira_vencimento com cash_date
        # Se cash_date não estiver definido, será preenchido via JavaScript quando o usuário preencher
        if not self.instance or not self.instance.pk:
            # Se cash_date já estiver preenchido no formulário, usa ele
            if 'cash_date' in self.data and self.data['cash_date']:
                self.fields['primeira_vencimento'].initial = self.data['cash_date']
            # Se cash_date estiver no initial, usa ele
            elif 'cash_date' in self.initial and self.initial['cash_date']:
                self.fields['primeira_vencimento'].initial = self.initial['cash_date']
            else:
                self.fields['primeira_vencimento'].initial = None
    
    def save(self, commit=True):
        """Sobrescreve save para definir transaction_type como RECEITA."""
        instance = super().save(commit=False)
        instance.transaction_type = TransactionType.RECEITA
        # Garante que category e subcategory sejam None para receitas
        instance.category = None
        instance.subcategory = None
        if commit:
            instance.save()
        return instance


class InstallmentForm(forms.ModelForm):
    """
    Formulário para editar parcelas individuais.
    
    Usado em InlineFormSet para gerenciar parcelas de uma Transaction.
    """
    
    class Meta:
        model = Installment
        fields = [
            'due_date',
            'payment_date',
            'amount',
            'penalty_amount',
            'status',
        ]
        widgets = {
            'due_date': forms.DateInput(attrs={
                'type': 'date',
                'class': 'w-full px-4 py-2 rounded-lg outline-none transition',
                'style': 'border: 1px solid #E9E4DB; color: #2D2926; background-color: #FFFFFF;',
            }),
            'payment_date': forms.DateInput(attrs={
                'type': 'date',
                'class': 'w-full px-4 py-2 rounded-lg outline-none transition',
                'style': 'border: 1px solid #E9E4DB; color: #2D2926; background-color: #FFFFFF;',
            }),
            'amount': forms.NumberInput(attrs={
                'step': '0.01',
                'min': '0.01',
                'class': 'w-full px-4 py-2 rounded-lg outline-none transition',
                'style': 'border: 1px solid #E9E4DB; color: #2D2926; background-color: #FFFFFF;',
            }),
            'penalty_amount': forms.NumberInput(attrs={
                'step': '0.01',
                'min': '0.00',
                'class': 'w-full px-4 py-2 rounded-lg outline-none transition',
                'style': 'border: 1px solid #E9E4DB; color: #2D2926; background-color: #FFFFFF;',
            }),
            'status': forms.Select(attrs={
                'class': 'w-full px-4 py-2 rounded-lg outline-none transition',
                'style': 'border: 1px solid #E9E4DB; color: #2D2926; background-color: #FFFFFF;',
            }),
        }
