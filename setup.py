"""
Script de Setup Automatizado para o Caixô.

Este script automatiza a instalação das dependências e configuração inicial
do projeto. Execute antes de rodar as migrações.

Uso:
    python setup.py

Ou execute manualmente os comandos:
    pip install -r requirements.txt
    python manage.py makemigrations core
    python manage.py migrate
    python manage.py init_admin
"""

import subprocess
import sys
import os
from pathlib import Path


def run_command(command, description):
    """
    Executa um comando do sistema e trata erros.
    
    Args:
        command: Comando a ser executado
        description: Descrição do comando para logs
    """
    print(f"\n{'='*60}")
    print(f"Executando: {description}")
    print(f"Comando: {command}")
    print(f"{'='*60}\n")
    
    try:
        result = subprocess.run(
            command,
            shell=True,
            check=True,
            capture_output=True,
            text=True
        )
        print(result.stdout)
        if result.stderr:
            print(result.stderr)
        return True
    except subprocess.CalledProcessError as e:
        print(f"✗ Erro ao executar: {description}")
        print(f"  Detalhes: {e.stderr}")
        return False


def check_env_file():
    """
    Verifica se o arquivo .env existe e está configurado.
    
    Returns:
        True se o arquivo existe, False caso contrário
    """
    env_path = Path('.env')
    if not env_path.exists():
        print("\n⚠ ATENÇÃO: Arquivo .env não encontrado!")
        print("\nPor favor, crie o arquivo .env baseado no ENV_EXAMPLE.txt:")
        print("  Copy-Item ENV_EXAMPLE.txt .env")
        print("\nOu siga as instruções no arquivo SETUP_ENV.md")
        return False
    
    # Verifica se a SECRET_KEY foi configurada
    with open(env_path, 'r') as f:
        content = f.read()
        if 'sua-chave-secreta-aqui' in content:
            print("\n⚠ ATENÇÃO: SECRET_KEY não foi configurada no arquivo .env!")
            print("Gere uma SECRET_KEY com:")
            print("  python -c \"import secrets; print(secrets.token_urlsafe(50))\"")
            print("\nE atualize o arquivo .env")
            return False
    
    return True


def main():
    """
    Função principal que executa o setup completo.
    """
    print("\n" + "="*60)
    print("CAIXÔ - Setup Automatizado")
    print("="*60)
    
    # Passo 1: Verifica arquivo .env
    print("\n[1/4] Verificando arquivo .env...")
    if not check_env_file():
        print("\n✗ Setup interrompido. Configure o arquivo .env e tente novamente.")
        sys.exit(1)
    print("✓ Arquivo .env encontrado e configurado.")
    
    # Passo 2: Instala dependências
    print("\n[2/4] Instalando dependências...")
    if not run_command(
        "pip install -r requirements.txt",
        "Instalação de dependências"
    ):
        print("\n✗ Falha na instalação de dependências.")
        sys.exit(1)
    print("✓ Dependências instaladas com sucesso.")
    
    # Passo 3: Executa migrações
    print("\n[3/4] Criando e aplicando migrações...")
    if not run_command(
        "python manage.py makemigrations core",
        "Criação de migrações"
    ):
        print("\n✗ Falha ao criar migrações.")
        sys.exit(1)
    
    if not run_command(
        "python manage.py migrate",
        "Aplicação de migrações"
    ):
        print("\n✗ Falha ao aplicar migrações.")
        sys.exit(1)
    print("✓ Migrações aplicadas com sucesso.")
    
    # Passo 4: Cria Admin Master
    print("\n[4/4] Criando SuperUser Master...")
    if not run_command(
        "python manage.py init_admin",
        "Criação do Admin Master"
    ):
        print("\n✗ Falha ao criar Admin Master.")
        sys.exit(1)
    print("✓ Admin Master criado com sucesso.")
    
    print("\n" + "="*60)
    print("✓ SETUP COMPLETO COM SUCESSO!")
    print("="*60)
    print("\nPróximos passos:")
    print("  1. Execute o servidor: python manage.py runserver")
    print("  2. Acesse o admin: http://localhost:8000/admin/")
    print("  3. Login: admin@caixo.com")
    print("  4. Senha: Mindhub1417!")
    print("\n⚠ IMPORTANTE: Altere a senha padrão em produção!")
    print("="*60 + "\n")


if __name__ == '__main__':
    main()


