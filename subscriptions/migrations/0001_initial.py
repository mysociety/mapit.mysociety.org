# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models
from django.conf import settings


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='Subscription',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('charitable', models.CharField(max_length=1, choices=[(b'c', b'Registered charity'), (b'i', b'Individual pursuing a non-profit project on an unpaid basis'), (b'o', b'Other')])),
                ('charity_number', models.TextField(blank=True)),
                ('description', models.TextField(blank=True)),
                ('stripe_id', models.CharField(max_length=100)),
                ('user', models.OneToOneField(to=settings.AUTH_USER_MODEL, on_delete=models.CASCADE)),
            ],
        ),
    ]
