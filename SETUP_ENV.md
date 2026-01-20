# Configuração do Arquivo .env

O arquivo `.env` não é versionado por questões de segurança. Você precisa criá-lo manualmente antes de executar as migrações.

## Passos para Criar o Arquivo .env

1. Copie o arquivo `ENV_EXAMPLE.txt` para `.env`:

```bash
# Windows (PowerShell):
Copy-Item ENV_EXAMPLE.txt .env

# Linux/Mac:
cp ENV_EXAMPLE.txt .env
```

2. Edite o arquivo `.env` criado e configure as seguintes variáveis:

```env
# Configurações do Django
SECRET_KEY=sua-chave-secreta-gerada
DEBUG=True
ALLOWED_HOSTS=localhost,127.0.0.1

# Banco de Dados PostgreSQL (valores padrão para desenvolvimento)
DATABASE_URL=postgresql://postgres:postgres@localhost:5432/caixo_db
DB_NAME=caixo_db
DB_USER=postgres
DB_PASSWORD=postgres
DB_HOST=localhost
DB_PORT=5432
```

## Gerar SECRET_KEY

Execute o comando abaixo para gerar uma SECRET_KEY segura:

```bash
python -c "import secrets; print(secrets.token_urlsafe(50))"
```

Copie a chave gerada e cole no arquivo `.env` na variável `SECRET_KEY`.

## Verificar Configuração

Após criar o arquivo `.env`, verifique se o Django consegue ler as variáveis:

```bash
python manage.py check
```

Se tudo estiver correto, você verá: "System check identified no issues (0 silenced)."

## Próximos Passos

Após criar o `.env`:

1. Execute as migrações:
```bash
python manage.py makemigrations core
python manage.py migrate
```

2. Crie o Admin Master:
```bash
python manage.py init_admin
```


