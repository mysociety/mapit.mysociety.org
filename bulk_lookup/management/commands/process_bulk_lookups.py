from collections import defaultdict, OrderedDict
import os
import tempfile
import traceback
import pyexcel
import defusedxml

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

defusedxml.defuse_stdlib()


class Command(BaseCommand):
    help = "Processes all the bulk lookup jobs that need processing"

    def handle(self, *args, **options):
        self.generation = Generation.objects.current()
        for bulk_lookup in BulkLookup.objects.needs_processing():
            self.process_job(bulk_lookup)

    def process_job(self, bulk_lookup):
        try:
            with transaction.atomic():
                # Get a row level lock before processing
                try:
                    lock = BulkLookup.objects.select_for_update(skip_locked=True).get(pk=bulk_lookup.pk)
                    # Just check it hasn't been dealt with in the time since the list was fetched
                    if lock.started:
                        return
                except BulkLookup.DoesNotExist:
                    return

                bulk_lookup.started = timezone.now()
                bulk_lookup.save()
                self.do_lookup(bulk_lookup)
                bulk_lookup.finished = timezone.now()
                bulk_lookup.save()
                self.send_success_email(bulk_lookup)
        except Exception:
            traceback.print_exc()
            bulk_lookup.started = None
            bulk_lookup.finished = None
            bulk_lookup.error_count += 1
            bulk_lookup.last_error = timezone.now()
            bulk_lookup.save()

    def do_lookup(self, bulk_lookup):
        self.column_names = bulk_lookup.output_field_names()

        with tempfile.TemporaryFile(mode='w+') as f:
            postcode_field = bulk_lookup.postcode_field
            output_options = bulk_lookup.output_options.all()
            self.header_row_done = False
            rows = (self.lookup_row(row, postcode_field, output_options)
                    for row in bulk_lookup.original_file_reader())
            original_filename = os.path.basename(
                bulk_lookup.original_file.name
            )
            base_filename, extension = os.path.splitext(original_filename)
            output_filename = '%s-mapit.csv' % base_filename
            pyexcel.isave_as(
                dest_file_stream=f, dest_file_type='csv', records=rows,
                auto_detect_float=False, auto_detect_int=False)
            bulk_lookup.output_file.save(output_filename, File(f))
            bulk_lookup.original_file.close()

    def lookup_row(self, row, postcode_field, output_options):
        postcode = clean_postcode(row[postcode_field])
        if is_valid_postcode(postcode):
            try:
                pc = Postcode.objects.get(postcode=postcode)
                areas = list(add_codes(Area.objects.by_postcode(pc, self.generation)))
                self.process_mapit_response(areas, row, output_options)
            except Postcode.DoesNotExist:
                pass
        row = defaultdict(lambda: "", row)
        if not self.header_row_done:
            # The writer gets the column order by the first row being ordered
            self.header_row_done = True
            ret = OrderedDict()
            for key in self.column_names:
                ret[key] = row[key]
            return ret
        return row

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
