# -*- coding: utf-8 -*-

from django import forms
from django.conf import settings
from django.utils.safestring import mark_safe


def describe_plan(i):
    s = settings.PRICING[i]
    if s['calls'] == '0':
        desc = '£%d/mth - Unlimited calls' % s['price']
    else:
        desc = '£%d/mth - %s calls per month' % (s['price'], s['calls'])
    return (s['plan'], desc)


class SubscriptionMixin(forms.Form):
    plan = forms.ChoiceField(choices=(
        describe_plan(i) for i in range(3)
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
        required=False)
    description = forms.CharField(
        label='If an individual, please provide details of your project',
        required=False)
    tandcs_tick = forms.BooleanField(
        label=mark_safe('I agree to the <a href="/legal" target="_blank">terms and conditions</a>'),
        required=True)
    stripeToken = forms.CharField(required=False, widget=forms.HiddenInput)

    def clean(self):
        cleaned_data = super(SubscriptionMixin, self).clean()
        typ = cleaned_data.get('charitable')

        if not cleaned_data.get('stripeToken') and not (
          cleaned_data.get('plan') == settings.PRICING[0]['plan'] and typ in ('c', 'i')):
            self.add_error('plan', 'You need to submit payment')

        if not cleaned_data.get('charitable_tick'):
            self.cleaned_data['charitable'] = ''
            self.cleaned_data['charity_number'] = ''
            self.cleaned_data['description'] = ''
            return
        if typ == 'c' and not cleaned_data.get('charity_number'):
            self.add_error('charity_number', 'Please provide your charity number')
        if typ == 'i' and not cleaned_data.get('description'):
            self.add_error('description', 'Please provide details of your project')