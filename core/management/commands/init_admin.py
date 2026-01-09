"""
Custom Management Command para criar o SuperUser Master (ADMIN_MASTER).

Este comando cria automaticamente o SuperUser Master do sistema Caixô,
garantindo que o usuário administrativo principal esteja sempre disponível.

Uso:
    python manage.py init_admin

Características:
    - Criação não-interativa (automática)
    - Verifica se o usuário já existe antes de criar
    - Tratamento de erros robusto com logs claros
    - Valida integridade das migrações antes de criar o usuário
"""

import sys
from django.core.management.base import BaseCommand, CommandError
from django.db import connection, OperationalError, transaction
from django.core.management import call_command
from django.core.exceptions import ValidationError

from core.models import User
from core.models.user import UserRole


class Command(BaseCommand):
    """
    Comando Django para criar o SuperUser Master automaticamente.
    
    Este comando verifica se o banco de dados está acessível, valida
    se as migrações foram aplicadas e cria o usuário ADMIN_MASTER
    se ele não existir.
    """
    
    help = 'Cria o SuperUser Master (ADMIN_MASTER) do sistema Caixô automaticamente.'
    
    # Dados padrão do SuperUser Master
    ADMIN_EMAIL = 'admin@caixo.com'
    ADMIN_PASSWORD = 'Mindhub1417!'
    ADMIN_ROLE = UserRole.ADMIN_MASTER
    
    def add_arguments(self, parser):
        """
        Adiciona argumentos opcionais ao comando.
        
        Permite sobrescrever email e senha via linha de comando se necessário.
        """
        parser.add_argument(
            '--email',
            type=str,
            default=self.ADMIN_EMAIL,
            help='Email do SuperUser Master (padrão: admin@caixo.com)'
        )
        parser.add_argument(
            '--password',
            type=str,
            default=self.ADMIN_PASSWORD,
            help='Senha do SuperUser Master'
        )
    
    def handle(self, *args, **options):
        """
        Método principal que executa o comando.
        
        Ordem de execução:
        1. Verifica conexão com o banco de dados
        2. Valida se as migrações foram aplicadas
        3. Verifica se o usuário já existe
        4. Cria o usuário se não existir
        5. Exibe mensagens de sucesso/erro apropriadas
        """
        email = options.get('email', self.ADMIN_EMAIL)
        password = options.get('password', self.ADMIN_PASSWORD)
        
        try:
            # Passo 1: Verifica conexão com o banco de dados
            self.stdout.write('Verificando conexão com o banco de dados...')
            self._check_database_connection()
            self.stdout.write(self.style.SUCCESS('[OK] Conexao com banco de dados estabelecida.'))
            
            # Passo 2: Valida se as migrações foram aplicadas
            self.stdout.write('Verificando se as migrações foram aplicadas...')
            self._check_migrations()
            self.stdout.write(self.style.SUCCESS('[OK] Migracoes validadas.'))
            
            # Passo 3: Verifica se o usuário já existe
            self.stdout.write(f'Verificando se o Admin Master ({email}) já existe...')
            
            if User.objects.filter(email=email).exists():
                user = User.objects.get(email=email)
                self.stdout.write(self.style.WARNING(
                    f'[AVISO] Admin Master ja existe com email: {email}'
                ))
                self.stdout.write(f'   - ID: {user.id}')
                self.stdout.write(f'   - Role: {user.get_role_display()}')
                self.stdout.write(f'   - Is Staff: {user.is_staff}')
                self.stdout.write(f'   - Is Superuser: {user.is_superuser}')
                self.stdout.write(self.style.SUCCESS('[OK] Nenhuma acao necessaria.'))
                return
            
            # Passo 4: Cria o usuário ADMIN_MASTER
            self.stdout.write(self.style.WARNING('Criando Admin Master...'))
            
            with transaction.atomic():
                user = User.objects.create_superuser(
                    email=email,
                    password=password,
                    role=self.ADMIN_ROLE,
                    tenant=None  # Admin Master não possui tenant
                )
                
                # Garante que os campos de permissão estão corretos
                user.is_staff = True
                user.is_superuser = True
                user.save()
            
            self.stdout.write(self.style.SUCCESS(
                f'[OK] Admin Master criado com sucesso!'
            ))
            self.stdout.write(f'   - Email: {user.email}')
            self.stdout.write(f'   - ID: {user.id}')
            self.stdout.write(f'   - Role: {user.get_role_display()}')
            self.stdout.write(self.style.WARNING(
                f'\n[AVISO] IMPORTANTE: Altere a senha padrao em producao!'
            ))
            
        except OperationalError as e:
            self.stdout.write(self.style.ERROR(
                '[ERRO] Erro ao conectar com o banco de dados!'
            ))
            self.stdout.write(self.style.ERROR(
                f'   Detalhes: {str(e)}'
            ))
            self.stdout.write(self.style.WARNING(
                '\nVerifique se:'
                '\n  1. O PostgreSQL está rodando'
                '\n  2. As credenciais no arquivo .env estão corretas'
                '\n  3. O banco de dados "caixo_db" foi criado'
            ))
            raise CommandError('Falha na conexão com o banco de dados.')
        
        except ValidationError as e:
            self.stdout.write(self.style.ERROR(
                '[ERRO] Erro de validacao ao criar Admin Master!'
            ))
            self.stdout.write(self.style.ERROR(f'   Detalhes: {str(e)}'))
            raise CommandError('Falha na validação do usuário.')
        
        except Exception as e:
            self.stdout.write(self.style.ERROR(
                '[ERRO] Erro inesperado ao criar Admin Master!'
            ))
            self.stdout.write(self.style.ERROR(f'   Detalhes: {str(e)}'))
            raise CommandError(f'Erro inesperado: {str(e)}')
    
    def _check_database_connection(self):
        """
        Verifica se a conexão com o banco de dados está funcionando.
        
        Raises:
            OperationalError: Se não conseguir conectar ao banco
        """
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1")
                cursor.fetchone()
        except OperationalError as e:
            raise OperationalError(
                f'Não foi possível conectar ao banco de dados. '
                f'Verifique as configurações no arquivo .env. Erro: {str(e)}'
            )
    
    def _check_migrations(self):
        """
        Verifica se as migrações foram aplicadas corretamente.
        
        Valida se a tabela do modelo User existe no banco de dados,
        garantindo que as migrações foram executadas antes de criar
        o SuperUser Master.
        
        Raises:
            CommandError: Se as migrações não foram aplicadas
        """
        try:
            # Verifica se a tabela do modelo User existe
            with connection.cursor() as cursor:
                # Verifica o tipo de banco de dados
                db_backend = connection.vendor
                
                if db_backend == 'sqlite':
                    # Para SQLite, usa sqlite_master
                    cursor.execute("""
                        SELECT name 
                        FROM sqlite_master 
                        WHERE type='table' AND name='core_user'
                    """)
                    result = cursor.fetchone()
                    if not result:
                        raise CommandError(
                            'Tabela core_user nao encontrada. '
                            'Execute "python manage.py migrate" antes de criar o Admin Master.'
                        )
                else:
                    # Para PostgreSQL/MySQL, usa information_schema
                    cursor.execute("""
                        SELECT table_name 
                        FROM information_schema.tables 
                        WHERE table_schema = 'public' AND table_name = 'core_user'
                    """)
                    result = cursor.fetchone()
                    if not result:
                        raise CommandError(
                            'Tabela core_user nao encontrada. '
                            'Execute "python manage.py migrate" antes de criar o Admin Master.'
                        )
                
        except OperationalError as e:
            raise CommandError(
                f'Erro ao verificar migracoes: {str(e)}. '
                'Certifique-se de que as migracoes foram aplicadas.'
            )

