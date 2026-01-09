📑 CAIXÔ — MANIFESTO TÉCNICO E ARQUITETURAL (V2.0)

## 1. VISÃO DO PRODUTO

O Caixô é um ecossistema SaaS de inteligência financeira gerencial focado em empresas que buscam rigor contábil com esforço operacional zero. O sistema utiliza Inteligência Artificial para processar entradas multimodais (WhatsApp) e transformá-las em relatórios de DRE (Competência) e Fluxo de Caixa (Caixa) em tempo real.

## 2. PILARES DE ENGENHARIA E "REGRAS DE OURO"

**Isolamento de Dados (Multi-Tenancy):** Todo e qualquer dado deve ser filtrado por tenant_id. Vazamento de dados entre lojas é um erro crítico nível 0.

**Dualidade Contábil Rigorosa:** Todo lançamento financeiro possui duas datas: a de Competência (fato gerador) e a de Caixa (movimentação bancária).

**Segurança por Ofuscação:** Nenhuma chave primária deve ser sequencial (Integer). Uso obrigatório de UUID para todas as tabelas.

**Código Limpo e Documentado:** Todo código deve seguir o padrão PEP 8, ser enxuto, eficiente e possuir comentários em Português-BR detalhando a lógica.

**Interface Mobile-First:** O dashboard React deve ser otimizado para o navegador do celular, priorizando velocidade e legibilidade.

## 3. ARQUITETURA TECNOLÓGICA (STACK)

**Backend:** Python 3.12+ / Django 5.0+ (Framework Robusto).

**Frontend:** React 18+ / Vite / Tailwind CSS / Shadcn/UI (Modernidade e Performance).

**Banco de Dados:** PostgreSQL (Relacional e ACID).

**Mensageria/Assincronismo:** Celery + Redis (Processamento de IA e Webhooks).

**Gateway WhatsApp:** Evolution API (Comunicação estável via WebSocket/Rest).

**Inteligência Artificial:** OpenAI GPT-4o-mini (Extração de dados) + Whisper (Voz).

## 4. MODELAGEM DE DADOS (DATABASE SCHEMA)

### 4.1. Núcleo de Tenant e Usuário

**Tenant (Empresa):** UUID, Razão Social, CNPJ (validado), Plano (Basic/Pro), Status, Configurações de Faturamento (Dia Semanal, Dia Mensal).

**User:** Email, Role (SuperAdmin/Gestor/Operador), WhatsApp JID, vínculo com Tenant.

### 4.2. Estrutura Financeira (Base da Planilha)

**Category & Subcategory:** Sistema hierárquico. Categorias Globais (Seed) + Categorias Customizadas por Loja.

**Transaction (Competência/DRE):** O fato econômico. Valor bruto, Fornecedor, Descrição, Categoria, Subcategoria, Mês/Ano de competência.

**Installment (Caixa/Fluxo):** A parcela financeira. Vínculo com Transaction, Data de Vencimento, Data de Pagamento, Valor Líquido, Multas/Juros, Status (ABERTO/PAGO).

### 4.3. Camada de Inteligência

**ParsingSession:** Tabela temporária para armazenar o JSON extraído pela IA antes da confirmação do usuário.

**LearnedRule:** Mapeamento inteligente que associa Palavra-Chave ou Fornecedor a uma Subcategoria específica da loja.

## 5. FLUXO DE INTELIGÊNCIA ARTIFICIAL (PARSING PIPELINE)

**Ingestão:** Recebe texto, áudio ou imagem via Evolution API.

**Normalização:** O sistema extrai o texto bruto (OCR para imagagens, ASR para áudios).

**Extração Semântica (LLM):** A IA identifica:

- Valor: Moeda corrente.
- Data de Caixa: Quando o dinheiro moveu.
- Data de Competência: Se for conta de consumo (Luz/Água/Aluguel), retroage 1 mês automaticamente.
- Categoria: Baseado no Glossário de Despesas.

**Sessão Temporária:** Grava os dados em ParsingSession e gera o Card de Confirmação no WhatsApp.

**Confirmação:** Ao clicar em [Confirmar], os registros são criados em Transaction e Installment.

## 6. LÓGICA DE COBRANÇA ATIVA (BOT PROATIVO)

**Faturamento Semanal:** No dia configurado, o bot dispara: "Qual foi o faturamento bruto da última semana (Segunda a Domingo)?".

**Faturamento Mensal:** Todo dia 'X', solicita o faturamento total do mês anterior para cálculo de indicadores.

**Lembrete de Vencimento:** Disparo diário às 08h com as contas que vencem no dia e botão de baixa rápida.

## 7. DASHBOARD E INDICADORES (KPIs)

A plataforma Web deve calcular e exibir:

**DRE Vertical:** Receita - Variáveis = Margem de Contribuição - Fixos = Lucro Líquido.

**Markup Médio:** Relação entre o custo de insumos (Estoque) e o faturamento.

**Ponto de Equilíbrio (Break-Even):** Valor mínimo de faturamento para não ter prejuízo.

**Eficiência de Caixa:** Total gasto em Juros e Multas no mês (exposto como alerta de erro operacional).

**Percentual por Categoria:** Gráfico de impacto de cada grupo de despesa no faturamento.

## 8. REQUISITOS DE IMPLEMENTAÇÃO (PARA O CURSOR)

**Django Base:** Use models.Model customizado com tenant_id obrigatório.

**DRF:** Endpoints devem ser limpos e usar Serializers rigorosos.

**Frontend:** Use Recharts para gráficos e TanStack Table para listas financeiras.

**Segurança:** Implemente validação de JID para garantir que apenas números autorizados lancem dados.

**Performance:** Queries de DRE devem ser otimizadas (use select_related e prefetch_related).

## 9. GLOSSÁRIO DE REFERÊNCIA (CATEGORIAS)

**Despesa Fixa:** Aluguel, Luz, Água, Salários, Pro Labore, Sistemas.

**Despesa Variável:** Impostos, Taxas de Cartão, Insumos (Estoque), Comissões.

**Investimentos:** Reformas, Máquinas novas, Marketing de expansão.

---

## MODO DE USO DO CURSOR:

**"Sempre que houver dúvida sobre uma regra de negócio ou campo de banco de dados, consulte este README. Priorize a consistência contábil sobre a facilidade de implementação."**

