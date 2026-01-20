# Quick Start - Caixô

## Configuração Rápida do Ambiente

### Pré-requisitos

- Python 3.12 ou superior
- PostgreSQL 12 ou superior
- pip (gerenciador de pacotes Python)

### Passo 1: Criar Arquivo .env

Copie o arquivo de exemplo e configure:

```bash
# Windows (PowerShell):
Copy-Item ENV_EXAMPLE.txt .env

# Linux/Mac:
cp ENV_EXAMPLE.txt .env
```

Edite o arquivo `.env` e configure a SECRET_KEY:

```bash
# Gere uma SECRET_KEY:
python -c "import secrets; print(secrets.token_urlsafe(50))"

# Cole a chave gerada no arquivo .env na variável SECRET_KEY
```

### Passo 2: Instalar Dependências

```bash
pip install -r requirements.txt
```

### Passo 3: Configurar Banco de Dados PostgreSQL

Certifique-se de que o PostgreSQL está rodando e crie o banco:

```sql
CREATE DATABASE caixo_db;
```

Ou ajuste as credenciais no arquivo `.env` se necessário.

### Passo 4: Executar Setup Automatizado

Execute o script de setup:

```bash
python setup.py
```

O script irá:
1. Verificar o arquivo .env
2. Instalar dependências
3. Criar e aplicar migrações
4. Criar o SuperUser Master

### Passo 5: Executar Servidor

```bash
python manage.py runserver
```

Acesse: http://localhost:8000/admin/

**Credenciais padrão:**
- Email: `admin@caixo.com`
- Senha: `Mindhub1417!`

⚠ **IMPORTANTE**: Altere a senha padrão em produção!

## Execução Manual (Alternativa)

Se preferir executar manualmente:

```bash
# 1. Instalar dependências
pip install -r requirements.txt

# 2. Criar migrações
python manage.py makemigrations core

# 3. Aplicar migrações
python manage.py migrate

# 4. Criar Admin Master
python manage.py init_admin

# 5. Executar servidor
python manage.py runserver
```

## Estrutura Criada

Após o setup, você terá:

- ✅ Banco de dados configurado com tabelas criadas
- ✅ SuperUser Master criado (admin@caixo.com)
- ✅ Estrutura de pastas de mídia (media/tenants/, media/temp/)
- ✅ Sistema multi-tenant funcional

## Problemas Comuns

### Erro: "ModuleNotFoundError: No module named 'rest_framework'"
**Solução**: Execute `pip install -r requirements.txt`

### Erro: "could not connect to server"
**Solução**: Verifique se o PostgreSQL está rodando e as credenciais no `.env` estão corretas.

### Erro: "relation 'core_user' does not exist"
**Solução**: Execute `python manage.py migrate` para criar as tabelas.

### Erro: "Admin Master já existe"
**Solução**: Isso é normal. O usuário já foi criado anteriormente.


