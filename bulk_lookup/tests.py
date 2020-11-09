import os
from six import StringIO, BytesIO

from django.core.management import call_command
from django.core.files.base import ContentFile, File
from django.urls import reverse
from django.test import TestCase

from bulk_lookup import csv, models


class BulkLookupViewTest(TestCase):
    def test_resubmission(self):
        csv_file = StringIO('ID,Postcode\n1,SW1A1AA\n2,EH11BB')
        csv_file.content_type = 'text/csv'
        response = self.client.post(reverse('home'), {
            'wizard_view-current_step': 'csv',
            'csv-original_file': csv_file,
        })
        self.assertEqual(len(response.context['form'].errors), 0)
        response = self.client.post(reverse('home'), {
            'wizard_view-current_step': 'postcode_field',
            'postcode_field-postcode_field': 'Bad',
        })
        self.assertFormError(
            response, 'form', 'postcode_field', 'Select a valid choice. Bad is not one of the available choices.')
        response = self.client.post(reverse('home'), {
            'wizard_view-current_step': 'postcode_field',
            'postcode_field-postcode_field': 'Postcode',
        })
        self.assertEqual(len(response.context['form'].errors), 0)
        csv_file = StringIO('ID,Different\n1,SW1A1AA\n2,EH11BB')
        csv_file.content_type = 'text/csv'
        response = self.client.post(reverse('home'), {
            'wizard_view-current_step': 'csv',
            'csv-original_file': csv_file,
        })
        self.assertContains(response, 'Different')
        self.assertEqual(len(response.context['form'].errors), 0)

    def test_direct_mid_submissions(self):
        self.client.get(reverse('home'))
        self.client.post(reverse('home'), {
            'wizard_view-current_step': 'postcode_field',
            'postcode_field-postcode_field': 'Postcode',
        })

        self.client.post(reverse('home'), {
            'wizard_view-current_step': 'csv',
            'csv-original_file': StringIO('ID,Postcode\n1,SW1A1AA\n2,EH11BB'),
        })
        self.client.post(reverse('home'), {
            'wizard_view-current_step': 'output_options',
        })

    def test_extra_commas(self):
        b = models.BulkLookup.objects.create(
            postcode_field='Postcode',
        )
        b.original_file.save("test.csv", ContentFile("ID,Postcode\n1,SW1A1AA,,\n2,EH11BB"))
        o = models.OutputOption.objects.create(name='Constituency', mapit_area_type='WMC')
        b.output_options.add(o)
        call_command('process_bulk_lookups')

    def test_excel_ods_files(self):
        data = [
            {'Postcode': 'B2 4QA', 'ID': 1, 'Name': 'Alice'},
            {'Postcode': 'M60 7RA', 'ID': 2, 'Name': 'Amanda'},
            {'Postcode': 'EH1 1BB', 'ID': 3, 'Name': 'Annabel'},
        ]
        for typ in ('csv', 'xlsx', 'ods'):
            with open(os.path.dirname(__file__) + '/fixtures/test.' + typ, 'rb') as fp:
                reader = csv.PyExcelReader(File(fp))
                self.assertEqual(reader.fieldnames, ['ID', 'Name', 'Postcode'])
                self.assertEqual(list(reader), data)

    def test_null_byte(self):
        csv_file = StringIO('ID,Postcode\n1,SW1A1AA\n2,EH11BB\0')
        csv_file.content_type = 'text/csv'
        self.client.post(reverse('home'), {
            'wizard_view-current_step': 'csv',
            'csv-original_file': csv_file,
        })

    def test_cp1252_file(self):
        csv_file = BytesIO(b'ID,Postcode\nKing\x92s Lynn,SW1A1AA\nCambridge,EH11BB\0')
        csv_file.content_type = 'text/csv'
        response = self.client.post(reverse('home'), {
            'wizard_view-current_step': 'csv',
            'csv-original_file': csv_file,
        })
        self.assertContains(response, u'King\u2019s Lynn')

    def test_unicode_file_split(self):
        # codecs reads in 72 bytes at a time...
        csv_file = StringIO(u'ID,Postcode\nKings Lynn,SW1A1AA\nCambridge,EH11BB\nPenzance,SW1A0AA\nAn caf\u018d\n')
        csv_file.content_type = 'text/csv'
        response = self.client.post(reverse('home'), {
            'wizard_view-current_step': 'csv',
            'csv-original_file': csv_file,
        })
        self.assertContains(response, u'Penzance')
