# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models
import bulk_lookup.models


class Migration(migrations.Migration):

    dependencies = [
    ]

    operations = [
        migrations.CreateModel(
            name='BulkLookup',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('original_file', models.FileField(upload_to=bulk_lookup.models.original_file_upload_to)),
                ('output_file', models.FileField(upload_to=bulk_lookup.models.output_file_upload_to, blank=True)),
                ('postcode_field', models.CharField(max_length=256)),
                ('email', models.EmailField(max_length=254)),
                ('description', models.TextField(blank=True)),
                ('bad_rows', models.IntegerField(null=True, blank=True)),
                ('created', models.DateTimeField(auto_now_add=True)),
                ('updated', models.DateTimeField(auto_now=True)),
                ('started', models.DateTimeField(null=True, blank=True)),
                ('finished', models.DateTimeField(null=True, blank=True)),
                ('last_error', models.DateTimeField(null=True, blank=True)),
                ('error_count', models.IntegerField(default=0)),
                ('charge_id', models.CharField(max_length=255, blank=True)),
            ],
        ),
        migrations.CreateModel(
            name='OutputOption',
            fields=[
                ('id', models.AutoField(verbose_name='ID', serialize=False, auto_created=True, primary_key=True)),
                ('name', models.CharField(max_length=500)),
                ('mapit_area_type', models.CharField(max_length=500)),
            ],
        ),
        migrations.AddField(
            model_name='bulklookup',
            name='output_options',
            field=models.ManyToManyField(related_query_name=b'bulk_lookup', related_name='bulk_lookups', to='bulk_lookup.OutputOption'),
        ),
    ]
