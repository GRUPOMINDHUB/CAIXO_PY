"""
Custom Management Command para popular o Glossário de Despesas MINDHUB.

Este comando popula as tabelas Category e Subcategory com os dados globais
do Glossário de Despesas fornecido, permitindo que todas as lojas utilizem
as mesmas categorias base.

Uso:
    python manage.py seed_glossary

Características:
    - Criação não-interativa (automática)
    - Verifica se as categorias já existem antes de criar
    - Popula com tenant=None (categorias globais)
    - Baseado no Glossário de Despesas.pdf fornecido
"""

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from core.models.finance import Category, Subcategory, CategoryType


class Command(BaseCommand):
    """
    Comando Django para popular o Glossário de Despesas.
    
    Popula as categorias e subcategorias globais baseadas no
    Glossário de Despesas MINDHUB fornecido.
    """
    
    help = 'Popula o Glossário de Despesas MINDHUB (categorias e subcategorias globais).'
    
    # Dados do Glossário de Despesas MINDHUB
    GLOSSARY_DATA = [
        # Despesa Fixa
        {
            'category': {'name': 'Despesa Fixa', 'type': CategoryType.FIXA},
            'subcategories': [
                'Sindicatos',
                'Jurídico',
                'Contas de consumo',
                'Custo com Mão de Obra',
                'Ocupação',
                'Sistemas',
                'Marketing',
                'Contabilidade',
                'Dedetização',
                'Pro Labore',
                'Taxas e Licenças',
                'Testes cozinha',
            ]
        },
        # Despesa Variável
        {
            'category': {'name': 'Despesa Variável', 'type': CategoryType.VARIAVEL},
            'subcategories': [
                'Gastos com iFood',
                'Comissão',
                'Material descartável',
                'Devolução e cancelamentos',
                'Impostos',
                'Despesas Bancárias',
                'Taxas de máquinas de cartão',
                'Deslocamentos',
                'Logística',
                'Material de escritório',
                'Material de limpeza',
                'Embalagens',
            ]
        },
        # Investimentos
        {
            'category': {'name': 'Investimentos', 'type': CategoryType.INVESTIMENTO},
            'subcategories': [
                'Equipamentos',
                'Materiais gerais',
                'Manutenção',
                'Reformas',
            ]
        },
        # Estoque
        {
            'category': {'name': 'Estoque', 'type': CategoryType.ESTOQUE},
            'subcategories': [
                'Gelo',
            ]
        },
    ]
    
    def add_arguments(self, parser):
        """
        Adiciona argumentos opcionais ao comando.
        
        Permite forçar recriação de todas as categorias.
        """
        parser.add_argument(
            '--force',
            action='store_true',
            help='Força recriação de todas as categorias (apaga e recria)'
        )
    
    def handle(self, *args, **options):
        """
        Método principal que executa o comando.
        
        Ordem de execução:
        1. Verifica se as categorias já existem
        2. Cria categorias globais (tenant=None)
        3. Cria subcategorias globais vinculadas às categorias
        4. Exibe mensagens de sucesso/erro apropriadas
        """
        force = options.get('force', False)
        
        try:
            self.stdout.write('=' * 60)
            self.stdout.write('Popular Glossario de Despesas MINDHUB')
            self.stdout.write('=' * 60)
            
            # Verifica se já existem categorias globais
            if not force and Category.objects.filter(tenant__isnull=True).exists():
                self.stdout.write(self.style.WARNING(
                    '[AVISO] Categorias globais ja existem no banco de dados.'
                ))
                self.stdout.write('Use --force para recriar todas as categorias.')
                
                # Mostra estatísticas
                category_count = Category.objects.filter(tenant__isnull=True).count()
                subcategory_count = Subcategory.objects.filter(tenant__isnull=True).count()
                self.stdout.write(f'  - Categorias globais: {category_count}')
                self.stdout.write(f'  - Subcategorias globais: {subcategory_count}')
                return
            
            # Se force=True, apaga categorias globais existentes
            if force:
                self.stdout.write(self.style.WARNING(
                    '[AVISO] Forcando recriacao de todas as categorias globais...'
                ))
                deleted_cats = Category.objects.filter(tenant__isnull=True).delete()
                deleted_subs = Subcategory.objects.filter(tenant__isnull=True).delete()
                self.stdout.write(f'  - Categorias removidas: {deleted_cats[0]}')
                self.stdout.write(f'  - Subcategorias removidas: {deleted_subs[0]}')
            
            # Cria categorias e subcategorias globais
            self.stdout.write('\nCriando categorias e subcategorias globais...')
            
            created_categories = 0
            created_subcategories = 0
            
            with transaction.atomic():
                for item in self.GLOSSARY_DATA:
                    # Cria categoria global (tenant=None)
                    category_data = item['category']
                    category, created = Category.objects.get_or_create(
                        name=category_data['name'],
                        type=category_data['type'],
                        tenant=None,  # Categoria global
                        defaults={
                            'name': category_data['name'],
                            'type': category_data['type'],
                            'tenant': None
                        }
                    )
                    
                    if created:
                        created_categories += 1
                        self.stdout.write(self.style.SUCCESS(
                            f'  [OK] Categoria criada: {category.name}'
                        ))
                    else:
                        self.stdout.write(self.style.WARNING(
                            f'  [AVISO] Categoria ja existe: {category.name}'
                        ))
                    
                    # Cria subcategorias globais (tenant=None)
                    for subcat_name in item['subcategories']:
                        subcategory, sub_created = Subcategory.objects.get_or_create(
                            name=subcat_name,
                            category=category,
                            tenant=None,  # Subcategoria global
                            defaults={
                                'name': subcat_name,
                                'category': category,
                                'tenant': None
                            }
                        )
                        
                        if sub_created:
                            created_subcategories += 1
                            self.stdout.write(self.style.SUCCESS(
                                f'    [OK] Subcategoria criada: {subcat_name} -> {category.name}'
                            ))
                        else:
                            self.stdout.write(self.style.WARNING(
                                f'    [AVISO] Subcategoria ja existe: {subcat_name}'
                            ))
            
            # Estatísticas finais
            self.stdout.write('\n' + '=' * 60)
            self.stdout.write(self.style.SUCCESS('[OK] Glossario populado com sucesso!'))
            self.stdout.write('=' * 60)
            self.stdout.write(f'  - Categorias criadas: {created_categories}')
            self.stdout.write(f'  - Subcategorias criadas: {created_subcategories}')
            
            # Estatísticas totais
            total_categories = Category.objects.filter(tenant__isnull=True).count()
            total_subcategories = Subcategory.objects.filter(tenant__isnull=True).count()
            self.stdout.write(f'\n  - Total de categorias globais: {total_categories}')
            self.stdout.write(f'  - Total de subcategorias globais: {total_subcategories}')
            
        except Exception as e:
            self.stdout.write(self.style.ERROR(
                '[ERRO] Erro inesperado ao popular Glossario!'
            ))
            self.stdout.write(self.style.ERROR(f'  Detalhes: {str(e)}'))
            raise CommandError(f'Erro ao popular Glossario: {str(e)}')

