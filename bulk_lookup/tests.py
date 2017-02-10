from StringIO import StringIO

from django.core.urlresolvers import reverse
from django.test import TestCase


class BulkLookupViewTest(TestCase):
    def test_resubmission(self):
        response = self.client.post(reverse('home'), {
            'wizard_view-current_step': 'csv',
            'csv-original_file': StringIO('ID,Postcode\n1,SW1A1AA\n2,EH11BB'),
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
        response = self.client.post(reverse('home'), {
            'wizard_view-current_step': 'csv',
            'csv-original_file': StringIO('ID,Different\n1,SW1A1AA\n2,EH11BB'),
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
