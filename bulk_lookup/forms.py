import re
from django import forms
from django.conf import settings
from django.utils.crypto import get_random_string

import stripe
from ukpostcodeutils.validation import is_valid_postcode

from .models import OutputOption


def clean_postcode(pc):
    return re.sub('[^A-Z0-9]', '', pc.upper())


class CSVForm(forms.Form):
    original_file = forms.FileField()


class PostcodeFieldForm(forms.Form):
    # This is hidden by default and only shown if the CSV fails validation
    skip_bad_rows = forms.BooleanField(
        widget=forms.HiddenInput(),
        required=False,
        label="Yes, skip those bad rows"
        )
    postcode_field = forms.ChoiceField(required=True)
    bad_rows = forms.IntegerField(widget=forms.HiddenInput(), required=False)

    def __init__(self, *args, **kwargs):
        self.bulk_lookup = kwargs.pop('bulk_lookup')
        postcode_fields = self.bulk_lookup.postcode_field_choices()
        super(PostcodeFieldForm, self).__init__(*args, **kwargs)
        self.fields['postcode_field'].choices = postcode_fields

    def clean(self):
        cleaned_data = super(PostcodeFieldForm, self).clean()
        postcode_field = cleaned_data.get('postcode_field')
        skip_bad_rows = cleaned_data.get('skip_bad_rows')
        bad_rows = 0
        bad_row_numbers = []
        for i, row in enumerate(self.bulk_lookup.original_file_reader()):
            postcode = clean_postcode(row[postcode_field])
            if not is_valid_postcode(postcode):
                bad_rows += 1
                bad_row_numbers.append(str(i + 1))
        if not skip_bad_rows and bad_rows > 0:
            # Make sure the skip checkbox is shown next time
            self.fields['skip_bad_rows'].widget = forms.CheckboxInput()
            if bad_rows == 1:
                msg = 'Row: '
                msg += ', '.join(bad_row_numbers)
                msg += ' doesn\'t seem to be a valid postcode.'
                msg += ' Do you want us to skip it?'
            else:
                msg = 'Rows: '
                msg += ', '.join(bad_row_numbers)
                msg += ' don\'t seem to be valid postcodes.'
                msg += ' Do you want us to skip them?'
            raise forms.ValidationError(msg)
        else:
            cleaned_data['bad_rows'] = bad_rows
            del cleaned_data['skip_bad_rows']
        return cleaned_data


class OutputOptionsForm(forms.Form):
    output_options = forms.ModelMultipleChoiceField(
        queryset=OutputOption.objects.all(),
        widget=forms.CheckboxSelectMultiple)


class PersonalDetailsForm(forms.Form):
    email = forms.CharField(max_length=254)
    description = forms.CharField()
    stripeToken = forms.CharField(widget=forms.HiddenInput, required=False)
    charge_id = forms.CharField(widget=forms.HiddenInput, required=False)

    def __init__(self, amount, free, *args, **kwargs):
        self.amount = amount
        self.free = free
        super(PersonalDetailsForm, self).__init__(*args, **kwargs)

    def clean(self):
        """
        Validate everything by trying to charge the card with Stripe
        """
        super(PersonalDetailsForm, self).clean()
        # If we're doing this for free
        if self.free and not self.cleaned_data['charge_id']:
            self.cleaned_data['charge_id'] = 'r_%s' % get_random_string()
        # If we've already successfully been here before
        if self.cleaned_data['charge_id']:
            del self.cleaned_data['stripeToken']
            return
        if not self.cleaned_data['stripeToken']:
            raise forms.ValidationError("You need to pay for the lookup")
        stripe.api_key = settings.STRIPE_SECRET_KEY
        try:
            charge = stripe.Charge.create(
                amount=self.amount * 100,
                currency="gbp",
                receipt_email=self.cleaned_data['email'],
                source=self.cleaned_data['stripeToken'],
                description=self.cleaned_data['description'])
            self.cleaned_data['charge_id'] = charge.id
            del self.cleaned_data['stripeToken']
        except stripe.CardError, e:
            # The card has been declined
            raise forms.ValidationError(
                """
                Sorry, your card has been declined.
                Perhaps you can try another?
                """
            )
