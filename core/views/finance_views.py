"""
Views de Movimentações Financeiras - Central Operacional do Caixô.

Implementa CRUD completo de Transaction e Installment com:
- Filtros inteligentes (período, status, tipo, busca)
- Totalizadores em tempo real
- Parcelamento automático
- Ações rápidas (marcar como pago, editar, excluir)
- Otimização de queries (select_related, prefetch_related)
- Isolamento multi-tenant rigoroso
"""

import logging
from datetime import date, timedelta
from decimal import Decimal
from typing import Optional

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.db import transaction as db_transaction
from django.db.models import Sum, F, Q, Count, Case, When, IntegerField, Value
from django.http import JsonResponse
from django.shortcuts import render, redirect, get_object_or_404
from django.utils import timezone
from django.views.decorators.http import require_POST, require_http_methods

from core.models.finance import (
    Transaction, Installment, Category, Subcategory, SalesChannel,
    InstallmentStatus, CategoryType, TransactionType
)
from core.forms.finance_forms import ExpenseForm, RevenueForm, InstallmentForm

logger = logging.getLogger(__name__)


def _is_revenue_category(category: Category) -> bool:
    """
    Verifica se uma categoria é de receita.
    
    Por enquanto, o sistema não tem categoria específica de receita.
    Quando houver, será uma categoria especial chamada "Receita".
    
    Args:
        category: Instância de Category
        
    Returns:
        True se for receita, False se for despesa
    """
    # TODO: Quando houver categoria de receita, verificar aqui
    # Por enquanto, todas são despesas
    return False


@login_required
def movement_list(request):
    """
    Lista todas as movimentações (Transactions) com filtros e totalizadores.
    
    Filtros disponíveis:
    - Período: Mês/Ano (query params: month, year)
    - Status: Todos, Pendentes, Pagos (query param: status)
    - Tipo: Receitas, Despesas (query param: type)
    - Busca: Fornecedor ou descrição (query param: search)
    
    Totalizadores calculados em tempo real:
    - Total de Entradas (receitas)
    - Total de Saídas (despesas)
    - Saldo do Período (entradas - saídas)
    
    Performance: Usa select_related e prefetch_related para evitar N+1.
    """
    tenant = getattr(request, 'tenant', None) or getattr(request.user, 'tenant', None)
    
    # Admin Master não tem tenant, mostra mensagem
    if not tenant:
        messages.info(request, 'Você precisa estar vinculado a uma empresa para ver movimentações.')
        return redirect('dashboard')
    
    # ============================================
    # FILTROS
    # ============================================
    # Período (mês/ano) - suporta "all" para todos
    today = date.today()
    month_param = request.GET.get('month', str(today.month))
    year_param = request.GET.get('year', str(today.year))
    
    # Processa mês
    if month_param == 'all':
        month = None  # None significa "todos os meses"
    else:
        try:
            month = int(month_param)
            if month < 1 or month > 12:
                month = today.month
        except (ValueError, TypeError):
            month = today.month
    
    # Processa ano
    if year_param == 'all':
        year = None  # None significa "todo o período"
    else:
        try:
            year = int(year_param)
            if year < 2000 or year > 2100:
                year = today.year
        except (ValueError, TypeError):
            year = today.year
    
    # Define período de filtro (só aplica se month e year não forem None)
    if month is not None and year is not None:
        first_day = date(year, month, 1)
        if month == 12:
            last_day = date(year + 1, 1, 1)
        else:
            last_day = date(year, month + 1, 1)
    else:
        # Se month ou year for None, não filtra por período
        first_day = None
        last_day = None
    
    # Status (Todos, Pendentes, Pagos)
    status_filter = request.GET.get('status', 'all')
    
    # Tipo (Receitas, Despesas, Todos)
    type_filter = request.GET.get('type', 'all')
    
    # Busca textual
    search_query = request.GET.get('search', '').strip()
    
    # ============================================
    # QUERY BASE - BUSCA INSTALLMENTS (PARCELAS)
    # ============================================
    # Agora buscamos Installments diretamente, não Transactions
    # Cada linha da tabela será uma parcela
    installments = Installment.objects.filter(tenant=tenant)
    
    # Filtro de período (competência da transação) - só aplica se período foi especificado
    if first_day is not None and last_day is not None:
        installments = installments.filter(
            transaction__competence_date__gte=first_day,
            transaction__competence_date__lt=last_day
        )
    
    # Filtro de busca (fornecedor, descrição ou canal de venda da transação)
    if search_query:
        installments = installments.filter(
            Q(transaction__description__icontains=search_query) |
            Q(transaction__supplier__icontains=search_query) |
            Q(transaction__sales_channel__name__icontains=search_query)
        )
    
    # Otimização: select_related para evitar N+1
    installments = installments.select_related(
        'transaction',
        'transaction__category',
        'transaction__subcategory',
        'transaction__sales_channel'
    )
    
    # ============================================
    # APLICA FILTROS DE STATUS E TIPO
    # ============================================
    # Filtro de tipo (Receitas, Despesas, Todos)
    if type_filter == 'revenue':
        installments = installments.filter(transaction__transaction_type=TransactionType.RECEITA)
    elif type_filter == 'expense':
        installments = installments.filter(transaction__transaction_type=TransactionType.DESPESA)
    # Se 'all', não filtra (mostra todos)
    
    # Filtro de status (aplica diretamente nas parcelas)
    if status_filter == 'pending':
        installments = installments.filter(status=InstallmentStatus.PENDENTE)
    elif status_filter == 'paid':
        installments = installments.filter(status=InstallmentStatus.PAGO)
    # Se 'all', não filtra (mostra todos)
    
    # ============================================
    # ORDENAÇÃO
    # ============================================
    order_by = request.GET.get('order_by', 'data')  # Padrão: data
    
    if order_by == 'tipo':
        # Ordena por tipo da transação (Receita primeiro, depois Despesa) e depois data de vencimento
        installments = installments.order_by('transaction__transaction_type', '-due_date', '-created_at')
    elif order_by == 'status':
        # Ordena por status da parcela (Pagos primeiro, depois Pendentes) e depois data de vencimento
        installments = installments.order_by('status', '-due_date', '-created_at')
    else:  # order_by == 'data' (padrão)
        # Ordena por data de vencimento (mais recente primeiro)
        installments = installments.order_by('-due_date', '-created_at')
    
    # ============================================
    # TOTALIZADORES
    # ============================================
    # Calcula totais de entradas e saídas do período filtrado
    # Usa a query base ANTES dos filtros de tipo para calcular corretamente
    
    # Query base para totalizadores (sem filtro de tipo)
    base_transactions = Transaction.objects.filter(tenant=tenant)
    # Só aplica filtro de período se foi especificado
    if first_day is not None and last_day is not None:
        base_transactions = base_transactions.filter(
            competence_date__gte=first_day,
            competence_date__lt=last_day
        )
    if search_query:
        base_transactions = base_transactions.filter(
            Q(description__icontains=search_query) |
            Q(supplier__icontains=search_query) |
            Q(sales_channel__name__icontains=search_query)
        )
    
    # Total de Entradas (receitas) - Competência
    total_entradas = base_transactions.filter(
        transaction_type=TransactionType.RECEITA
    ).aggregate(
        total=Sum('amount')
    )['total'] or Decimal('0.00')
    
    # Total de Saídas (despesas) - Competência
    total_saidas = base_transactions.filter(
        transaction_type=TransactionType.DESPESA
    ).aggregate(
        total=Sum('amount')
    )['total'] or Decimal('0.00')
    
    # Saldo Projetado do Período (Competência - todas as transações do período)
    saldo_projetado = total_entradas - total_saidas
    
    # ============================================
    # SALDO ATUAL (CAIXA - apenas parcelas pagas)
    # ============================================
    # Calcula baseado em Installments pagas, independente do período de competência
    # Entradas (receitas pagas)
    entradas_caixa = Installment.objects.filter(
        tenant=tenant,
        transaction__transaction_type=TransactionType.RECEITA,
        status=InstallmentStatus.PAGO,
        payment_date__isnull=False
    ).aggregate(
        total=Sum(F('amount') + F('penalty_amount'))
    )['total'] or Decimal('0.00')
    
    # Saídas (despesas pagas)
    saidas_caixa = Installment.objects.filter(
        tenant=tenant,
        transaction__transaction_type=TransactionType.DESPESA,
        status=InstallmentStatus.PAGO,
        payment_date__isnull=False
    ).aggregate(
        total=Sum(F('amount') + F('penalty_amount'))
    )['total'] or Decimal('0.00')
    
    # Saldo Atual (Caixa)
    saldo_atual = entradas_caixa - saidas_caixa
    
    # ============================================
    # CONTAGEM DE REGISTROS
    # ============================================
    total_registros = installments.count()
    
    # ============================================
    # CONTEXTO PARA TEMPLATE
    # ============================================
    context = {
        'tenant': tenant,
        'installments': installments,  # Agora passamos installments em vez de transactions
        
        # Filtros ativos
        'month': month,
        'year': year,
        'status_filter': status_filter,
        'type_filter': type_filter,
        'search_query': search_query,
        
        # Totalizadores (Competência)
        'total_entradas': total_entradas,
        'total_saidas': total_saidas,
        'saldo_projetado': saldo_projetado,
        
        # Totalizadores (Caixa)
        'entradas_caixa': entradas_caixa,
        'saidas_caixa': saidas_caixa,
        'saldo_atual': saldo_atual,
        
        'total_registros': total_registros,
        
        # Períodos para dropdown
        'months': [
            ('all', 'Todos os meses'),
            (1, 'Janeiro'), (2, 'Fevereiro'), (3, 'Março'), (4, 'Abril'),
            (5, 'Maio'), (6, 'Junho'), (7, 'Julho'), (8, 'Agosto'),
            (9, 'Setembro'), (10, 'Outubro'), (11, 'Novembro'), (12, 'Dezembro')
        ],
        'years': [('all', 'Todo o período')] + [(y, str(y)) for y in range(today.year - 5, today.year + 1)],
        'order_by': order_by,
    }
    
    return render(request, 'core/finance/movement_list.html', context)


@login_required
@require_http_methods(['GET', 'POST'])
def expense_create(request):
    """
    Cria uma nova despesa (Transaction tipo DESPESA + Installments).
    
    Suporta:
    - Criação de Transaction única
    - Parcelamento automático (N parcelas mensais)
    - Marcação de "Já pago?" na primeira parcela
    - Categoria e Subcategoria (obrigatórias)
    
    Usa transaction.atomic() para garantir integridade.
    """
    tenant = getattr(request, 'tenant', None) or getattr(request.user, 'tenant', None)
    
    if not tenant:
        messages.error(request, 'Você precisa estar vinculado a uma empresa para criar despesas.')
        return redirect('dashboard')
    
    if request.method == 'POST':
        form = ExpenseForm(request.POST, tenant=tenant)
        
        if form.is_valid():
            try:
                with db_transaction.atomic():
                    # Cria a Transaction
                    transaction = form.save(commit=False)
                    transaction.tenant = tenant
                    transaction.transaction_type = TransactionType.DESPESA
                    transaction.save()
                    
                    # Processa parcelas
                    num_parcelas = form.cleaned_data.get('num_parcelas', 1)
                    valor_total = form.cleaned_data['amount']
                    valor_parcela = valor_total / Decimal(str(num_parcelas))
                    
                    # Periodicidade e data base para vencimentos
                    periodicidade = form.cleaned_data.get('periodicidade', 'MENSAL')
                    primeira_vencimento = form.cleaned_data.get('primeira_vencimento', date.today())
                    ja_pago = form.cleaned_data.get('ja_pago', False)
                    
                    # Cria as parcelas
                    parcelas_criadas = []
                    for i in range(num_parcelas):
                        # Calcula data de vencimento baseado na periodicidade
                        if periodicidade == 'PERSONALIZADO':
                            # Busca data personalizada do POST
                            vencimento_key = f'vencimento_personalizado_{i + 1}'
                            vencimento_str = request.POST.get(vencimento_key)
                            if vencimento_str:
                                try:
                                    due_date = date.fromisoformat(vencimento_str)
                                except (ValueError, TypeError):
                                    raise ValueError(f'Data inválida para parcela {i + 1}')
                            else:
                                raise ValueError(f'Data de vencimento não fornecida para parcela {i + 1}')
                        elif periodicidade == 'SEMANAL':
                            # Adiciona i semanas à primeira data
                            due_date = primeira_vencimento + timedelta(weeks=i)
                        else:  # MENSAL (padrão)
                            # Adiciona i meses à primeira data
                            if i == 0:
                                due_date = primeira_vencimento
                            else:
                                if primeira_vencimento.month + i <= 12:
                                    due_date = date(
                                        primeira_vencimento.year,
                                        primeira_vencimento.month + i,
                                        primeira_vencimento.day
                                    )
                                else:
                                    due_date = date(
                                        primeira_vencimento.year + 1,
                                        primeira_vencimento.month + i - 12,
                                        primeira_vencimento.day
                                    )
                        
                        # Cria a parcela
                        installment = Installment(
                            tenant=tenant,
                            transaction=transaction,
                            due_date=due_date,
                            amount=valor_parcela,
                            penalty_amount=Decimal('0.00'),
                            status=InstallmentStatus.PAGO if (ja_pago and i == 0) else InstallmentStatus.PENDENTE
                        )
                        
                        # Se já pago, define data de pagamento
                        if ja_pago and i == 0:
                            installment.payment_date = date.today()
                        
                        installment.save()
                        parcelas_criadas.append(installment)
                    
                    # Mensagem de sucesso
                    if num_parcelas > 1:
                        messages.success(
                            request,
                            f'Despesa de R$ {valor_total:,.2f} registrada em {num_parcelas} parcelas.'
                        )
                    else:
                        messages.success(
                            request,
                            f'Despesa de R$ {valor_total:,.2f} registrada com sucesso!'
                        )
                    
                    return redirect('movement_list')
                    
            except Exception as e:
                logger.error(f'Erro ao criar despesa: {str(e)}', exc_info=True)
                messages.error(request, f'Erro ao criar despesa: {str(e)}')
    else:
        form = ExpenseForm(tenant=tenant)
    
    # Força a avaliação do queryset de categorias e passa para o template
    # Re-avalia o queryset para garantir que as categorias globais sejam carregadas
    categories_list = list(form.fields['category'].queryset.all())
    
    context = {
        'form': form,
        'categories': categories_list,  # Passa as categorias já avaliadas
        'tenant': tenant,
        'form_type': 'expense',
        'title': 'Nova Despesa',
    }
    
    return render(request, 'core/finance/movement_form.html', context)


@login_required
@require_http_methods(['GET', 'POST'])
def expense_edit(request, pk):
    """
    Edita uma despesa existente.
    
    Validações:
    - Se já possui parcelas pagas, avisa ao alterar valor total
    - Não permite alterar parcelas já pagas
    """
    tenant = getattr(request, 'tenant', None) or getattr(request.user, 'tenant', None)
    
    if not tenant:
        messages.error(request, 'Você precisa estar vinculado a uma empresa para editar despesas.')
        return redirect('dashboard')
    
    # Busca a transação (com isolamento multi-tenant)
    transaction = get_object_or_404(
        Transaction.objects.filter(tenant=tenant, transaction_type=TransactionType.DESPESA),
        pk=pk
    )
    
    # Verifica se tem parcelas pagas
    parcelas_pagas = transaction.installments.filter(status=InstallmentStatus.PAGO).count()
    tem_parcelas_pagas = parcelas_pagas > 0
    
    if request.method == 'POST':
        form = ExpenseForm(request.POST, instance=transaction, tenant=tenant)
        
        if form.is_valid():
            try:
                with db_transaction.atomic():
                    # Se tem parcelas pagas e valor mudou, avisa
                    valor_original = transaction.amount
                    valor_novo = form.cleaned_data['amount']
                    
                    if tem_parcelas_pagas and valor_original != valor_novo:
                        # Avisa mas permite (afeta apenas parcelas futuras)
                        messages.warning(
                            request,
                            'Atenção: O valor foi alterado. Isso afetará apenas as parcelas futuras.'
                        )
                    
                    # Salva a transação
                    transaction = form.save()
                    
                    messages.success(request, 'Despesa atualizada com sucesso!')
                    return redirect('movement_list')
                    
            except Exception as e:
                logger.error(f'Erro ao editar despesa: {str(e)}', exc_info=True)
                messages.error(request, f'Erro ao atualizar despesa: {str(e)}')
    else:
        form = ExpenseForm(instance=transaction, tenant=tenant)
    
    # Força a avaliação do queryset de categorias e passa para o template
    # Re-avalia o queryset para garantir que as categorias globais sejam carregadas
    categories_list = list(form.fields['category'].queryset.all())
    
    # Busca parcelas
    installments = transaction.installments.all().order_by('due_date')
    
    context = {
        'form': form,
        'categories': categories_list,  # Passa as categorias já avaliadas
        'transaction': transaction,
        'installments': installments,
        'tem_parcelas_pagas': tem_parcelas_pagas,
        'tenant': tenant,
        'form_type': 'expense',
        'title': f'Editar Despesa: {transaction.description or "Sem descrição"}',
    }
    
    return render(request, 'core/finance/movement_form.html', context)


@login_required
@require_http_methods(['GET', 'POST'])
def revenue_create(request):
    """
    Cria uma nova receita (Transaction tipo RECEITA + Installments).
    
    Suporta:
    - Criação de Transaction única
    - Parcelamento automático (N parcelas mensais)
    - Marcação de "Já recebido?" na primeira parcela
    - Canal de Venda (obrigatório)
    - Data de Caixa (opcional, se diferente da competência)
    
    Usa transaction.atomic() para garantir integridade.
    """
    tenant = getattr(request, 'tenant', None) or getattr(request.user, 'tenant', None)
    
    if not tenant:
        messages.error(request, 'Você precisa estar vinculado a uma empresa para criar receitas.')
        return redirect('dashboard')
    
    if request.method == 'POST':
        form = RevenueForm(request.POST, tenant=tenant)
        
        if form.is_valid():
            try:
                with db_transaction.atomic():
                    # Cria a Transaction
                    transaction = form.save(commit=False)
                    transaction.tenant = tenant
                    transaction.transaction_type = TransactionType.RECEITA
                    transaction.save()
                    
                    # Processa parcelas
                    num_parcelas = form.cleaned_data.get('num_parcelas', 1)
                    valor_total = form.cleaned_data['amount']
                    valor_parcela = valor_total / Decimal(str(num_parcelas))
                    
                    # Data base para vencimentos (usa primeira_vencimento se fornecido, senão cash_date, senão competence_date)
                    cash_date = form.cleaned_data.get('cash_date')
                    primeira_vencimento = form.cleaned_data.get('primeira_vencimento')
                    # Se não foi informada primeira_vencimento, usa cash_date ou competence_date
                    if not primeira_vencimento:
                        primeira_vencimento = cash_date or form.cleaned_data.get('competence_date') or date.today()
                    ja_recebido = form.cleaned_data.get('ja_pago', False)
                    
                    # Cria as parcelas
                    parcelas_criadas = []
                    for i in range(num_parcelas):
                        # Calcula data de vencimento (mensal)
                        if i == 0:
                            due_date = primeira_vencimento
                        else:
                            # Adiciona i meses à primeira data
                            if primeira_vencimento.month + i <= 12:
                                due_date = date(
                                    primeira_vencimento.year,
                                    primeira_vencimento.month + i,
                                    primeira_vencimento.day
                                )
                            else:
                                due_date = date(
                                    primeira_vencimento.year + 1,
                                    primeira_vencimento.month + i - 12,
                                    primeira_vencimento.day
                                )
                        
                        # Cria a parcela
                        installment = Installment(
                            tenant=tenant,
                            transaction=transaction,
                            due_date=due_date,
                            amount=valor_parcela,
                            penalty_amount=Decimal('0.00'),
                            status=InstallmentStatus.PAGO if (ja_recebido and i == 0) else InstallmentStatus.PENDENTE
                        )
                        
                        # Se já recebido, define data de pagamento
                        if ja_recebido and i == 0:
                            installment.payment_date = date.today()
                        
                        installment.save()
                        parcelas_criadas.append(installment)
                    
                    # Mensagem de sucesso
                    if num_parcelas > 1:
                        messages.success(
                            request,
                            f'Receita de R$ {valor_total:,.2f} registrada em {num_parcelas} parcelas.'
                        )
                    else:
                        messages.success(
                            request,
                            f'Receita de R$ {valor_total:,.2f} registrada com sucesso!'
                        )
                    
                    return redirect('movement_list')
                    
            except Exception as e:
                logger.error(f'Erro ao criar receita: {str(e)}', exc_info=True)
                messages.error(request, f'Erro ao criar receita: {str(e)}')
    else:
        form = RevenueForm(tenant=tenant)
    
    context = {
        'form': form,
        'tenant': tenant,
        'form_type': 'revenue',
        'title': 'Nova Receita',
        'transaction': None,
    }
    
    return render(request, 'core/finance/movement_form.html', context)


@login_required
@require_http_methods(['GET', 'POST'])
def revenue_edit(request, pk):
    """
    Edita uma receita existente.
    
    Validações:
    - Se já possui parcelas pagas, avisa ao alterar valor total
    - Não permite alterar parcelas já pagas
    """
    tenant = getattr(request, 'tenant', None) or getattr(request.user, 'tenant', None)
    
    if not tenant:
        messages.error(request, 'Você precisa estar vinculado a uma empresa para editar receitas.')
        return redirect('dashboard')
    
    # Busca a transação (com isolamento multi-tenant)
    transaction = get_object_or_404(
        Transaction.objects.filter(tenant=tenant, transaction_type=TransactionType.RECEITA),
        pk=pk
    )
    
    # Verifica se tem parcelas pagas
    parcelas_pagas = transaction.installments.filter(status=InstallmentStatus.PAGO).count()
    tem_parcelas_pagas = parcelas_pagas > 0
    
    if request.method == 'POST':
        form = RevenueForm(request.POST, instance=transaction, tenant=tenant)
        
        if form.is_valid():
            try:
                with db_transaction.atomic():
                    # Se tem parcelas pagas e valor mudou, avisa
                    valor_original = transaction.amount
                    valor_novo = form.cleaned_data['amount']
                    
                    if tem_parcelas_pagas and valor_original != valor_novo:
                        # Avisa mas permite (afeta apenas parcelas futuras)
                        messages.warning(
                            request,
                            'Atenção: O valor foi alterado. Isso afetará apenas as parcelas futuras.'
                        )
                    
                    # Salva a transação
                    transaction = form.save()
                    
                    messages.success(request, 'Receita atualizada com sucesso!')
                    return redirect('movement_list')
                    
            except Exception as e:
                logger.error(f'Erro ao editar receita: {str(e)}', exc_info=True)
                messages.error(request, f'Erro ao atualizar receita: {str(e)}')
    else:
        form = RevenueForm(instance=transaction, tenant=tenant)
    
    # Busca parcelas
    installments = transaction.installments.all().order_by('due_date')
    
    context = {
        'form': form,
        'transaction': transaction,
        'installments': installments,
        'tem_parcelas_pagas': tem_parcelas_pagas,
        'tenant': tenant,
        'form_type': 'revenue',
        'title': f'Editar Receita: {transaction.description or "Sem descrição"}',
    }
    
    return render(request, 'core/finance/movement_form.html', context)


@login_required
@require_POST
def movement_delete(request, pk):
    """
    Exclui uma movimentação (Transaction + Installments).
    
    Validações:
    - Não permite excluir se houver parcelas pagas (integridade contábil)
    """
    tenant = getattr(request, 'tenant', None) or getattr(request.user, 'tenant', None)
    
    if not tenant:
        messages.error(request, 'Você precisa estar vinculado a uma empresa para excluir movimentações.')
        return redirect('dashboard')
    
    # Busca a transação (com isolamento multi-tenant)
    transaction = get_object_or_404(
        Transaction.objects.filter(tenant=tenant),
        pk=pk
    )
    
    # Verifica se tem parcelas pagas
    parcelas_pagas = transaction.installments.filter(status=InstallmentStatus.PAGO).count()
    
    if parcelas_pagas > 0:
        messages.error(
            request,
            'Não é possível excluir este lançamento pois possui parcelas já pagas. '
            'Para manter a integridade contábil, apenas lançamentos sem pagamentos podem ser excluídos.'
        )
        return redirect('movement_list')
    
    try:
        # Exclui a transação (as parcelas são excluídas em cascata)
        descricao = transaction.description or "Sem descrição"
        valor = transaction.amount
        transaction.delete()
        
        messages.success(
            request,
            f'Lançamento "{descricao}" (R$ {valor:,.2f}) excluído com sucesso!'
        )
    except Exception as e:
        logger.error(f'Erro ao excluir movimentação: {str(e)}', exc_info=True)
        messages.error(request, f'Erro ao excluir lançamento: {str(e)}')
    
    return redirect('movement_list')


@login_required
@require_POST
def installment_mark_paid(request, pk):
    """
    Marca uma parcela como paga (ação rápida).
    
    Endpoint AJAX que marca uma Installment como PAGO.
    Retorna JSON com resultado.
    """
    tenant = getattr(request, 'tenant', None) or getattr(request.user, 'tenant', None)
    
    if not tenant:
        return JsonResponse({'success': False, 'error': 'Tenant não encontrado'}, status=403)
    
    # Busca a parcela (com isolamento multi-tenant)
    installment = get_object_or_404(
        Installment.objects.filter(tenant=tenant),
        pk=pk
    )
    
    try:
        # Marca como pago usando o método do modelo
        installment.mark_as_paid(payment_date=date.today())
        
        return JsonResponse({
            'success': True,
            'message': 'Parcela marcada como paga!'
        })
    except Exception as e:
        logger.error(f'Erro ao marcar parcela como paga: {str(e)}', exc_info=True)
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=400)


@login_required
def get_subcategories(request, category_id):
    """
    Endpoint AJAX para buscar subcategorias de uma categoria.
    
    Usado pelo formulário de movimentações para carregar subcategorias
    dinamicamente quando a categoria é selecionada.
    """
    # Obtém tenant do request (definido pelo middleware)
    tenant = getattr(request, 'tenant', None)
    
    if not tenant:
        logger.warning(f'[get_subcategories] Tenant não encontrado para usuário {request.user.id}')
        return JsonResponse({'error': 'Tenant não encontrado'}, status=403)
    
    try:
        # Busca a categoria (global ou do tenant) usando without_tenant_filter para permitir globais
        category = Category.objects.without_tenant_filter().filter(
            Q(id=category_id) & (Q(tenant=tenant) | Q(tenant__isnull=True))
        ).first()
        
        if not category:
            logger.warning(f'[get_subcategories] Categoria {category_id} não encontrada para tenant {tenant.id}')
            return JsonResponse({'error': 'Categoria não encontrada'}, status=404)
        
        # Busca subcategorias do tenant (subcategorias são sempre específicas do tenant, não globais)
        # IMPORTANTE: Subcategorias são sempre do tenant, não globais
        # Usa without_tenant_filter() para garantir que busca todas as subcategorias do tenant
        subcategories = Subcategory.objects.without_tenant_filter().filter(
            tenant=tenant,
            category=category
        ).order_by('name')
        
        # Log para debug
        subcategories_count = subcategories.count()
        logger.info(
            f'[get_subcategories] Encontradas {subcategories_count} subcategorias '
            f'para categoria {category.name} (ID: {category_id}) do tenant {tenant.name} (ID: {tenant.id})'
        )
        
        # Serializa subcategorias
        subcategories_data = [
            {
                'id': str(subcat.id),
                'name': subcat.name
            }
            for subcat in subcategories
        ]
        
        return JsonResponse({
            'subcategories': subcategories_data
        })
        
    except Exception as e:
        logger.error(f'[get_subcategories] Erro ao buscar subcategorias: {str(e)}', exc_info=True)
        return JsonResponse({'error': str(e)}, status=500)


@login_required
def get_all_subcategories(request):
    """
    Endpoint AJAX para buscar TODAS as subcategorias do tenant.
    
    Usado pelo formulário de movimentações para carregar todas as subcategorias
    quando nenhuma categoria está selecionada.
    """
    # Obtém tenant do request (definido pelo middleware)
    tenant = getattr(request, 'tenant', None)
    
    if not tenant:
        logger.warning(f'[get_all_subcategories] Tenant não encontrado para usuário {request.user.id}')
        return JsonResponse({'error': 'Tenant não encontrado'}, status=403)
    
    try:
        # Busca TODAS as subcategorias do tenant (sem filtro de categoria)
        # Usa without_tenant_filter() para garantir que busca todas as subcategorias do tenant
        subcategories = Subcategory.objects.without_tenant_filter().filter(
            tenant=tenant
        ).select_related('category').order_by('category__name', 'name')
        
        # Log para debug
        subcategories_count = subcategories.count()
        logger.info(
            f'[get_all_subcategories] Encontradas {subcategories_count} subcategorias '
            f'do tenant {tenant.name} (ID: {tenant.id})'
        )
        
        # Serializa subcategorias com informação da categoria para exibição
        subcategories_data = [
            {
                'id': str(subcat.id),
                'name': subcat.name,
                'category_id': str(subcat.category.id),
                'category_name': subcat.category.name
            }
            for subcat in subcategories
        ]
        
        return JsonResponse({
            'subcategories': subcategories_data
        })
        
    except Exception as e:
        logger.error(f'[get_all_subcategories] Erro ao buscar subcategorias: {str(e)}', exc_info=True)
        return JsonResponse({'error': str(e)}, status=500)


@login_required
@require_POST
def create_category_ajax(request):
    """
    Endpoint AJAX para criar uma nova categoria rapidamente.
    
    Args:
        request: HttpRequest com dados do formulário (name, type).
        
    Returns:
        JsonResponse com status e dados da categoria criada.
    """
    tenant = request.tenant
    if not tenant:
        return JsonResponse({'success': False, 'error': 'Nenhuma empresa selecionada.'}, status=400)
    
    name = request.POST.get('name', '').strip()
    category_type = request.POST.get('type', '').strip()
    
    if not name or not category_type:
        return JsonResponse({'success': False, 'error': 'Nome e tipo são obrigatórios.'}, status=400)
    
    if category_type not in [choice[0] for choice in CategoryType.choices]:
        return JsonResponse({'success': False, 'error': 'Tipo de categoria inválido.'}, status=400)
    
    try:
        with db_transaction.atomic():
            # Cria categoria do tenant (não global)
            category = Category.objects.create(
                tenant=tenant,
                name=name,
                type=category_type
            )
            
            return JsonResponse({
                'success': True,
                'category': {
                    'id': str(category.id),
                    'name': category.name,
                    'type_display': category.get_type_display()
                }
            })
    except Exception as e:
        logger.error(f'Erro ao criar categoria via AJAX: {str(e)}', exc_info=True)
        return JsonResponse({'success': False, 'error': f'Erro ao criar categoria: {str(e)}'}, status=500)


@login_required
@require_POST
def create_subcategory_ajax(request):
    """
    Endpoint AJAX para criar uma nova subcategoria rapidamente.
    
    Args:
        request: HttpRequest com dados do formulário (category, name).
        
    Returns:
        JsonResponse com status e dados da subcategoria criada.
    """
    tenant = request.tenant
    if not tenant:
        return JsonResponse({'success': False, 'error': 'Nenhuma empresa selecionada.'}, status=400)
    
    category_id = request.POST.get('category', '').strip()
    name = request.POST.get('name', '').strip()
    
    if not category_id or not name:
        return JsonResponse({'success': False, 'error': 'Categoria e nome são obrigatórios.'}, status=400)
    
    try:
        # Busca categoria usando without_tenant_filter para permitir categorias globais
        category = Category.objects.without_tenant_filter().get(id=category_id)
    except Category.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Categoria não encontrada.'}, status=404)
    
    # Verifica se já existe uma subcategoria com o mesmo nome na mesma categoria
    # Usa without_tenant_filter() para garantir busca completa
    existing_subcategory = Subcategory.objects.without_tenant_filter().filter(
        tenant=tenant,
        category=category,
        name__iexact=name
    ).first()
    
    if existing_subcategory:
        return JsonResponse({
            'success': False,
            'error': f'Já existe uma subcategoria chamada "{name}" na categoria "{category.name}".'
        }, status=400)
    
    try:
        with db_transaction.atomic():
            # Cria subcategoria do tenant (não global)
            subcategory = Subcategory.objects.create(
                tenant=tenant,
                category=category,
                name=name
            )
            
            return JsonResponse({
                'success': True,
                'subcategory': {
                    'id': str(subcategory.id),
                    'name': subcategory.name,
                    'category_id': str(subcategory.category.id)
                }
            })
    except Exception as e:
        # Captura erros de constraint UNIQUE (caso ainda ocorra)
        error_message = str(e)
        if 'UNIQUE constraint' in error_message or 'unique_subcategory_per_tenant' in error_message:
            return JsonResponse({
                'success': False,
                'error': f'Já existe uma subcategoria chamada "{name}" na categoria "{category.name}".'
            }, status=400)
        
        logger.error(f'Erro ao criar subcategoria via AJAX: {str(e)}', exc_info=True)
        return JsonResponse({'success': False, 'error': f'Erro ao criar subcategoria: {str(e)}'}, status=500)


@login_required
def get_subcategory_detail(request, subcategory_id):
    """
    Endpoint AJAX para buscar detalhes de uma subcategoria.
    
    Args:
        request: HttpRequest
        subcategory_id: UUID da subcategoria
        
    Returns:
        JsonResponse com dados da subcategoria (com isolamento multi-tenant).
    """
    tenant = request.tenant
    if not tenant:
        return JsonResponse({'success': False, 'error': 'Nenhuma empresa selecionada.'}, status=400)
    
    try:
        # Busca subcategoria do tenant (com isolamento multi-tenant)
        subcategory = Subcategory.objects.filter(tenant=tenant).get(id=subcategory_id)
        
        return JsonResponse({
            'success': True,
            'subcategory': {
                'id': str(subcategory.id),
                'name': subcategory.name,
                'category_id': str(subcategory.category.id),
                'category_name': subcategory.category.name
            }
        })
    except Subcategory.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Subcategoria não encontrada.'}, status=404)
    except Exception as e:
        logger.error(f'Erro ao buscar subcategoria: {str(e)}', exc_info=True)
        return JsonResponse({'success': False, 'error': f'Erro ao buscar subcategoria: {str(e)}'}, status=500)


@login_required
@require_POST
def edit_subcategory_ajax(request, subcategory_id):
    """
    Endpoint AJAX para editar uma subcategoria existente.
    
    Args:
        request: HttpRequest com dados do formulário (category, name).
        subcategory_id: UUID da subcategoria a editar
        
    Returns:
        JsonResponse com status e dados da subcategoria editada (com isolamento multi-tenant).
    """
    tenant = request.tenant
    if not tenant:
        return JsonResponse({'success': False, 'error': 'Nenhuma empresa selecionada.'}, status=400)
    
    category_id = request.POST.get('category', '').strip()
    name = request.POST.get('name', '').strip()
    
    if not category_id or not name:
        return JsonResponse({'success': False, 'error': 'Categoria e nome são obrigatórios.'}, status=400)
    
    try:
        # Busca subcategoria do tenant (com isolamento multi-tenant)
        subcategory = Subcategory.objects.filter(tenant=tenant).get(id=subcategory_id)
    except Subcategory.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Subcategoria não encontrada.'}, status=404)
    
    try:
        # Busca categoria usando without_tenant_filter para permitir categorias globais
        category = Category.objects.without_tenant_filter().get(id=category_id)
    except Category.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Categoria não encontrada.'}, status=404)
    
    try:
        with db_transaction.atomic():
            # Atualiza subcategoria
            subcategory.name = name
            subcategory.category = category
            subcategory.save()
            
            return JsonResponse({
                'success': True,
                'subcategory': {
                    'id': str(subcategory.id),
                    'name': subcategory.name,
                    'category_id': str(subcategory.category.id)
                }
            })
    except Exception as e:
        logger.error(f'Erro ao editar subcategoria via AJAX: {str(e)}', exc_info=True)
        return JsonResponse({'success': False, 'error': f'Erro ao editar subcategoria: {str(e)}'}, status=500)


@login_required
@require_POST
def delete_subcategory_ajax(request, subcategory_id):
    """
    Endpoint AJAX para excluir uma subcategoria.
    
    Args:
        request: HttpRequest
        subcategory_id: UUID da subcategoria a excluir
        
    Returns:
        JsonResponse com status (com isolamento multi-tenant).
    """
    tenant = request.tenant
    if not tenant:
        return JsonResponse({'success': False, 'error': 'Nenhuma empresa selecionada.'}, status=400)
    
    try:
        # Busca subcategoria do tenant (com isolamento multi-tenant)
        subcategory = Subcategory.objects.filter(tenant=tenant).get(id=subcategory_id)
        
        # Verifica se há transações usando esta subcategoria
        transactions_count = Transaction.objects.filter(
            tenant=tenant,
            subcategory=subcategory
        ).count()
        
        if transactions_count > 0:
            return JsonResponse({
                'success': False,
                'error': f'Não é possível excluir esta subcategoria pois ela está sendo usada em {transactions_count} lançamento(s).'
            }, status=400)
        
        with db_transaction.atomic():
            subcategory_name = subcategory.name
            subcategory.delete()
            
            return JsonResponse({
                'success': True,
                'message': f'Subcategoria "{subcategory_name}" excluída com sucesso!'
            })
    except Subcategory.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Subcategoria não encontrada.'}, status=404)
    except Exception as e:
        logger.error(f'Erro ao excluir subcategoria via AJAX: {str(e)}', exc_info=True)
        return JsonResponse({'success': False, 'error': f'Erro ao excluir subcategoria: {str(e)}'}, status=500)


@login_required
@require_POST
def create_sales_channel_ajax(request):
    """
    Endpoint AJAX para criar um novo canal de venda rapidamente.
    
    Args:
        request: HttpRequest com dados do formulário (name, description).
        
    Returns:
        JsonResponse com status e dados do canal de venda criado.
    """
    tenant = request.tenant
    if not tenant:
        return JsonResponse({'success': False, 'error': 'Nenhuma empresa selecionada.'}, status=400)
    
    name = request.POST.get('name', '').strip()
    description = request.POST.get('description', '').strip()
    
    if not name:
        return JsonResponse({'success': False, 'error': 'Nome é obrigatório.'}, status=400)
    
    try:
        with db_transaction.atomic():
            # Cria canal de venda do tenant (não global)
            sales_channel = SalesChannel.objects.create(
                tenant=tenant,
                name=name,
                description=description if description else None,
                active=True
            )
            
            return JsonResponse({
                'success': True,
                'sales_channel': {
                    'id': str(sales_channel.id),
                    'name': sales_channel.name
                }
            })
    except Exception as e:
        logger.error(f'Erro ao criar canal de venda via AJAX: {str(e)}', exc_info=True)
        return JsonResponse({'success': False, 'error': f'Erro ao criar canal de venda: {str(e)}'}, status=500)
