"""
Service de Inteligência Artificial para parsing de mensagens financeiras.

Utiliza OpenAI GPT-4o-mini para extrair informações estruturadas de mensagens
de texto recebidas via WhatsApp, seguindo regras contábeis específicas.

Características:
- Extração automática de valores, datas, categorias e descrições
- Regra de retroação de competência para contas de consumo
- Vínculo semântico com o Glossário de Despesas
- Output estruturado em JSON
"""

import json
import logging
from typing import Dict, List, Optional
from decimal import Decimal, InvalidOperation
from datetime import datetime, date

import openai
from django.conf import settings

logger = logging.getLogger(__name__)


class IAProcessor:
    """
    Processador de Inteligência Artificial para análise de mensagens financeiras.
    
    Utiliza OpenAI GPT-4o-mini para extrair dados estruturados de mensagens
    textuais sobre gastos e receitas, aplicando regras contábeis específicas.
    """
    
    def __init__(self):
        """
        Inicializa o processador de IA configurando a API da OpenAI.
        """
        api_key = settings.OPENAI_API_KEY
        if not api_key or api_key == 'sk-sua-chave-openai-aqui':
            logger.warning(
                'OPENAI_API_KEY não configurada. Configure no arquivo .env'
            )
        
        # Configura cliente OpenAI
        self.client = openai.OpenAI(api_key=api_key) if api_key else None
    
    def parse_financial_message(
        self,
        text: str,
        context_categories: List[Dict[str, str]]
    ) -> Dict:
        """
        Processa uma mensagem de texto e extrai informações financeiras estruturadas.
        
        Utiliza GPT-4o-mini para analisar o texto e extrair:
        - Valor monetário
        - Descrição da transação
        - Data de caixa (quando houve movimentação)
        - Data de competência (fato gerador - com regra de retroação)
        - Categoria e subcategoria sugeridas baseadas no Glossário
        
        Regra de Retroação (Regime de Competência):
        - Se for conta de consumo (Luz, Água, Internet, Aluguel, Sindicato),
          a data de competência deve ser obrigatoriamente o mês anterior à data de caixa.
        - Isso reflete o fato gerador do consumo do mês anterior.
        
        Args:
            text: Texto da mensagem recebida (ex: "Paguei R$ 500 de luz hoje")
            context_categories: Lista de categorias/subcategorias do Glossário disponíveis
                               Formato: [{'category': 'Despesa Fixa', 'subcategory': 'Contas de consumo'}, ...]
        
        Returns:
            Dict com os dados extraídos:
            {
                'valor': Decimal,
                'descricao': str,
                'data_caixa': 'YYYY-MM-DD',
                'data_competencia': 'YYYY-MM-DD',
                'categoria_sugerida': str,
                'subcategoria_sugerida': str,
                'fornecedor': str (opcional),
                'confianca': float (0.0 a 1.0)
            }
        
        Raises:
            ValueError: Se a IA não conseguir extrair dados válidos
            openai.APIError: Se houver erro na comunicação com a API
        """
        if not self.client:
            raise ValueError('Cliente OpenAI não configurado. Verifique OPENAI_API_KEY no .env')
        
        try:
            # Prepara o contexto de categorias para a IA
            categories_context = self._format_categories_context(context_categories)
            
            # System Prompt: Define o papel e as regras para a IA
            system_prompt = self._build_system_prompt(categories_context)
            
            # User Prompt: A mensagem do usuário a ser analisada
            user_prompt = f"""Analise a seguinte mensagem sobre um gasto ou receita financeira:

"{text}"

Extraia todas as informações financeiras relevantes seguindo as regras contábeis especificadas."""
            
            logger.info(f'Enviando mensagem para OpenAI: {text[:50]}...')
            
            # Chama a API da OpenAI
            response = self.client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=0.3,  # Baixa temperatura para respostas mais determinísticas
                response_format={"type": "json_object"}  # Força resposta JSON estruturada
            )
            
            # Extrai o conteúdo da resposta
            content = response.choices[0].message.content
            logger.info(f'Resposta da OpenAI recebida: {content[:200]}...')
            
            # Parse do JSON retornado
            extracted_data = json.loads(content)
            
            # Valida e normaliza os dados extraídos
            normalized_data = self._normalize_extracted_data(extracted_data, text)
            
            logger.info(f'Dados extraídos e normalizados com sucesso: {normalized_data}')
            
            return normalized_data
            
        except json.JSONDecodeError as e:
            logger.error(f'Erro ao fazer parse do JSON retornado pela IA: {str(e)}')
            logger.error(f'Conteúdo recebido: {content[:500]}')
            raise ValueError(
                'A IA retornou dados em formato inválido. '
                'Tente reenviar a mensagem de forma mais clara.'
            )
        
        except openai.APIError as e:
            logger.error(f'Erro na API da OpenAI: {str(e)}')
            raise ValueError(
                'Erro ao processar mensagem com IA. '
                'Verifique a configuração da API key ou tente novamente mais tarde.'
            )
        
        except Exception as e:
            logger.error(f'Erro inesperado ao processar mensagem: {str(e)}')
            raise ValueError(
                'Erro inesperado ao processar mensagem. '
                'Por favor, tente novamente ou entre em contato com o suporte.'
            )
    
    def _build_system_prompt(self, categories_context: str) -> str:
        """
        Constrói o System Prompt com todas as regras contábeis e instruções.
        
        Args:
            categories_context: String formatada com as categorias disponíveis
            
        Returns:
            System prompt completo em português
        """
        return f"""Você é um contador especializado em restaurantes e empresas B2B, com expertise em 
regime de competência e fluxo de caixa.

Sua tarefa é extrair informações financeiras de mensagens textuais sobre gastos ou receitas, 
seguindo rigorosamente as regras contábeis abaixo:

REGRAS DE EXTRAÇÃO:

1. VALOR:
   - Sempre extraia o valor monetário em Reais (R$)
   - Aceite formatos: "500", "R$ 500", "500,00", "R$ 500,00", "quinhentos reais"
   - Converta para número decimal (ex: 500.00)

2. DESCRIÇÃO:
   - Extraia uma descrição clara e objetiva do que foi pago/comprado
   - Exemplo: "Paguei luz" -> "Pagamento conta de luz"
   - Exemplo: "Compra de ingredientes" -> "Compra de ingredientes"

3. DATA DE CAIXA (data_caixa):
   - Data em que o dinheiro realmente saiu/entrou (movimentação bancária)
   - Se mencionada explicitamente: use a data mencionada
   - Se não mencionada: assuma a data de hoje (formato ISO: YYYY-MM-DD)
   - Formato obrigatório: YYYY-MM-DD

4. DATA DE COMPETÊNCIA (data_competencia) - REGRA DE OURO:
   - Esta é a data do fato gerador (quando o gasto/receita ocorreu realmente)
   - REGRA ESPECIAL: Se a descrição mencionar "Luz", "Água", "Internet", "Aluguel" ou "Sindicato":
     * A data de competência DEVE SER OBRIGATORIAMENTE o mês anterior à data de caixa
     * Exemplo: Se pagou luz hoje (2025-01-15), a competência é do mês anterior (2024-12-01)
     * Isso reflete que a conta é referente ao consumo do mês anterior
   - Para outros itens: use a mesma data da data de caixa
   - Formato obrigatório: YYYY-MM-DD (use o dia 01 do mês para contas de consumo)

5. CATEGORIZAÇÃO:
   - Use EXCLUSIVAMENTE as categorias e subcategorias fornecidas abaixo
   - Compare a descrição com as subcategorias disponíveis
   - Escolha a categoria e subcategoria que melhor se encaixam semanticamente
   - Se não houver correspondência exata, escolha a mais próxima
   - IMPORTANTE: Se não tiver 100% de certeza da subcategoria, reduza o valor de "confianca" para abaixo de 0.8
   - Se confianca < 0.8, adicione um campo "aviso_categoria" no JSON explicando a incerteza

CATEGORIAS DISPONÍVEIS:
{categories_context}

6. FORNECEDOR (opcional):
   - Extraia o nome do fornecedor/prestador de serviço se mencionado
   - Exemplo: "Pagamento para Copel" -> fornecedor: "Copel"

7. PAGAMENTO REALIZADO (pagamento_realizado):
   - Se a mensagem indicar que o pagamento já foi realizado (ex: "Paguei hoje", "Já paguei", "Pagamento efetuado"),
     defina pagamento_realizado como true
   - Se pagamento_realizado for true e houver um valor pago diferente (ex: "Paguei R$ 550, mas devia R$ 500"),
     extraia o valor pago em "valor_pago"
   - Se não mencionado, assuma pagamento_realizado como false

OUTPUT:
Retorne APENAS um JSON válido no seguinte formato (sem markdown, sem comentários):
{{
    "valor": 500.00,
    "descricao": "Pagamento conta de luz",
    "data_caixa": "2025-01-15",
    "data_competencia": "2024-12-01",
    "categoria_sugerida": "Despesa Fixa",
    "subcategoria_sugerida": "Contas de consumo",
    "fornecedor": "Copel",
    "confianca": 0.95,
    "pagamento_realizado": false,
    "valor_pago": null,
    "aviso_categoria": null
}}

CAMPOS OBRIGATÓRIOS: valor, descricao, data_caixa, data_competencia, categoria_sugerida, subcategoria_sugerida, confianca
CAMPOS OPCIONAIS: fornecedor, pagamento_realizado (default: false), valor_pago (default: null), aviso_categoria (default: null)

NOTA SOBRE aviso_categoria:
- Use este campo APENAS se confianca < 0.8
- Explique brevemente a incerteza (ex: "Não encontrei correspondência exata. Escolhi a mais próxima: 'Material geral'")

IMPORTANTE:
- Sempre retorne JSON válido
- Sempre respeite a regra de retroação para contas de consumo
- Use as categorias exatas do glossário fornecido
- Se não tiver 100% de certeza da subcategoria, reduza "confianca" para < 0.8 e adicione "aviso_categoria"
- Se o pagamento já foi realizado, defina pagamento_realizado como true
- Se houver multas/juros (valor pago > valor original), inclua em valor_pago"""
    
    def _format_categories_context(self, context_categories: List[Dict[str, str]]) -> str:
        """
        Formata a lista de categorias para inclusão no prompt da IA.
        
        Args:
            context_categories: Lista de dicionários com category e subcategory
            
        Returns:
            String formatada com todas as categorias e subcategorias
        """
        if not context_categories:
            return "Nenhuma categoria disponível."
        
        # Agrupa subcategorias por categoria
        categories_dict = {}
        for item in context_categories:
            cat = item.get('category', 'Desconhecida')
            subcat = item.get('subcategory', 'Desconhecida')
            if cat not in categories_dict:
                categories_dict[cat] = []
            categories_dict[cat].append(subcat)
        
        # Formata em string legível
        formatted = []
        for category, subcategories in categories_dict.items():
            subcats_str = ", ".join(subcategories)
            formatted.append(f"- {category}: {subcats_str}")
        
        return "\n".join(formatted)
    
    def _normalize_extracted_data(self, extracted_data: Dict, original_text: str) -> Dict:
        """
        Valida e normaliza os dados extraídos pela IA.
        
        Garante que todos os campos obrigatórios estejam presentes e
        em formatos corretos (Decimal, dates, etc.).
        
        Args:
            extracted_data: Dados brutos retornados pela IA
            original_text: Texto original da mensagem (para contexto em erros)
            
        Returns:
            Dict normalizado e validado
            
        Raises:
            ValueError: Se dados obrigatórios estiverem faltando ou inválidos
        """
        # Valida campos obrigatórios
        required_fields = ['valor', 'descricao', 'data_caixa', 'data_competencia']
        missing_fields = [field for field in required_fields if field not in extracted_data]
        
        if missing_fields:
            raise ValueError(
                f'A IA não conseguiu extrair os seguintes campos obrigatórios: {", ".join(missing_fields)}. '
                f'Mensagem original: "{original_text[:100]}"'
            )
        
        # Normaliza valor para Decimal
        try:
            valor = Decimal(str(extracted_data['valor']))
            if valor <= 0:
                raise ValueError('Valor deve ser maior que zero')
        except (InvalidOperation, ValueError, TypeError) as e:
            raise ValueError(f'Valor inválido extraído: {extracted_data.get("valor")}. Erro: {str(e)}')
        
        # Normaliza datas
        try:
            data_caixa = self._parse_date(extracted_data['data_caixa'])
            data_competencia = self._parse_date(extracted_data['data_competencia'])
        except ValueError as e:
            raise ValueError(f'Data inválida extraída: {str(e)}')
        
        # Valida que data_competencia não seja futura
        today = date.today()
        if data_competencia > today:
            logger.warning(
                f'Data de competência futura detectada: {data_competencia}. '
                f'Ajustando para hoje: {today}'
            )
            data_competencia = today
        
        # Normaliza descrição
        descricao = str(extracted_data.get('descricao', '')).strip()
        if not descricao:
            descricao = original_text[:100]  # Fallback para texto original
        
        # Normaliza categoria e subcategoria (usa valores padrão se não encontrados)
        categoria_sugerida = str(extracted_data.get('categoria_sugerida', 'Despesa Variável')).strip()
        subcategoria_sugerida = str(extracted_data.get('subcategoria_sugerida', 'Material geral')).strip()
        
        # Normaliza fornecedor (opcional)
        fornecedor = str(extracted_data.get('fornecedor', '')).strip() or None
        
        # Normaliza confiança (0.0 a 1.0)
        try:
            confianca = float(extracted_data.get('confianca', 0.8))
            confianca = max(0.0, min(1.0, confianca))  # Clamp entre 0 e 1
        except (ValueError, TypeError):
            confianca = 0.5  # Valor padrão se inválido
        
        # Normaliza pagamento realizado
        pagamento_realizado = extracted_data.get('pagamento_realizado', False)
        if isinstance(pagamento_realizado, str):
            pagamento_realizado = pagamento_realizado.lower() in ('true', '1', 'yes', 'sim', 'já', 'paguei')
        
        # Normaliza valor pago (se fornecido)
        valor_pago = None
        if pagamento_realizado:
            valor_pago_str = extracted_data.get('valor_pago')
            if valor_pago_str:
                try:
                    valor_pago = Decimal(str(valor_pago_str))
                    if valor_pago <= 0:
                        valor_pago = None  # Ignora se inválido
                except (InvalidOperation, ValueError, TypeError):
                    valor_pago = None
        
        # Normaliza aviso de categoria (se confiança baixa)
        aviso_categoria = extracted_data.get('aviso_categoria', '').strip() if confianca < 0.8 else None
        
        return {
            'valor': valor,
            'descricao': descricao,
            'data_caixa': data_caixa.isoformat(),
            'data_competencia': data_competencia.isoformat(),
            'categoria_sugerida': categoria_sugerida,
            'subcategoria_sugerida': subcategoria_sugerida,
            'fornecedor': fornecedor,
            'confianca': confianca,
            'pagamento_realizado': pagamento_realizado,
            'valor_pago': float(valor_pago) if valor_pago else None,
            'aviso_categoria': aviso_categoria
        }
    
    def _parse_date(self, date_str: str) -> date:
        """
        Parse de string de data para objeto date.
        
        Aceita formatos: YYYY-MM-DD, DD/MM/YYYY, DD-MM-YYYY
        
        Args:
            date_str: String com a data
            
        Returns:
            Objeto date
            
        Raises:
            ValueError: Se a data for inválida ou não puder ser parseada
        """
        date_str = str(date_str).strip()
        
        # Tenta formato ISO (YYYY-MM-DD)
        try:
            return datetime.strptime(date_str, '%Y-%m-%d').date()
        except ValueError:
            pass
        
        # Tenta formato brasileiro (DD/MM/YYYY)
        try:
            return datetime.strptime(date_str, '%d/%m/%Y').date()
        except ValueError:
            pass
        
        # Tenta formato com hífen (DD-MM-YYYY)
        try:
            return datetime.strptime(date_str, '%d-%m-%Y').date()
        except ValueError:
            pass
        
        raise ValueError(f'Formato de data inválido: {date_str}')

