#!/usr/bin/env python
from collections import Counter
from datetime import timedelta, datetime

import click
import requests
from colorama import Fore
from functools import reduce
from github import Github, UnknownObjectException, NamedUser


def extract_reviewers(pull_request, extract_weight):
    sources = [
        set([rev.user for rev in pull_request.get_reviews() if rev.state in ['APPROVED', 'REQUEST_CHANGES']]),
        set([rev for rev in pull_request.get_review_requests()[0] if isinstance(rev, NamedUser.NamedUser)]),
        set([rev for rev in pull_request.get_review_requests()[1] if isinstance(rev, NamedUser.NamedUser)])
    ]
    points = extract_weight(pull_request)
    return {user: points for user in reduce(set.union, sources)}


def extract_complex(pull_request):
    return pull_request.additions + pull_request.deletions


def extract_simple(pull_request):  # noqa
    return 1


def print_bar(iteration, total, prefix='', length=44):
    percent = round(100 * (iteration / float(total)), 1)
    filled = int(length * iteration // total)
    bar = '#' * filled + '-' * (length - filled)
    click.echo('{}{:<25}{} [{}] {:>7}% ({})'
               .format(Fore.GREEN, prefix, Fore.RESET, bar, percent, iteration))


def print_list_item(item):
    click.echo(' ✥ {}{}{}'.format(Fore.GREEN, item, Fore.RESET))


def display_user_counter(counter, headline):
    total_sum = sum(counter.values())
    click.echo()
    click.echo(headline)

    for item, i in sorted(counter.items(), key=lambda pair: pair[1], reverse=True):
        print_bar(i, total_sum, prefix=item.login)


def time_condition(pull_request, condition):
    """Returns True if pull_request's created_at matches given time frame."""

    if condition == 'all':
        return True
    elif condition == 'week':
        delta = timedelta(days=7)
    elif condition == 'month':
        delta = timedelta(days=31)
    elif condition == 'year':
        delta = timedelta(days=365)
    else:
        return False

    return pull_request.created_at > datetime.now() - delta

def get_comment_author_name(comment):
    return comment.user.login

def print_users_with_comment_count(users_with_comment_count):
    print("\nComment count per user:")
    for (name, comment_count) in users_with_comment_count:
        print(f"{name}:".ljust(20, ' ') + str(comment_count))


@click.group()
@click.option('--token', envvar='GITHUB_TOKEN')
def cli(token):
    if not token:
        raise click.ClickException('Please provide env variable `GITHUB_TOKEN`')
    cli.token = token


@cli.command()
@click.argument('name')
@click.option('--weight-method', '-w', default='changes',
              type=click.Choice(['simple', 'changes']),
              help='Select method of calculating weights of pull requests.')
@click.option('--label', '-l', 'label_list', multiple=True)
@click.option('--state', default='open')
@click.option('--younger-than', '-y', 'younger_than',
              help='Take into account only pull requests younger than.',
              type=click.Choice(['week', 'month', 'year', 'all']), default='month')
def show(name, label_list, state, weight_method, younger_than):
    """Display reviewers stats for given repository"""
    g = Github(cli.token)

    try:
        pull_requests = g.get_repo(name).get_pulls(state)
    except UnknownObjectException:
        raise click.ClickException('Repository not found!')

    # filter by creation date
    pull_requests = [request for request in pull_requests if time_condition(request, younger_than)]
    pull_requests_length = len(pull_requests)

    review_counter = Counter()
    creator_counter = Counter()

    if weight_method == 'simple':
        extract_weight = extract_simple
    else:
        extract_weight = extract_complex

    if label_list:
        label_set = set(label_list)
        pull_requests = [p for p in pull_requests if
                         label_set <= set(l.name for l in p.labels)]
        pull_requests_length = len(pull_requests)

    with click.progressbar(pull_requests, length=pull_requests_length,
                           show_eta=False, label='Processing Pull Requests') as pull_requests_bar:
        for pull in pull_requests_bar:
            review_counter.update(extract_reviewers(pull, extract_weight))
            creator_counter.update({pull.user: extract_weight(pull)})
    display_user_counter(review_counter, 'Reviewers ranking:')
    display_user_counter(creator_counter, 'Creators ranking:')


@cli.command()
@click.argument('name')
def labels(name):
    """Display list of labels for given repository."""
    g = Github(cli.token)
    try:
        for label in g.get_repo(name).get_labels():
            print_list_item(label.name)
    except requests.exceptions.ConnectionError:
        raise click.ClickException('Check your internet connection!')
    except UnknownObjectException:
        raise click.ClickException('Repository not found!')


@cli.command()
def repos():
    """Show list of your repos."""
    g = Github(cli.token)
    try:
        for repo in g.get_user().get_repos():
            print_list_item(repo.full_name)
    except requests.exceptions.ConnectionError:
        raise click.ClickException('Check your internet connection!')


@cli.command()
@click.argument('name')
@click.option('--state', '-s', default='open',
              type=click.Choice(['open', 'closed', 'all']),
              help='Select which category of pull requests you want to retrieve comments from.')
def comments(name, state):
    """Display number of review comments per user for a given repository."""
    g = Github(cli.token)
    try:
        pull_requests = g.get_repo(name).get_pulls(state=state)
        with click.progressbar(pull_requests, length=pull_requests.totalCount,
                        show_eta=False, label='Processing Pull Requests') as pull_requests_bar:
            user_names = []
            for pull_request in pull_requests_bar:
                comments = pull_request.get_comments()
                user_names += (list(map(get_comment_author_name, comments)))

        sorted_comment_count = Counter(user_names).most_common()
        print_users_with_comment_count(sorted_comment_count)
    except requests.exceptions.ConnectionError:
        raise click.ClickException('Check your internet connection!')
    except UnknownObjectException:
        raise click.ClickException('Repository not found!')


if __name__ == '__main__':
    cli()
