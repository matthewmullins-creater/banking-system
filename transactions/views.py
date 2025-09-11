from dateutil.relativedelta import relativedelta

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.urls import reverse_lazy
from django.utils import timezone
from django.views.generic import CreateView, ListView
from django.db import models
from decimal import Decimal
from django.db import transaction
from django.db.models import F

from transactions.constants import DEPOSIT, WITHDRAWAL
from transactions.forms import (
    DepositForm,
    TransactionDateRangeForm,
    WithdrawForm,
)
from transactions.models import Transaction
from accounts.models import BankAccountType, UserBankAccount


class TransactionReportView(LoginRequiredMixin, ListView):
    template_name = 'transactions/transaction_report.html'
    model = Transaction
    form_data = {}

    def get(self, request, *args, **kwargs):
        form = TransactionDateRangeForm(request.GET or None)
        if form.is_valid():
            self.form_data = form.cleaned_data

        return super().get(request, *args, **kwargs)

    def get_queryset(self):
        # queryset = super().get_queryset().filter(
        #     account=self.request.user.account
        # )
        queryset = super().get_queryset().select_related('account', 'account__user')
        queryset = queryset.filter(
            account__user=self.request.user
        )

        daterange = self.form_data.get("daterange")

        if daterange:
            queryset = queryset.filter(timestamp__date__range=daterange)

        return queryset.distinct()

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        account = getattr(self.request.user, 'account', None)
        context.update({
            'account': account,
            'form': TransactionDateRangeForm(self.request.GET or None)
        })

        return context


class TransactionCreateMixin(LoginRequiredMixin, CreateView):
    template_name = 'transactions/transaction_form.html'
    model = Transaction
    title = ''
    success_url = reverse_lazy('transactions:transaction_report')

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        account = getattr(self.request.user, 'account', None)
        kwargs.update({
            'account': account,
        })
        return kwargs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update({
            'title': self.title
        })

        return context


class DepositMoneyView(TransactionCreateMixin):
    form_class = DepositForm
    title = 'Deposit Money to Your Account'

    def get_initial(self):
        initial = {'transaction_type': DEPOSIT}
        return initial
    
    def _get_or_create_account(self, user):
        default_type = BankAccountType.objects.first()
        if default_type is None:
            return None, False
        
        acct, created = UserBankAccount.objects.get_or_create(
            user=user,
            defaults={
                'account_type': default_type,
                'account_no': (UserBankAccount.objects.aggregate(m=models.Max('account_no'))['m'] or 10000000) + 1,
                'gender': 'U',
                'balance': Decimal('0.00'),
            },
        )
        return acct, created

    def dispatch(self, request, *args, **kwargs):
        self.account = getattr(request.user, 'account', None)
        if self.account is None:
            self.account, _ = self._get_or_create_account(request.user)
        return super().dispatch(request, *args, **kwargs)

    @transaction.atomic
    def form_valid(self, form):
        amount = form.cleaned_data.get('amount')
        # account = self.request.user.account
        if not amount or amount <= 0:
            form.add_error('amount', 'Amount must be positive.')
            return self.form_invalid(form)

        if self.account is None:
            messages.error(self.request, "No bank account found; please try again.")
            return self.form_invalid(form)

        account = UserBankAccount.objects.select_for_update().get(pk=self.account.pk)
        
        if not account.initial_deposit_date:
            now = timezone.now().date()
            next_interest_month = int(
                12 / account.account_type.interest_calculation_per_year
            )
            account.initial_deposit_date = now
            account.interest_start_date = (
                now + relativedelta(
                    months=+next_interest_month
                )
            )

        account.balance = F('balance') + amount
        account.save(
            update_fields=[
                'initial_deposit_date',
                'balance',
                'interest_start_date'
            ]
        )
        account.refresh_from_db(fields=['balance'])

        form.instance.account = account
        form.instance.balance_after_transaction = account.balance

        messages.success(
            self.request,
            f'{amount}$ was deposited to your account successfully.'
        )

        return super().form_valid(form)

    def form_invalid(self, form):
        messages.error(
            self.request,
            'There was an error with your deposit. Please correct the errors below.'
        )
        return super().form_invalid(form)

class WithdrawMoneyView(TransactionCreateMixin):
    form_class = WithdrawForm
    title = 'Withdraw Money from Your Account'

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs["user"] = self.request.user
        return kwargs

    def get_initial(self):
        initial = {'transaction_type': WITHDRAWAL}
        return initial

    def form_valid(self, form):
        amount = form.cleaned_data.get('amount')

        self.request.user.account.balance -= form.cleaned_data.get('amount')
        self.request.user.account.save(update_fields=['balance'])

        messages.success(
            self.request,
            f'Successfully withdrawn {amount}$ from your account'
        )

        return super().form_valid(form)
