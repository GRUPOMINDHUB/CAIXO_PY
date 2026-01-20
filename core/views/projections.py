"""
Views de Projeções Financeiras com Inteligência Externa.

Combina dados financeiros (despesas e receitas projetadas) com
inteligência externa (clima, eventos, feriados) para fornecer
uma visão antecipada do futuro financeiro do restaurante.
"""

import logging
from datetime import date, timedelta, datetime
from decimal import Decimal

from django.contrib.auth.decorators import login_required
from django.db.models import Sum, F, Q
from django.shortcuts import render
from django.core.cache import cache

from core.models.finance import (
    Transaction, Installment,
    InstallmentStatus, TransactionType
)
from core.services.external_data import get_external_data_service

logger = logging.getLogger(__name__)


def _get_period_dates(period_filter: str) -> tuple[date, date]:
    """
    Calcula as datas inicial e final baseado no filtro de período.
    
    Args:
        period_filter: String identificando o período ('today', '7_days', etc)
        
    Returns:
        Tupla (data_inicial, data_final) para uso em queries __gte e __lt
    """
    today = date.today()
    
    if period_filter == 'today':
        # Hoje
        return today, today + timedelta(days=1)
    
    elif period_filter == '7_days':
        # Próximos 7 dias
        return today, today + timedelta(days=7)
    
    elif period_filter == '15_days':
        # Próximos 15 dias
        return today, today + timedelta(days=15)
    
    elif period_filter == 'next_month':
        # Mês que vem
        if today.month == 12:
            first_day = date(today.year + 1, 1, 1)
            last_day = date(today.year + 1, 2, 1)
        else:
            first_day = date(today.year, today.month + 1, 1)
            if today.month + 1 == 12:
                last_day = date(today.year + 1, 1, 1)
            else:
                last_day = date(today.year, today.month + 2, 1)
        return first_day, last_day
    
    elif period_filter == 'custom':
        # Período personalizado (vem via query params)
        return _get_period_dates('7_days')
    
    else:
        # Default: próximos 7 dias
        return _get_period_dates('7_days')


@login_required
def projections_view(request):
    """
    View principal de Projeções com dados financeiros e inteligência externa.
    
    Calcula:
    - Despesas projetadas (parcelas pendentes no período)
    - Receitas projetadas (parcelas de receita no período)
    - Saldo previsto ao final do período
    - Alertas de clima e eventos
    
    Args:
        request: HttpRequest com request.user e request.tenant
        
    Returns:
        HttpResponse com template de projeções renderizado
    """
    tenant = getattr(request, 'tenant', None)
    
    if not tenant:
        context = {
            'tenant': None,
            'user': request.user,
            'today': date.today(),
            'error': 'É necessário estar vinculado a uma empresa para visualizar projeções.',
        }
        return render(request, 'core/finance/projections.html', context)
    
    try:
        today = date.today()
        
        # Processa filtro de período
        period_filter = request.GET.get('period', '7_days')
        date_start = request.GET.get('date_start')
        date_end = request.GET.get('date_end')
        
        # Se período personalizado, tenta usar as datas fornecidas
        if period_filter == 'custom' and date_start and date_end:
            try:
                first_day = datetime.strptime(date_start, '%Y-%m-%d').date()
                last_day = datetime.strptime(date_end, '%Y-%m-%d').date()
                # Adiciona 1 dia ao last_day para incluir o dia final
                last_day = last_day + timedelta(days=1)
            except (ValueError, TypeError):
                first_day, last_day = _get_period_dates('7_days')
                period_filter = '7_days'
        else:
            first_day, last_day = _get_period_dates(period_filter)
        
        # ============================================
        # 1. SALDO ATUAL (CAIXA)
        # ============================================
        # Soma de Installments pagas até hoje
        
        total_entradas = Installment.objects.filter(
            tenant=tenant,
            transaction__transaction_type=TransactionType.RECEITA,
            status=InstallmentStatus.PAGO,
            payment_date__isnull=False
        ).aggregate(
            total=Sum(F('amount') + F('penalty_amount'))
        )['total'] or Decimal('0.00')
        
        total_saidas = Installment.objects.filter(
            tenant=tenant,
            transaction__transaction_type=TransactionType.DESPESA,
            status=InstallmentStatus.PAGO,
            payment_date__isnull=False
        ).aggregate(
            total=Sum(F('amount') + F('penalty_amount'))
        )['total'] or Decimal('0.00')
        
        saldo_atual = total_entradas - total_saidas
        
        # ============================================
        # 2. DESPESAS PROJETADAS
        # ============================================
        # Installments pendentes com vencimento no período
        
        despesas_projetadas = Installment.objects.filter(
            tenant=tenant,
            transaction__transaction_type=TransactionType.DESPESA,
            status=InstallmentStatus.PENDENTE,
            due_date__gte=first_day,
            due_date__lt=last_day
        ).select_related('transaction', 'transaction__category', 'transaction__subcategory')
        
        total_despesas_projetadas = despesas_projetadas.aggregate(
            total=Sum(F('amount') + F('penalty_amount'))
        )['total'] or Decimal('0.00')
        
        # Top 10 maiores despesas
        maiores_despesas = despesas_projetadas.order_by('-amount')[:10]
        
        # ============================================
        # 3. RECEITAS PROJETADAS
        # ============================================
        # Installments de receita com vencimento no período (mesmo que pagas)
        
        receitas_projetadas = Installment.objects.filter(
            tenant=tenant,
            transaction__transaction_type=TransactionType.RECEITA,
            due_date__gte=first_day,
            due_date__lt=last_day
        ).aggregate(
            total=Sum(F('amount') + F('penalty_amount'))
        )['total'] or Decimal('0.00')
        
        # ============================================
        # 4. SALDO PREVISTO
        # ============================================
        # Saldo Atual + Receitas Projetadas - Despesas Projetadas
        
        saldo_previsto = saldo_atual + receitas_projetadas - total_despesas_projetadas
        
        # ============================================
        # 5. ESCADA FINANCEIRA (Dia a dia)
        # ============================================
        # Calcula o saldo acumulado dia a dia conforme os boletos vencem
        
        escada_financeira = []
        current_balance = saldo_atual
        current_date = first_day
        
        # Agrupa despesas e receitas por data
        despesas_por_data = {}
        receitas_por_data = {}
        
        for installment in Installment.objects.filter(
            tenant=tenant,
            due_date__gte=first_day,
            due_date__lt=last_day
        ).select_related('transaction'):
            due_date = installment.due_date
            amount = installment.amount + (installment.penalty_amount or Decimal('0.00'))
            
            if installment.transaction.transaction_type == TransactionType.DESPESA:
                if installment.status == InstallmentStatus.PENDENTE:
                    # Só conta despesas pendentes
                    if due_date not in despesas_por_data:
                        despesas_por_data[due_date] = Decimal('0.00')
                    despesas_por_data[due_date] += amount
            else:  # RECEITA
                # Conta receitas (pagas ou não)
                if due_date not in receitas_por_data:
                    receitas_por_data[due_date] = Decimal('0.00')
                receitas_por_data[due_date] += amount
        
        # Monta escada dia a dia
        while current_date < last_day:
            despesa_dia = despesas_por_data.get(current_date, Decimal('0.00'))
            receita_dia = receitas_por_data.get(current_date, Decimal('0.00'))
            
            current_balance = current_balance + receita_dia - despesa_dia
            
            escada_financeira.append({
                'date': current_date,
                'balance': current_balance,
                'expense': despesa_dia,
                'revenue': receita_dia,
            })
            
            current_date += timedelta(days=1)
        
        # ============================================
        # 6. INTELIGÊNCIA EXTERNA
        # ============================================
        # Busca dados de clima, feriados e eventos
        
        external_service = get_external_data_service()
        
        # Clima
        weather_data = {}
        if tenant.city:
            weather_data = external_service.get_weather_forecast(
                city=tenant.city,
                neighborhood=tenant.neighborhood,
                start_date=first_day,
                end_date=last_day
            )
        
        # Feriados
        holidays_list = external_service.get_holidays(
            state='BR',  # TODO: Adicionar campo state no Tenant
            start_date=first_day,
            end_date=last_day
        )
        
        # Eventos locais
        events_list = []
        if tenant.city:
            events_list = external_service.get_local_events(
                city=tenant.city,
                neighborhood=tenant.neighborhood,
                start_date=first_day,
                end_date=last_day
            )
        
        # Prepara contexto
        context = {
            'tenant': tenant,
            'user': request.user,
            'today': today,
            
            # Filtros de período
            'period_filter': period_filter,
            'date_start': date_start if period_filter == 'custom' else None,
            'date_end': date_end if period_filter == 'custom' else None,
            'first_day': first_day,
            'last_day': last_day,
            
            # Dados financeiros
            'saldo_atual': saldo_atual,
            'receitas_projetadas': receitas_projetadas,
            'despesas_projetadas': total_despesas_projetadas,
            'saldo_previsto': saldo_previsto,
            'maiores_despesas': maiores_despesas,
            'escada_financeira': escada_financeira,
            
            # Inteligência externa
            'weather_data': weather_data,
            'holidays_list': holidays_list,
            'events_list': events_list,
        }
        
        return render(request, 'core/finance/projections.html', context)
        
    except Exception as e:
        logger.error(f'Erro ao calcular projeções para tenant {tenant.id}: {str(e)}', exc_info=True)
        context = {
            'tenant': tenant,
            'user': request.user,
            'today': today,
            'error': 'Erro ao calcular projeções. Tente novamente mais tarde.',
        }
        return render(request, 'core/finance/projections.html', context)
