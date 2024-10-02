# -*- coding: utf-8 -*-

from django import forms
from django.conf import settings
from django.core.exceptions import ValidationError
from django.utils.safestring import mark_safe


def describe_price(i):
    s = settings.PRICING[i]
    if s['calls'] == '0':
        desc = '£%d/mth - Unlimited calls' % s['price']
    else:
        desc = '£%d/mth - %s calls per month' % (s['price'], s['calls'])
    return (s['id'], desc)


class SubscriptionMixin(forms.Form):
    price = forms.ChoiceField(choices=(
        describe_price(i) for i in range(3)
    ), label='Please choose a plan', widget=forms.RadioSelect)
    charitable_tick = forms.BooleanField(
        label='I qualify for a charitable discounted price',
        required=False)
    charitable = forms.ChoiceField(required=False, choices=(
        ('c', 'Registered charity'),
        ('i', 'Individual pursuing a non-profit project on an unpaid basis'),
        ('o', 'Neither')
    ), label='Are you?', widget=forms.RadioSelect)
    charity_number = forms.CharField(
        label='If charity, please provide your registered charity number',
        max_length=500, required=False)
    description = forms.CharField(
        label='Please provide some details of your project',
        help_text='(optional)',
        max_length=500, required=False)
    interest_contact = forms.BooleanField(
        label=mark_safe('We like to write about interesting uses of MapIt on the mySociety blog. '
                        'Please tick here if you are happy for us to get in touch for this purpose.'),
        required=False)
    tandcs_tick = forms.BooleanField(
        label=mark_safe('I agree to the <a href="/legal/" target="_blank">terms and conditions</a>'),
        required=False)
    stripeToken = forms.CharField(required=False, widget=forms.HiddenInput)
    payment_method = forms.CharField(required=False, widget=forms.HiddenInput)

    def __init__(self, has_payment_data=False, stripe=False, *args, **kwargs):
        self.has_payment_data = has_payment_data
        self.stripe = stripe
        return super(SubscriptionMixin, self).__init__(*args, **kwargs)

    def clean_payment_method(self):
        pm = self.cleaned_data['payment_method']
        if pm and len(pm) < 4:
            raise ValidationError('Invalid value')
        return pm

    def clean(self):
        cleaned_data = super(SubscriptionMixin, self).clean()
        typ = cleaned_data.get('charitable')

        payment_data = cleaned_data.get('stripeToken') or cleaned_data.get('payment_method')
        if not self.has_payment_data and not payment_data and not (
                cleaned_data.get('price') == settings.PRICING[0]['id'] and typ in ('c', 'i')):
            self.add_error('price', 'You need to submit payment')

        if not self.stripe and not cleaned_data.get('tandcs_tick'):
            self.add_error('tandcs_tick', 'Please agree to the terms and conditions')

        if not cleaned_data.get('charitable_tick'):
            self.cleaned_data['charitable'] = ''
            self.cleaned_data['charity_number'] = ''
            self.cleaned_data['description'] = ''
            return
        if typ == 'c' and not self.has_error('charity_number') and not cleaned_data.get('charity_number'):
            self.add_error('charity_number', 'Please provide your charity number')
        if typ == 'i' and not self.has_error('description') and not cleaned_data.get('description'):
            self.add_error('description', 'Please provide details of your project')


class SubsForm(SubscriptionMixin):
    pass
