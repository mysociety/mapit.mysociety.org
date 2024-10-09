import os
import itertools
from datetime import timedelta

from django.db import models
from django.utils import timezone
from django.conf import settings
from django.utils.crypto import get_random_string

from .csv import PyExcelReader


class cache(object):
    '''Computes attribute value and caches it in the instance.
    Python Cookbook (Denis Otkidach) http://stackoverflow.com/users/168352/denis-otkidach
    This decorator allows you to create a property which can be computed once and
    accessed many times. Sort of like memoization.

    '''
    def __init__(self, method, name=None):
        # record the unbound-method and the name
        self.method = method
        self.name = name or method.__name__
        self.__doc__ = method.__doc__

    def __get__(self, inst, cls):
        # self: <__main__.cache object at 0xb781340c>
        # inst: <__main__.Foo object at 0xb781348c>
        # cls: <class '__main__.Foo'>
        if inst is None:
            # instance attribute accessed on class, return self
            # You get here if you write `Foo.bar`
            return self
        # compute, cache and return the instance's attribute value
        result = self.method(inst)
        # setattr redefines the instance's attribute so this doesn't get called again
        setattr(inst, self.name, result)
        return result


def original_file_upload_to(instance, filename):
    return random_folder_path('original_files', filename)


def output_file_upload_to(instance, filename):
    return random_folder_path('output_files', filename)


def random_folder_path(base_folder, filename):
    random_folder = get_random_string(12)
    return os.path.join(base_folder, random_folder, filename)


class BulkLookupQuerySet(models.QuerySet):
    def needs_processing(self):
        """
        Bulk lookups that need processing:
        - Haven't already started
        - Have been paid (or got something in charge_id)
        - Have failed less than MAX_RETRIES times already
        - Last failed more than RETRY_INTERVAL minutes ago (if they've ever failed)
        """
        retry_minutes = settings.RETRY_INTERVAL
        retry_time = timezone.now() - timedelta(minutes=retry_minutes)
        retry_count = settings.MAX_RETRIES
        return self.filter(started__isnull=True, error_count__lt=retry_count).exclude(charge_id='').filter(
            models.Q(last_error__lt=retry_time) | models.Q(last_error=None)
        ).distinct()


class BulkLookup(models.Model):
    original_file = models.FileField(upload_to=original_file_upload_to, blank=False)
    output_file = models.FileField(upload_to=output_file_upload_to, blank=True)
    postcode_field = models.CharField(max_length=256)
    output_options = models.ManyToManyField(
        'OutputOption',
        related_name='bulk_lookups',
        related_query_name='bulk_lookup'
    )
    email = models.EmailField()
    description = models.TextField(blank=True)
    bad_rows = models.IntegerField(blank=True, null=True)

    created = models.DateTimeField(auto_now_add=True)
    updated = models.DateTimeField(auto_now=True)
    started = models.DateTimeField(blank=True, null=True)
    finished = models.DateTimeField(blank=True, null=True)
    last_error = models.DateTimeField(blank=True, null=True)
    error_count = models.IntegerField(default=0, blank=False)

    # From Stripe
    charge_id = models.CharField(max_length=255, blank=True)

    objects = BulkLookupQuerySet.as_manager()

    def __str__(self):
        return "{} - {} - {:%d %B %Y, %H:%I}".format(
            self.email,
            os.path.basename(self.original_file.name),
            self.created
        )

    def postcode_field_choices(self):
        return [(f, f) for f in self.field_names]

    @cache
    def field_names(self):
        return self.original_file_reader().fieldnames

    def example_rows(self):
        return itertools.islice(self.original_file_reader(), 5)

    def original_file_reader(self):
        return PyExcelReader(self.original_file)

    def output_file_name(self):
        return os.path.basename(self.output_file.name)

    def output_field_names(self):
        names = self.field_names
        for option in self.output_options.all():
            names += option.output_field_names()
        return names


class OutputOption(models.Model):
    name = models.CharField(max_length=500, blank=False)
    mapit_area_type = models.CharField(max_length=500, blank=False)

    def __str__(self):
        return '%s (%s)' % (self.name, self.mapit_area_type)

    def output_field_names(self):
        return [
            "{0} - Name".format(self.name),
            "{0} - GSS Code".format(self.name),
            "{0} - MapIt ID".format(self.name)
        ]

    def get_from_mapit_response(self, areas):
        """ Extract the right data from mapit's data """
        fields = {f: "" for f in self.output_field_names()}
        for area in areas:
            if area.type.code == self.mapit_area_type:
                fields["{0} - Name".format(self.name)] = area.name
                fields["{0} - GSS Code".format(self.name)] = area.all_codes.get('gss', '')  # NOQA
                fields["{0} - MapIt ID".format(self.name)] = area.id
                break
        return fields
