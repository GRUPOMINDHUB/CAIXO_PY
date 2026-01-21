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
            'neighborhood',
            'city',
            'plan',
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
            'neighborhood': forms.TextInput(attrs={
                'class': 'w-full px-4 py-2 rounded-lg outline-none transition',
                'style': 'border: 1px solid #E9E4DB; color: #2D2926; background-color: #FFFFFF;',
                'placeholder': 'Ex: Centro, Jardins, Savassi...',
                'onfocus': "this.style.borderColor='#D4AF37'; this.style.boxShadow='0 0 0 3px rgba(212, 175, 55, 0.1)';",
                'onblur': "this.style.borderColor='#E9E4DB'; this.style.boxShadow='none';"
            }),
            'city': forms.TextInput(attrs={
                'class': 'w-full px-4 py-2 rounded-lg outline-none transition',
                'style': 'border: 1px solid #E9E4DB; color: #2D2926; background-color: #FFFFFF;',
                'placeholder': 'Ex: São Paulo, Rio de Janeiro...',
                'onfocus': "this.style.borderColor='#D4AF37'; this.style.boxShadow='0 0 0 3px rgba(212, 175, 55, 0.1)';",
                'onblur': "this.style.borderColor='#E9E4DB'; this.style.boxShadow='none';"
            }),
            'plan': forms.Select(attrs={
                'class': 'w-full px-4 py-2 rounded-lg outline-none transition',
                'style': 'border: 1px solid #E9E4DB; color: #2D2926; background-color: #FFFFFF;',
                'onfocus': "this.style.borderColor='#D4AF37'; this.style.boxShadow='0 0 0 3px rgba(212, 175, 55, 0.1)';",
                'onblur': "this.style.borderColor='#E9E4DB'; this.style.boxShadow='none';"
            }),
        }
        labels = {
            'name': 'Razão Social',
            'cnpj': 'CNPJ',
            'neighborhood': 'Bairro',
            'city': 'Cidade',
            'plan': 'Plano',
        }
        help_texts = {}
    
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
    