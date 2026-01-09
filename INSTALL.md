# Instruções de Instalação - Caixô

## Pré-requisitos

- Python 3.12 ou superior
- PostgreSQL 12 ou superior
- pip (gerenciador de pacotes Python)

## Passo 1: Configurar Ambiente Virtual

```bash
# Criar ambiente virtual
python -m venv venv

# Ativar ambiente virtual
# Windows:
venv\Scripts\activate
# Linux/Mac:
source venv/bin/activate
```

## Passo 2: Instalar Dependências

```bash
pip install -r requirements.txt
```

## Passo 3: Configurar Banco de Dados PostgreSQL

1. Crie um banco de dados PostgreSQL:
```sql
CREATE DATABASE caixo_db;
CREATE USER caixo_user WITH PASSWORD 'sua_senha_aqui';
GRANT ALL PRIVILEGES ON DATABASE caixo_db TO caixo_user;
```

2. Copie o arquivo `ENV_EXAMPLE.txt` para `.env`:
```bash
# Windows:
copy ENV_EXAMPLE.txt .env
# Linux/Mac:
cp ENV_EXAMPLE.txt .env
```

3. Edite o arquivo `.env` com suas configurações:
```env
SECRET_KEY=sua-chave-secreta-aqui
DEBUG=True
ALLOWED_HOSTS=localhost,127.0.0.1

DB_NAME=caixo_db
DB_USER=caixo_user
DB_PASSWORD=sua_senha_aqui
DB_HOST=localhost
DB_PORT=5432
```

## Passo 4: Gerar Chave Secreta do Django

```bash
python manage.py shell -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"
```

Copie a chave gerada e cole no arquivo `.env` na variável `SECRET_KEY`.

## Passo 5: Criar Migrações e Aplicar

```bash
# Criar migrações
python manage.py makemigrations

# Aplicar migrações
python manage.py migrate
```

## Passo 6: Criar Superusuário (ADMIN_MASTER)

```bash
python manage.py createsuperuser
```

**Importante:** O primeiro usuário criado será automaticamente ADMIN_MASTER e não terá tenant associado.

## Passo 7: Executar Servidor de Desenvolvimento

```bash
python manage.py runserver
```

Acesse: http://localhost:8000/admin/

## Estrutura Criada

### Modelos Implementados

- **Tenant**: Representa uma loja/empresa no sistema
- **User**: Usuário customizado com tenant, role e whatsapp_number
- **TenantModel**: Classe base abstrata para modelos multi-tenant

### Recursos de Segurança

- ✅ Isolamento automático de dados por tenant
- ✅ UUID como chave primária (não sequencial)
- ✅ Validação de CNPJ
- ✅ Filtragem automática no Admin baseada em role

### Próximos Passos

1. Implementar middleware para definir tenant automaticamente no contexto
2. Criar modelos financeiros (Transaction, Installment, Category, etc.)
3. Implementar API REST com Django REST Framework
4. Integrar com Evolution API para WhatsApp
5. Implementar pipeline de IA para parsing de mensagens

## Notas Importantes

- **NUNCA** remova o filtro de tenant sem necessidade absoluta
- **SEMPRE** use `TenantModel` como base para modelos financeiros
- **SEMPRE** use UUID para chaves primárias
- **NUNCA** use IDs sequenciais (integers) para segurança

