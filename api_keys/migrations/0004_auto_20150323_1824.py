# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import models, migrations
from django.conf import settings


class Migration(migrations.Migration):

    dependencies = [
        ('api_keys', '0003_auto_20150323_1802'),
    ]

    operations = [
        migrations.AlterField(
            model_name='apikey',
            name='user',
            field=models.OneToOneField(related_name='api_key', to=settings.AUTH_USER_MODEL),
            preserve_default=True,
        ),
    ]
