# encoding: utf-8

import re
from django import forms
from django.utils.encoding import smart_str

from ukpostcodeutils.validation import is_valid_postcode

from .models import OutputOption


def clean_postcode(pc):
    return re.sub('[^A-Z0-9]', '', smart_str(pc).upper())


class CSVForm(forms.Form):
    original_file = forms.FileField(
        label='Step 1: Upload a CSV, Excel or OpenDocument file '
              'which includes a column of the postcodes you wish to match')

    def clean_original_file(self):
        original_file = self.cleaned_data['original_file']
        if original_file:
            file_type = original_file.content_type
            # e.g. application/ vnd.ms-excel, vnd.openxmlformats-officedocument.spreadsheetml.sheet
            if 'excel' not in file_type and 'xls' not in file_type and \
                    'spreadsheet' not in file_type and 'csv' not in file_type:
                raise forms.ValidationError('I’m afraid we only support CSV, Excel or OpenDocument files.')
        return original_file


class PostcodeFieldForm(forms.Form):
    # This is hidden by default and only shown if the CSV fails validation
    skip_bad_rows = forms.BooleanField(
        widget=forms.HiddenInput(),
        required=False,
        label="Yes, skip those bad rows"
    )
    postcode_field = forms.ChoiceField(
        label='Please confirm the column which contains the postcodes you’d like to match',
        required=True)
    bad_rows = forms.IntegerField(widget=forms.HiddenInput(), required=False)
    num_rows = forms.IntegerField(widget=forms.HiddenInput(), required=False)

    def __init__(self, *args, **kwargs):
        self.bulk_lookup = kwargs.pop('bulk_lookup')
        postcode_fields = self.bulk_lookup.postcode_field_choices()
        super(PostcodeFieldForm, self).__init__(*args, **kwargs)
        self.fields['postcode_field'].choices = postcode_fields
        if self.data:
            # Make mutable so bad/num row items can be 'set' in process
            self.data = self.data.copy()

    def clean(self):
        cleaned_data = super(PostcodeFieldForm, self).clean()
        postcode_field = cleaned_data.get('postcode_field')
        if not postcode_field:
            return cleaned_data

        skip_bad_rows = cleaned_data.pop('skip_bad_rows')
        bad_rows = cleaned_data.get('bad_rows')
        num_rows = cleaned_data.get('num_rows')
        if num_rows and not (bad_rows > 0 and not skip_bad_rows):
            return cleaned_data

        bad_row_numbers = []
        if not num_rows:
            bad_rows = num_rows = 0
            for i, row in enumerate(self.bulk_lookup.original_file_reader()):
                postcode = clean_postcode(row[postcode_field])
                num_rows += 1
                if not is_valid_postcode(postcode):
                    bad_rows += 1
                    bad_row_numbers.append(str(i + 1))
            self.data['postcode_field-num_rows'] = num_rows
            self.data['postcode_field-bad_rows'] = bad_rows

        if not skip_bad_rows and bad_rows > 0:
            # Make sure the skip checkbox is shown next time
            self.fields['skip_bad_rows'].widget = forms.CheckboxInput()
            if not bad_row_numbers:
                msg = 'Please confirm you wish to skip the invalid rows.'
            elif bad_rows == 1:
                msg = 'Row: '
                msg += ', '.join(bad_row_numbers)
                msg += u' doesn’t seem to be a valid postcode.'
                msg += ' Do you want us to skip it?'
            else:
                msg = 'Rows: '
                msg += ', '.join(bad_row_numbers)
                msg += u' don’t seem to be valid postcodes.'
                msg += ' Do you want us to skip them?'
            raise forms.ValidationError(msg)

        return cleaned_data


class OutputOptionsForm(forms.Form):
    output_options = forms.ModelMultipleChoiceField(
        label='You may select any number of the outputs below',
        error_messages={'required': 'Please select at least one output'},
        queryset=OutputOption.objects.all(),
        widget=forms.CheckboxSelectMultiple)


class PersonalDetailsForm(forms.Form):
    email = forms.CharField(
        max_length=254, widget=forms.EmailInput,
        help_text='''We’ll email to let you know when your file is ready. In most
        cases this will not take long, but in times of high demand processing
        may take a few hours.''')
    description = forms.CharField(
        required=False,
        help_text='You can add a note here if you need to keep track of multiple files.')
