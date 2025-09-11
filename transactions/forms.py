import datetime

from django import forms
from django.conf import settings
from decimal import Decimal
from .models import Transaction


class TransactionForm(forms.ModelForm):

    class Meta:
        model = Transaction
        fields = [
            'amount',
            'transaction_type'
        ]

    def __init__(self, *args, **kwargs):
        self.account = kwargs.pop('account')
        super().__init__(*args, **kwargs)

        self.fields['transaction_type'].disabled = True
        self.fields['transaction_type'].widget = forms.HiddenInput()

    def save(self, commit=True):
        self.instance.account = self.account
        self.instance.balance_after_transaction = self.account.balance
        return super().save()


class DepositForm(TransactionForm):

    def clean_amount(self):
        min_deposit_amount = settings.MINIMUM_DEPOSIT_AMOUNT
        amount = self.cleaned_data.get('amount')

        if amount < min_deposit_amount:
            raise forms.ValidationError(
                f'You need to deposit at least {min_deposit_amount} $'
            )

        return amount


class WithdrawForm(TransactionForm):
    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = user
        self.account = getattr(user, 'account', None)

    def clean_amount(self):
        if self.account is None:
            raise forms.ValidationError(
                'You do not have a bank account. Please create one before withdrawing.'
            )
        # account = self.account
        # min_withdraw_amount = settings.MINIMUM_WITHDRAWAL_AMOUNT
        # max_withdraw_amount = (
        #     account.account_type.maximum_withdrawal_amount
        # )
        # balance = account.balance

        amount = self.cleaned_data.get('amount')
        if amount is None:
            raise forms.ValidationError('Amount is required.')
        
        try:
            min_withdraw = getattr(settings, 'MINIMUM_WITHDRAWAL_AMOUNT', Decimal("1.00"))
            if not isinstance(min_withdraw, Decimal):
                min_withdraw = Decimal(str(min_withdraw))
        except Exception:
            min_withdraw = Decimal("1.00")
        
        max_withdraw = self.account.account_type.maximum_withdrawal_amount
        balance = self.account.balance

        if amount <= 0:
            raise forms.ValidationError('Amount must be greater than 0.')

        if amount < min_withdraw:
            raise forms.ValidationError(
                f'You can withdraw at least {min_withdraw} $'
            )

        if amount > max_withdraw:
            raise forms.ValidationError(
                f'You can withdraw at most {max_withdraw} $'
            )

        if amount > balance:
            raise forms.ValidationError(
                f'You have {balance} $ in your account. '
                'You can not withdraw more than your account balance'
            )

        return amount


class TransactionDateRangeForm(forms.Form):
    daterange = forms.CharField(required=False)

    def clean_daterange(self):
        daterange = self.cleaned_data.get("daterange")
        print(daterange)

        try:
            daterange = daterange.split(' - ')
            print(daterange)
            if len(daterange) == 2:
                for date in daterange:
                    datetime.datetime.strptime(date, '%Y-%m-%d')
                return daterange
            else:
                raise forms.ValidationError("Please select a date range.")
        except (ValueError, AttributeError):
            raise forms.ValidationError("Invalid date range")
