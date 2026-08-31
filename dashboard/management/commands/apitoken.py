"""Issue, list and revoke the tokens the product API authenticates with.

The product endpoints do not accept the browser session, so a team that wants to
scrape them needs a token that somebody deliberately issued. This is how one is
issued, without going through the admin UI.

    python manage.py apitoken --list
    python manage.py apitoken alice --create
    python manage.py apitoken alice --show
    python manage.py apitoken alice --revoke

A token is printed once, when it is created. Django stores it in full rather
than hashed, so --show can print it again -- that is DRF's design, not a choice
made here, and it is worth knowing when deciding who may reach the database.

One token per user, which is DRF's model. Revoking cuts off every script using
that identity, so give a scraper its own service account rather than reusing a
person's.
"""
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from rest_framework.authtoken.models import Token


class Command(BaseCommand):
    help = 'Issue, list or revoke product API tokens.'

    def add_arguments(self, parser):
        parser.add_argument('username', nargs='?', help='the user to act on')
        group = parser.add_mutually_exclusive_group()
        group.add_argument('--create', action='store_true',
                           help='issue a token, or print the existing one')
        group.add_argument('--show', action='store_true', help='print an existing token')
        group.add_argument('--revoke', action='store_true', help='delete the token')
        group.add_argument('--rotate', action='store_true',
                           help='replace the token with a new one')
        parser.add_argument('--list', action='store_true', help='every user holding a token')

    def handle(self, *args, **options):
        if options['list'] or not options['username']:
            return self._list()

        User = get_user_model()
        try:
            user = User.objects.get(username=options['username'])
        except User.DoesNotExist:
            raise CommandError(f"No user named {options['username']!r}.")

        if options['revoke']:
            deleted, _ = Token.objects.filter(user=user).delete()
            self.stdout.write(self.style.SUCCESS(
                f'Revoked the token for {user.username}.' if deleted
                else f'{user.username} had no token.'))
            return

        if options['rotate']:
            Token.objects.filter(user=user).delete()
            token = Token.objects.create(user=user)
            self._print(user, token, 'Rotated')
            return

        if options['show']:
            token = Token.objects.filter(user=user).first()
            if not token:
                raise CommandError(f'{user.username} has no token. Use --create.')
            self._print(user, token, 'Existing')
            return

        token, created = Token.objects.get_or_create(user=user)
        self._print(user, token, 'Created' if created else 'Existing')

    def _print(self, user, token, what):
        self.stdout.write('')
        self.stdout.write(self.style.SUCCESS(f'{what} token for {user.username}'))
        self.stdout.write(f'  {token.key}')
        self.stdout.write('')
        self.stdout.write('Use it as:')
        self.stdout.write(f'  curl -H "Authorization: Token {token.key}" \\')
        self.stdout.write('       https://<host>/api/v2/finops/quotas/')
        self.stdout.write('')

    def _list(self):
        tokens = Token.objects.select_related('user').order_by('user__username')
        if not tokens:
            self.stdout.write('No product API tokens have been issued.')
            return
        self.stdout.write(f'{"USER":<24} {"CREATED":<12} ACTIVE')
        for token in tokens:
            self.stdout.write(
                f'{token.user.username:<24} '
                f'{token.created.date().isoformat():<12} '
                f'{"yes" if token.user.is_active else "NO -- user disabled"}'
            )
