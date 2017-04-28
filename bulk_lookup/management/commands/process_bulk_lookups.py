import os
import tempfile
import traceback
import unicodecsv as csv

from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone
from django.core.files import File
from django.core.mail import send_mail
from django.contrib.sites.shortcuts import get_current_site

from ukpostcodeutils.validation import is_valid_postcode

from ...models import BulkLookup
from ...forms import clean_postcode

from mapit.models import Postcode, Area, Generation
from mapit.views.areas import add_codes


class Command(BaseCommand):
    help = "Processes all the bulk lookup jobs that need processing"

    def handle(self, *args, **options):
        self.generation = Generation.objects.current()
        for bulk_lookup in BulkLookup.objects.needs_processing():
            self.process_job(bulk_lookup)

    def process_job(self, bulk_lookup):
        try:
            with transaction.atomic():
                bulk_lookup.started = timezone.now()
                bulk_lookup.save()
                self.do_lookup(bulk_lookup)
                bulk_lookup.finished = timezone.now()
                bulk_lookup.save()
                self.send_success_email(bulk_lookup)
        except Exception, e:
            traceback.print_exc()
            bulk_lookup.started = None
            bulk_lookup.finished = None
            bulk_lookup.error_count += 1
            bulk_lookup.last_error = timezone.now()
            bulk_lookup.save()

    def do_lookup(self, bulk_lookup):
        with tempfile.TemporaryFile() as f:
            writer = csv.DictWriter(f, bulk_lookup.output_field_names())
            writer.writeheader()
            postcode_field = bulk_lookup.postcode_field
            output_options = bulk_lookup.output_options.all()
            for row in bulk_lookup.original_file_reader():
                self.lookup_row(row, postcode_field, output_options)
                writer.writerow(row)
            original_filename = os.path.basename(
                bulk_lookup.original_file.name
            )
            base_filename, extension = os.path.splitext(original_filename)
            output_filename = '%s-mapit%s' % (base_filename, extension)
            bulk_lookup.output_file.save(output_filename, File(f))

    def lookup_row(self, row, postcode_field, output_options):
        postcode = clean_postcode(row[postcode_field])
        if is_valid_postcode(postcode):
            try:
                pc = Postcode.objects.get(postcode=postcode)
                areas = list(add_codes(Area.objects.by_postcode(pc, self.generation)))
                self.process_mapit_response(areas, row, output_options)
            except Postcode.DoesNotExist:
                pass

    def process_mapit_response(self, areas, row, output_options):
        for output_option in output_options:
            row.update(output_option.get_from_mapit_response(areas))

    def send_success_email(self, bulk_lookup):
        url = ''.join([
            'https://',
            get_current_site(None).domain,
            bulk_lookup.output_file.url
        ])
        message = """
We have matched your postcodes and added all the results to your data.

You can download your new file from {0}

Thanks for using MapIt, a service from mySociety.
""".format(url)
        send_mail(
            'Your MapIt file is ready',
            message,
            settings.CONTACT_EMAIL,
            [bulk_lookup.email],
            fail_silently=False
        )
