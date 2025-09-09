# file: carton_pricing/management/commands/seed_carton.py
from django.core.management.base import BaseCommand
from carton_pricing.models import BaseSettings, FluteStep

class Command(BaseCommand):
    help = 'Seed default base settings and flute steps'
    def handle(self, *args, **opts):
        bs, _ = BaseSettings.objects.get_or_create(singleton_key='ONLY', defaults={
            'overhead_per_meter': 0,
            'sheet_price_cash': 0,
            'sheet_price_credit': 0,
            'profit_rate_percent': 10,
            'shipping_cost': 0,
            'pallet_cost': 0,
            'interface_cost': 0,
            'fixed_widths': [80,90,100,110,120,125,140],
        })
        for k in ['C','E','B','CB','CE','EB']:
            FluteStep.objects.get_or_create(key=k)
        self.stdout.write(self.style.SUCCESS('Seeded base settings and flute steps.'))