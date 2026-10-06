'''Stdlib-only key helpers shared by the catalogue build and the device catalogue jobs.

The device jobs run without the site dependencies (markdown/mkdocs), so ``slugify`` mirrors
``markdown.extensions.toc.slugify`` (python-markdown 3.x) exactly rather than importing it.
'''
import re
import unicodedata


def slugify(value: str, separator: str) -> str:
    value = unicodedata.normalize('NFKD', value)
    value = value.encode('ascii', 'ignore').decode('ascii')
    value = re.sub(r'[^\w\s-]', '', value).strip().lower()
    return re.sub(r'[{}\s]+'.format(separator), separator, value)


def compute_compare_key(title: str, content_type: str, the_movie_db: str = '', year: str = '') -> str:
    ''' a stable, cross-author key for a title used to group filter comparison data;
    mirrors the theMovieDB/year suffix scheme used for per-author page slugs so that
    the same film/show maps to the same key regardless of which author submitted it '''
    suffix = the_movie_db or year or ''
    base = f"{title}_{suffix}" if suffix else title
    return f"{content_type}-{slugify(base.casefold(), '-')}"
