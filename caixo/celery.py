"""
Configuração do Celery para processamento assíncrono.

Configura o Celery para processar tarefas assíncronas (como parsing de mensagens)
usando Redis como message broker.

Uso:
    celery -A caixo worker --loglevel=info
    celery -A caixo beat --loglevel=info
"""

"""
Configuração do Celery para processamento assíncrono.

Configura o Celery para processar tarefas assíncronas (como parsing de mensagens)
usando Redis como message broker.

Uso:
    celery -A caixo worker --loglevel=info
    celery -A caixo beat --loglevel=info
"""

import os
from celery import Celery

# Define o módulo de settings padrão do Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'caixo.settings')

# Cria instância do Celery
app = Celery('caixo')

# Configuração usando settings do Django
# Namespace 'CELERY' significa que todas as configurações devem começar com CELERY_
app.config_from_object('django.conf:settings', namespace='CELERY')

# Auto-descobre tasks em todos os apps instalados
app.autodiscover_tasks()


@app.task(bind=True, ignore_result=True)
def debug_task(self):
    """
    Task de debug para testar se o Celery está funcionando.
    
    Uso:
        debug_task.delay()
    """
    print(f'Request: {self.request!r}')

