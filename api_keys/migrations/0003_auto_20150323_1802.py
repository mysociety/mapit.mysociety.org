# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations
from django.conf import settings


class Migration(migrations.Migration):

    dependencies = [
        ('api_keys', '0002_auto_20150323_1737'),
    ]

    operations = [
        migrations.AlterField(
            model_name='apikey',
            name='user',
            field=models.ForeignKey(related_name='api_key', to=settings.AUTH_USER_MODEL, on_delete=models.CASCADE),
            preserve_default=True,
        ),
    ]
