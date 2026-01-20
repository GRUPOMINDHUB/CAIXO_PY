"""
Views do Dashboard - Indicadores Financeiros e KPIs.

Calcula e exibe todos os indicadores financeiros do sistema:
- Saldo Atual (Fluxo de Caixa)
- A Pagar (Hoje)
- Faturamento Mensal (Competência)
- Despesas Mensais
- Lista de Lançamentos Recentes

Todas as queries respeitam o isolamento multi-tenant através do request.tenant
injetado pelo TenantMiddleware.
"""

import logging
from datetime import date, timedelta, datetime
from decimal import Decimal

from django.contrib.auth.decorators import login_required
from django.db.models import Sum, F, Q
from django.shortcuts import render

from core.models.finance import (
    Transaction, Installment, Category,
    CategoryType, InstallmentStatus, TransactionType
)
from core.models.tenant import Tenant, TenantStatus

logger = logging.getLogger(__name__)


def _get_period_dates(period_filter: str) -> tuple[date, date]:
    """
    Calcula as datas inicial e final baseado no filtro de período.
    
    Args:
        period_filter: String identificando o período ('current_month', '30_days', etc)
        ou None para mês atual
        
    Returns:
        Tupla (data_inicial, data_final) para uso em queries __gte e __lt
    """
    today = date.today()
    
    if period_filter == 'current_month':
        # Mês atual
        first_day = date(today.year, today.month, 1)
        if today.month == 12:
            last_day = date(today.year + 1, 1, 1)
        else:
            last_day = date(today.year, today.month + 1, 1)
        return first_day, last_day
    
    elif period_filter == '30_days':
        # Últimos 30 dias
        first_day = today - timedelta(days=30)
        last_day = today + timedelta(days=1)  # Inclui hoje
        return first_day, last_day
    
    elif period_filter == '90_days':
        # Últimos 90 dias
        first_day = today - timedelta(days=90)
        last_day = today + timedelta(days=1)
        return first_day, last_day
    
    elif period_filter == '6_months':
        # Últimos 6 meses
        first_day = date(today.year, today.month, 1)
        # Subtrai 6 meses
        for _ in range(6):
            if first_day.month == 1:
                first_day = date(first_day.year - 1, 12, 1)
            else:
                first_day = date(first_day.year, first_day.month - 1, 1)
        last_day = today + timedelta(days=1)
        return first_day, last_day
    
    elif period_filter == '12_months':
        # Últimos 12 meses
        first_day = date(today.year, today.month, 1)
        # Subtrai 12 meses
        for _ in range(12):
            if first_day.month == 1:
                first_day = date(first_day.year - 1, 12, 1)
            else:
                first_day = date(first_day.year, first_day.month - 1, 1)
        last_day = today + timedelta(days=1)
        return first_day, last_day
    
    elif period_filter == 'custom':
        # Período personalizado (vem via query params date_start e date_end)
        # Se não vier, usa mês atual
        return _get_period_dates('current_month')
    
    else:
        # Default: mês atual
        return _get_period_dates('current_month')


@login_required
def dashboard_view(request):
    """
    View principal do Dashboard com métricas financeiras em tempo real.
    
    Calcula indicadores filtrados pelo tenant do usuário logado:
    - Saldo Atual: Entradas (receitas pagas) - Saídas (despesas pagas)
    - A Pagar Hoje: Despesas com vencimento hoje e não pagas
    - Faturamento Mensal: Receitas do mês atual (competência)
    - Despesas Mensais: Despesas do mês atual (competência)
    
    Performance: Utiliza aggregate() e Sum() para cálculos diretos no banco,
    evitando carregar objetos na memória.
    
    Args:
        request: HttpRequest com request.user e request.tenant (injetado pelo middleware)
        
    Returns:
        HttpResponse com template do dashboard renderizado
    """
    # Obtém o tenant do usuário (injetado pelo TenantMiddleware)
    # O middleware injeta request.tenant automaticamente baseado na sessão
    tenant = getattr(request, 'tenant', None)
    
    # Se usuário não tem tenant (Admin Master), mostra dashboard vazio mas sem erro
    # Admin Master pode ver dados agregados de todos os tenants no futuro
    if not tenant:
        # all_tenants já está no request (injetado pelo middleware)
        context = {
            'tenant': None,
            'user': request.user,
            'today': date.today(),
            'saldo_atual': Decimal('0.00'),
            'a_pagar_hoje': Decimal('0.00'),
            'faturamento_mensal': Decimal('0.00'),
            'despesas_mensais': Decimal('0.00'),
            'total_entradas': Decimal('0.00'),
            'total_saidas': Decimal('0.00'),
            'lancamentos_recentes': [],
            'whatsapp_conectado': False,
            'is_admin_master': True,
        }
        return render(request, 'core/dashboard.html', context)
    
    try:
        # Data atual
        today = date.today()
        
        # Processa filtro de período
        period_filter = request.GET.get('period', 'current_month')
        date_start = request.GET.get('date_start')
        date_end = request.GET.get('date_end')
        
        # Se período personalizado, tenta usar as datas fornecidas
        if period_filter == 'custom' and date_start and date_end:
            try:
                first_day = datetime.strptime(date_start, '%Y-%m-%d').date()
                last_day = datetime.strptime(date_end, '%Y-%m-%d').date()
                # Adiciona 1 dia ao last_day para incluir o dia final na query __lt
                last_day = last_day + timedelta(days=1)
            except (ValueError, TypeError):
                # Se datas inválidas, usa mês atual
                first_day, last_day = _get_period_dates('current_month')
                period_filter = 'current_month'
        else:
            first_day, last_day = _get_period_dates(period_filter)
        
        # Para compatibilidade com código existente (mantém variáveis antigas)
        first_day_month = first_day
        last_day_month = last_day
        
        # ============================================
        # 1. SALDO ATUAL (FLUXO DE CAIXA)
        # ============================================
        # Soma de Installments pagas: Receitas (entradas) - Despesas (saídas)
        # Filtra por transaction_type para diferenciar receitas de despesas
        
        # Total de entradas (receitas pagas) - filtrado por período de pagamento
        total_entradas = Installment.objects.filter(
            tenant=tenant,
            transaction__transaction_type=TransactionType.RECEITA,
            status=InstallmentStatus.PAGO,
            payment_date__isnull=False,
            payment_date__gte=first_day,
            payment_date__lt=last_day
        ).aggregate(
            total=Sum(F('amount') + F('penalty_amount'))
        )['total'] or Decimal('0.00')
        
        # Total de saídas (despesas pagas) - filtrado por período de pagamento
        total_saidas = Installment.objects.filter(
            tenant=tenant,
            transaction__transaction_type=TransactionType.DESPESA,
            status=InstallmentStatus.PAGO,
            payment_date__isnull=False,
            payment_date__gte=first_day,
            payment_date__lt=last_day
        ).aggregate(
            total=Sum(F('amount') + F('penalty_amount'))
        )['total'] or Decimal('0.00')
        
        # Saldo = Entradas - Saídas
        saldo_atual = total_entradas - total_saidas
        
        # ============================================
        # 2. A PAGAR HOJE
        # ============================================
        # Soma de Installments do tipo despesa com due_date = hoje e status = PENDENTE
        # Filtra apenas despesas (não receitas) que vencem hoje e não foram pagas
        
        a_pagar_hoje = Installment.objects.filter(
            tenant=tenant,
            transaction__transaction_type=TransactionType.DESPESA,
            status=InstallmentStatus.PENDENTE,
            due_date=today
        ).aggregate(
            total=Sum(F('amount') + F('penalty_amount'))
        )['total'] or Decimal('0.00')
        
        # ============================================
        # 3. FATURAMENTO MENSAL (COMPETÊNCIA)
        # ============================================
        # Soma de Transactions do tipo receita cuja competence_date pertence ao mês atual
        
        faturamento_mensal = Transaction.objects.filter(
            tenant=tenant,
            transaction_type=TransactionType.RECEITA,
            competence_date__gte=first_day_month,
            competence_date__lt=last_day_month
        ).aggregate(
            total=Sum('amount')
        )['total'] or Decimal('0.00')
        
        # ============================================
        # 4. DESPESAS MENSAIS (COMPETÊNCIA)
        # ============================================
        # Soma de Transactions do tipo despesa cuja competence_date pertence ao mês atual
        # Inclui todas as categorias de despesa (FIXA, VARIAVEL, INVESTIMENTO, ESTOQUE)
        
        despesas_mensais = Transaction.objects.filter(
            tenant=tenant,
            transaction_type=TransactionType.DESPESA,
            competence_date__gte=first_day_month,
            competence_date__lt=last_day_month
        ).aggregate(
            total=Sum('amount')
        )['total'] or Decimal('0.00')
        
        # ============================================
        # 5. LANÇAMENTOS RECENTES
        # ============================================
        # Últimas 5 Installments do período, ordenadas por data de criação
        # Inclui informações de status, categoria e valor
        
        lancamentos_recentes = Installment.objects.filter(
            tenant=tenant,
            due_date__gte=first_day,
            due_date__lt=last_day
        ).select_related(
            'transaction',
            'transaction__category',
            'transaction__subcategory'
        ).order_by('-created_at')[:5]
        
        # ============================================
        # 6. STATUS DO WHATSAPP
        # ============================================
        # Verifica se o campo evolution_instance_name está preenchido
        # Simula o status de conexão (verde se preenchido, vermelho se vazio)
        
        whatsapp_conectado = bool(tenant.evolution_instance_name and tenant.evolution_instance_name.strip())
        
        # Prepara contexto para o template
        context = {
            'tenant': tenant,
            'user': request.user,
            'today': today,
            
            # Métricas principais
            'saldo_atual': saldo_atual,
            'a_pagar_hoje': a_pagar_hoje,
            'faturamento_mensal': faturamento_mensal,
            'despesas_mensais': despesas_mensais,
            
            # Dados auxiliares
            'total_entradas': total_entradas,
            'total_saidas': total_saidas,
            
            # Lista de lançamentos
            'lancamentos_recentes': lancamentos_recentes,
            
            # Status WhatsApp
            'whatsapp_conectado': whatsapp_conectado,
            
            # Filtros de período
            'period_filter': period_filter,
            'date_start': date_start if period_filter == 'custom' else None,
            'date_end': date_end if period_filter == 'custom' else None,
            'first_day': first_day,
            'last_day': last_day,
        }
        
        return render(request, 'core/dashboard.html', context)
        
    except Exception as e:
        logger.error(f'Erro ao calcular indicadores do dashboard para tenant {tenant.id}: {str(e)}', exc_info=True)
        # Retorna dashboard com erro
        context = {
            'tenant': tenant,
            'user': request.user,
            'today': today,
            'error': 'Erro ao calcular indicadores. Tente novamente mais tarde.',
        }
        return render(request, 'core/dashboard.html', context)
