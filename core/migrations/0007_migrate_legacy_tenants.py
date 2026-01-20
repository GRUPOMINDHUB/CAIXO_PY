# Generated migration para migrar tenants legados para ManyToMany

from django.db import migrations


def migrate_legacy_tenants(apps, schema_editor):
    """
    Migra tenants do campo legado (tenant) para ManyToMany (tenants).
    
    Para cada usuário que tem tenant legado, adiciona o tenant
    ao ManyToMany e mantém o campo legado temporariamente.
    """
    User = apps.get_model('core', 'User')
    
    # Para cada usuário com tenant legado
    for user in User.objects.filter(tenant__isnull=False):
        # Adiciona o tenant legado ao ManyToMany
        if user.tenant:
            user.tenants.add(user.tenant)
            print(f'Migrado: {user.email} -> {user.tenant.name}')


def reverse_migrate(apps, schema_editor):
    """
    Reversão: move tenants do ManyToMany para o campo legado.
    
    Usa o primeiro tenant do ManyToMany como tenant legado.
    """
    User = apps.get_model('core', 'User')
    
    for user in User.objects.all():
        first_tenant = user.tenants.first()
        if first_tenant:
            user.tenant = first_tenant
            user.save(update_fields=['tenant'])
            print(f'Revertido: {user.email} -> {first_tenant.name}')


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0006_add_manytomany_tenants'),
    ]

    operations = [
        migrations.RunPython(migrate_legacy_tenants, reverse_migrate),
    ]
