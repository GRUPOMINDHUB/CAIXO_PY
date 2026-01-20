"""
Formulários do sistema Caixô.

Define formulários Django para cadastro e edição de modelos.
"""

from django import forms
from django.core.exceptions import ValidationError

from core.models.tenant import Tenant, TenantPlan, TenantStatus


class TenantForm(forms.ModelForm):
    """
    Formulário para cadastro e edição de Tenants (Empresas).
    
    Valida CNPJ automaticamente e organiza campos em seções lógicas.
    """
    
    class Meta:
        model = Tenant
        fields = [
            'name',
            'cnpj',
            'plan',
            'status',
            'billing_day_weekly',
            'billing_day_monthly',
            'evolution_instance_name',
        ]
        widgets = {
            'name': forms.TextInput(attrs={
                'class': 'w-full px-4 py-2 rounded-lg outline-none transition',
                'style': 'border: 1px solid #E9E4DB; color: #2D2926; background-color: #FFFFFF;',
                'placeholder': 'Nome completo da empresa/loja',
                'onfocus': "this.style.borderColor='#D4AF37'; this.style.boxShadow='0 0 0 3px rgba(212, 175, 55, 0.1)';",
                'onblur': "this.style.borderColor='#E9E4DB'; this.style.boxShadow='none';"
            }),
            'cnpj': forms.TextInput(attrs={
                'class': 'w-full px-4 py-2 rounded-lg outline-none transition',
                'style': 'border: 1px solid #E9E4DB; color: #2D2926; background-color: #FFFFFF;',
                'placeholder': '00.000.000/0000-00',
                'onfocus': "this.style.borderColor='#D4AF37'; this.style.boxShadow='0 0 0 3px rgba(212, 175, 55, 0.1)';",
                'onblur': "this.style.borderColor='#E9E4DB'; this.style.boxShadow='none';"
            }),
            'plan': forms.Select(attrs={
                'class': 'w-full px-4 py-2 rounded-lg outline-none transition',
                'style': 'border: 1px solid #E9E4DB; color: #2D2926; background-color: #FFFFFF;',
                'onfocus': "this.style.borderColor='#D4AF37'; this.style.boxShadow='0 0 0 3px rgba(212, 175, 55, 0.1)';",
                'onblur': "this.style.borderColor='#E9E4DB'; this.style.boxShadow='none';"
            }),
            'status': forms.Select(attrs={
                'class': 'w-full px-4 py-2 rounded-lg outline-none transition',
                'style': 'border: 1px solid #E9E4DB; color: #2D2926; background-color: #FFFFFF;',
                'onfocus': "this.style.borderColor='#D4AF37'; this.style.boxShadow='0 0 0 3px rgba(212, 175, 55, 0.1)';",
                'onblur': "this.style.borderColor='#E9E4DB'; this.style.boxShadow='none';"
            }),
            'billing_day_weekly': forms.NumberInput(attrs={
                'class': 'w-full px-4 py-2 rounded-lg outline-none transition',
                'style': 'border: 1px solid #E9E4DB; color: #2D2926; background-color: #FFFFFF;',
                'min': '0',
                'max': '6',
                'onfocus': "this.style.borderColor='#D4AF37'; this.style.boxShadow='0 0 0 3px rgba(212, 175, 55, 0.1)';",
                'onblur': "this.style.borderColor='#E9E4DB'; this.style.boxShadow='none';"
            }),
            'billing_day_monthly': forms.NumberInput(attrs={
                'class': 'w-full px-4 py-2 rounded-lg outline-none transition',
                'style': 'border: 1px solid #E9E4DB; color: #2D2926; background-color: #FFFFFF;',
                'min': '1',
                'max': '31',
                'onfocus': "this.style.borderColor='#D4AF37'; this.style.boxShadow='0 0 0 3px rgba(212, 175, 55, 0.1)';",
                'onblur': "this.style.borderColor='#E9E4DB'; this.style.boxShadow='none';"
            }),
            'evolution_instance_name': forms.TextInput(attrs={
                'class': 'w-full px-4 py-2 rounded-lg outline-none transition',
                'style': 'border: 1px solid #E9E4DB; color: #2D2926; background-color: #FFFFFF;',
                'placeholder': 'Nome da instância na Evolution API',
                'onfocus': "this.style.borderColor='#D4AF37'; this.style.boxShadow='0 0 0 3px rgba(212, 175, 55, 0.1)';",
                'onblur': "this.style.borderColor='#E9E4DB'; this.style.boxShadow='none';"
            }),
        }
        labels = {
            'name': 'Razão Social',
            'cnpj': 'CNPJ',
            'plan': 'Plano',
            'status': 'Status',
            'billing_day_weekly': 'Dia da Semana (Faturamento Semanal)',
            'billing_day_monthly': 'Dia do Mês (Faturamento Mensal)',
            'evolution_instance_name': 'Instância Evolution API',
        }
        help_texts = {
            'billing_day_weekly': '0=Domingo, 1=Segunda, 2=Terça, ..., 6=Sábado',
            'billing_day_monthly': 'Dia do mês (1-31) para solicitação de faturamento mensal',
            'evolution_instance_name': 'Nome da instância do WhatsApp configurada na Evolution API',
        }
    
    def clean_cnpj(self):
        """
        Valida e limpa o CNPJ antes de salvar.
        
        Remove caracteres especiais e valida o formato.
        """
        cnpj = self.cleaned_data.get('cnpj')
        if cnpj:
            # Remove caracteres especiais
            from core.utils.cnpj import clean_cnpj, validate_cnpj
            cnpj_limpo = clean_cnpj(cnpj)
            
            # Valida o CNPJ
            if not validate_cnpj(cnpj_limpo):
                raise ValidationError('CNPJ inválido. Verifique o número informado.')
            
            return cnpj_limpo
        
        return cnpj
    
    def clean_evolution_instance_name(self):
        """
        Valida se o tenant pode adicionar mais uma instância WhatsApp.
        
        Verifica o limite do plano antes de permitir cadastro.
        """
        instance_name = self.cleaned_data.get('evolution_instance_name')
        
        # Se não está preenchendo instância, não valida
        if not instance_name or not instance_name.strip():
            return instance_name
        
        # Se estiver editando, verifica o tenant atual
        if self.instance and self.instance.pk:
            tenant = self.instance
            # Se já tinha instância, permite manter ou alterar
            if tenant.evolution_instance_name:
                return instance_name
            # Se não tinha e está adicionando, valida limite
            if not tenant.can_add_instance():
                plan_display = tenant.get_plan_display()
                max_instances = tenant.get_max_instances()
                raise ValidationError(
                    f'Limite de números atingido para o plano {plan_display}. '
                    f'O plano permite até {max_instances} instância(s) WhatsApp. '
                    f'Atualize para um plano superior para adicionar mais instâncias.'
                )
        else:
            # Criando novo tenant: valida limite do plano selecionado
            plan = self.cleaned_data.get('plan')
            if plan:
                from core.models.tenant import TenantPlan
                limits = {
                    TenantPlan.STARTER: 1,
                    TenantPlan.PLUS: 2,
                    TenantPlan.PRO: 5,
                }
                max_instances = limits.get(plan, 1)
                # Se está tentando cadastrar instância na criação, valida
                if instance_name and max_instances < 1:
                    plan_display = dict(TenantPlan.choices).get(plan, plan)
                    raise ValidationError(
                        f'O plano {plan_display} não permite instâncias WhatsApp. '
                        f'Escolha um plano superior.'
                    )
        
        return instance_name