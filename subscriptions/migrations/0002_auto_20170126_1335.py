# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('subscriptions', '0001_initial'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='subscription',
            name='charitable',
        ),
        migrations.RemoveField(
            model_name='subscription',
            name='charity_number',
        ),
        migrations.RemoveField(
            model_name='subscription',
            name='description',
        ),
    ]
