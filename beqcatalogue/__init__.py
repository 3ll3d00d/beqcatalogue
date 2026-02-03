import csv
import hashlib
import json
import math
import os
import re
import time
import traceback
import xml.etree.ElementTree as ET
from collections import defaultdict
from email.utils import formatdate
from itertools import groupby
from operator import itemgetter
from urllib import parse

from markdown.extensions.toc import slugify

from iir import xml_to_filt

TWO_WEEKS_AGO = time.time() - (2 * 7 * 24 * 60 * 60)


def cleanse_audio_types(audio_types: list[str]) -> list[str]:
    def replace(audio_type: str) -> str:
        if audio_type.startswith('DTS-HD-MA '):
            audio_type = audio_type.replace('DTS-HD-MA ', 'DTS-HD MA ')
        elif audio_type.startswith('DTS-HD.MA '):
            audio_type = audio_type.replace('DTS-HD.MA ', 'DTS-HD MA ')
        elif audio_type.startswith('DTS-HD.MA.'):
            audio_type = audio_type.replace('DTS-HD.MA.', 'DTS-HD MA ')
        elif audio_type.endswith('_to_mono'):
            audio_type = audio_type[0:-8]
        elif audio_type.endswith('_s1_5.1'):
            audio_type = audio_type[0:-7]
        elif audio_type.startswith('DTS-X'):
            audio_type = audio_type.replace('DTS-X', 'DTS:X')
        elif audio_type == 'DTS-X HR':
            audio_type = 'DTS:X HR'
        elif audio_type == 'DD+5 1':
            audio_type = 'DD+ 5.1'
        elif audio_type == 'DD+Atmos':
            audio_type = 'DD+ Atmos'
        elif audio_type == 'DR+ 5.1':
            audio_type = 'DTS-HD MA 5.1'
        return audio_type

    return [replace(at.strip()) for ats in audio_types for at in ats.split(',')]


def parse_audio_format(format_string: str) -> tuple[str, str]:
    # Pattern: capture everything up to the channel count, then capture the channel count
    # Channel count pattern: digits.digits or just standalone formats
    pattern = r'^(.+?)\s*(\d+\.\d+|\d+\s+\d+)?(?:_.*)?$'

    match = re.match(pattern, format_string)
    if match:
        codec = match.group(1).strip()
        channel_count = match.group(2).strip() if match.group(2) else ""
        # Normalize channel count format (e.g., "5 1" -> "5.1")
        if channel_count and ' ' in channel_count:
            channel_count = channel_count.replace(' ', '.')
        return (codec, channel_count)
    return (format_string, "")


def extract_from_repo(path1: str, path2: str, content_type: str, author: str):
    '''
    extracts beq_metadata of following format
           <beq_metadata>
                <beq_title>9</beq_title>
                <beq_alt_title />
                <beq_sortTitle>9</beq_sortTitle>
                <beq_year>2009</beq_year>
                <beq_spectrumURL>https://i.imgur.com/aRic6II.jpg</beq_spectrumURL>
                <beq_pvaURL>https://i.imgur.com/4DReGr5.jpg</beq_pvaURL>
                <beq_edition />
                <beq_season />
                <beq_note />
                <beq_warning />
                <beq_gain>-1 gain</beq_gain>
                <beq_language>English</beq_language>
                <beq_source>Disc</beq_source>
                <beq_author>aron7awol</beq_author>
                <beq_avs>https://www.avsforum.com/threads/bass-eq-for-filtered-movies.2995212/post-57282106</beq_avs>
                <beq_theMovieDB>12244</beq_theMovieDB>
                <beq_runtime>79</beq_runtime>
                <beq_audioTypes>
                        <audioType>DTS-HD MA 5.1</audioType>
                </beq_audioTypes>
                <beq_genres>
                        <genre id="878">Science Fiction</genre>
                        <genre id="16">Animation</genre>
                        <genre id="12">Adventure</genre>
                        <genre id="28">Action</genre>
                        <genre id="53">Thriller</genre>
                </beq_genres>
            </beq_metadata>

        new season format replaces beq_season with

               <beq_season id="92137">
                   <number>1</number>
                   <episodes count="8">1,2,3,4,5,6,7,8</episodes>
               </beq_season>

    :return:
    '''
    import glob
    elements = []
    for xml in sorted(glob.glob(f"{path1}{path2}/**/*.xml", recursive=True)):
        git_path = str(xml)[len(path1):]
        try:
            root = extract_root(xml)
            file_name = xml[:-4]
            meta = {
                'repo_file': str(xml),
                'git_path': git_path,
                'file_name': file_name.split('/')[-1],
                'file_path': '/'.join(file_name[len(path1):].split('/')[:-1]),
                'content_type': content_type
            }
            for child in root:
                if child.tag == 'beq_metadata':
                    for m in child:
                        if len(m) == 0:
                            txt = m.text
                            if txt:
                                if m.tag == 'beq_collection':
                                    if 'id' in m.attrib:
                                        meta[m.tag[4:]] = {'id': m.attrib['id'], 'name': m.text}
                                else:
                                    meta[m.tag[4:]] = m.text
                        elif m.tag == 'beq_audioTypes':
                            audio_types = [c.text.strip() for c in m if c.text]
                            meta['audioType'] = [at for at in audio_types if at]
                        elif m.tag == 'beq_season':
                            parse_season(m, meta, xml)
                        elif m.tag == 'beq_genres':
                            genres = [c.text.strip() for c in m if c.text]
                            meta['genres'] = [at for at in genres if at]
            filts = [f for f in xml_to_filt(xml, unroll=True)]
            meta['jsonfilters'] = [f.to_map() for f in filts]
            meta['filters'] = '^'.join([str(f) for f in filts])
            suffix = get_title_suffix(meta)
            page_title = f"{meta['title']}_{suffix}" if suffix else meta['title']
            meta['page_title'] = page_title.casefold()
            if 'gain' in meta:
                g = meta['gain']
                if g[0] == '+':
                    g = g[1:]
                if g.endswith(' gain'):
                    g = g[:-5]
                meta['gain'] = g
            if 'theMovieDB' in meta:
                db_id = meta['theMovieDB']
                try:
                    int(db_id)
                except ValueError as e:
                    print(f"Non integer theMovieDB '{db_id}' found in {xml}")
                    if db_id[-1] == '"':
                        meta['theMovieDB'] = db_id[:-1]
            elements.append(meta)
        except Exception as e:
            print(f"Unexpected error while extracting metadata from {xml}")
            traceback.print_exc()
            error_files[author].append(f'{git_path}|{e}')

    return elements


def get_title_suffix(meta):
    suffix = meta.get('theMovieDB', None)
    if not suffix:
        suffix = meta.get('year', None)
    return suffix


def extract_root(xml):
    import xml.etree.ElementTree as ET
    et_tree = ET.parse(str(xml))
    root = et_tree.getroot()
    return root


def parse_season(m, meta, xml):
    try:
        meta['season'] = {
            'id': m.attrib['id'],
            'complete': False,
            'episodes': 0
        }
        for c in m:
            if c.tag == 'episodes':
                meta['season']['episode_count'] = c.attrib['count']
            meta['season'][c.tag] = c.text
        complete = True
        if 'episode_count' in meta['season'] and 'episodes' in meta['season']:
            count = int(meta['season']['episode_count'])
            epi_txt = meta['season']['episodes']
            if epi_txt:
                episodes = [int(e) for e in meta['season']['episodes'].split(',')]
                for c in range(count):
                    if c + 1 not in episodes:
                        complete = False
        meta['season']['complete'] = complete
    except:
        print(f"Unable to parse season info from {xml}")


def group_film_content(author, content_meta):
    by_title = defaultdict(list)
    fallback_pattern = re.compile(r'(.*) \((\d{4})\)(?: *\(.*\))? (.*)')
    for meta in content_meta:
        try:
            if 'title' in meta:
                title = meta['title']
                page_title = meta['page_title']
                if title.casefold() in by_title:
                    if page_title == by_title[title.casefold()][0]['page_title']:
                        by_title[title.casefold()].append(meta)
                    else:
                        by_title[page_title.casefold()].append(meta)
                else:
                    by_title[title.casefold()].append(meta)
            else:
                entry = {
                    'title': meta['file_name'],
                    'author': author,
                    'content_type': meta['content_type']
                }
                match = fallback_pattern.match(meta['file_name'])
                if match:
                    entry['title'] = match.group(1)
                    entry['year'] = match.group(2)
                    entry['audioTypes'] = match.group(3).split('+')
                entry['page_title'] = entry['title'].casefold()
                print(f"Missing title entry, extracted {entry}")
                entry['filters'] = meta['jsonfilters']
                add_to_catalogue(entry, meta['git_path'], author)
        except Exception as e:
            print(f'Unexpected error when grouping {meta["git_path"]}')
            error_files[author].append(f'{meta["git_path"]}|{e}')
            traceback.print_exc()
    return by_title


def add_to_catalogue(entry: dict, path: str, author: str):
    entry['digest'] = digest(entry)
    t = times.get(author, [])
    if path in t:
        entry['created_at'] = t[path][0]
        entry['updated_at'] = t[path][1]
    else:
        print(f"Missing times for {author} / {path}")
        entry['created_at'] = 0
        entry['updated_at'] = 0
    json_catalogue.append(entry)


def digest(entry: dict) -> str:
    digest_keys = ['title', 'filters', 'mv', 'season', 'episode']
    to_hash = json.dumps(slice_dict(digest_keys, entry)).encode('utf-8')
    return hashlib.sha256(to_hash).hexdigest()


def group_tv_content(author, content_meta):
    by_title = {}
    fallback_pattern = re.compile(r'(.*) \((\d{4})\)(?: *\(.*\))? (.*)')
    for meta in content_meta:
        try:
            if 'title' in meta:
                title = meta['title']
                if title[-4:-2] == ' E' and title[-2:].isdigit():
                    meta['episode'] = title[-2:]
                    title = title[:-4]
                    meta['title'] = title
                elif 'note' in meta:
                    note = meta['note']
                    if note[0] == 'E':
                        if note[1:].isdigit():
                            meta['episode'] = note[1:]
                        elif '-' in note[1:]:
                            vals = [int(i) for i in note[1:].split('-')]
                            if len(vals) == 2:
                                meta['episode'] = ','.join([str(e) for e in range(vals[0], vals[1] + 1)])
                    elif note[0] == 'S':
                        frags = note.split('-')
                        if len(frags) == 2:
                            if frags[1][0] == 'E':
                                if frags[1][1:].isdigit():
                                    meta['episode'] = frags[1][1:]
                    if 'episode' not in meta:
                        print(f"Unknown note format in TV {meta}")
                    else:
                        del meta['note']
                        print(f"Note used for episode info by {meta['repo_file']}, removing note from meta")
                if title in by_title:
                    by_title[title].append(meta)
                else:
                    by_title[title] = [meta]
            else:
                entry = {
                    'title': meta['file_name'],
                    'author': author,
                    'content_type': meta['content_type']
                }
                match = fallback_pattern.match(meta['file_name'])
                if match:
                    entry['title'] = match.group(1)
                    entry['year'] = match.group(2)
                    entry['audioTypes'] = match.group(3).split('+')
                print(f"Missing title entry, extracted {entry}")
                entry['filters'] = meta['jsonfilters']
                add_to_catalogue(entry, meta['git_path'], author)
        except Exception as e:
            print(f'Unexpected error when grouping {meta["git_path"]}')
            error_files[author].append(f'{meta["git_path"]}|{e}')
            traceback.print_exc()
    return by_title


def process_content_from_repo(author: str, content_meta, index_entries, content_type, pages_touched, created_titles=None):
    ''' converts beq_metadata into md '''
    page_titles = []
    if content_type == 'film':
        by_title = group_film_content(author, content_meta)
    else:
        by_title = group_tv_content(author, content_meta)
    for title, metas in by_title.items():
        title_md = slugify(title, '-')
        if created_titles and title_md in created_titles:
            title_md = f'{title_md}-{content_type}'
        page_titles.append(title_md)
        from pathlib import Path
        Path(f"docs/{author}").mkdir(parents=True, exist_ok=True)
        page = f"docs/{author}/{title_md}.md"
        pages_touched.append(page)
        with open(page, mode='w+') as content_md:
            generate_content_page(title_md, metas, content_md, index_entries, author, content_type)
    return page_titles


def generate_content_page(page_name, metas, content_md, index_entries, author, content_type):
    try:
        if content_type == 'film':
            generate_film_content_page(page_name, metas, content_md, index_entries, author)
        else:
            generate_tv_content_page(page_name, metas, content_md, index_entries, author)
    except Exception as e:
        print(f"Unexpected error while processing {content_type} content file {author} -- {metas[0]['git_path']}")
        raise e


def generate_film_content_page(page_name, metas, content_md, index_entries, author):
    ''' prints the md content page '''
    print(f"# {metas[0]['title']}", file=content_md)
    print("", file=content_md)
    img_idx = 0
    for meta in sorted(metas, key=lambda m: ', '.join(m.get('audioType', ''))):
        if 'pvaURL' not in meta and 'spectrumURL' not in meta:
            print(f"No charts found in {meta}")
        else:
            audio_type = meta.get('audioType', '')
            beq_catalogue_url = ''
            actual_img_links = []
            if 'pvaURL' in meta:
                actual_img_links.append(meta['pvaURL'])
            if 'spectrumURL' in meta:
                actual_img_links.append(meta['spectrumURL'])
            if audio_type:
                linked_content_format = ', '.join(audio_type)
                print(f"## {linked_content_format}", file=content_md)
                if 'edition' in meta:
                    print("", file=content_md)
                    print(meta['edition'], file=content_md)
                if 'altTitle' in meta and meta['altTitle'] != meta['title']:
                    print("", file=content_md)
                    print(meta['altTitle'], file=content_md)
                extra_meta = []
                if 'year' in meta:
                    extra_meta.append(meta['year'])
                if 'rating' in meta:
                    extra_meta.append(meta['rating'])
                if 'runtime' in meta:
                    extra_meta.append(f"{math.floor(int(meta['runtime']) / 60)}h {int(meta['runtime']) % 60}m")
                if 'language' in meta and meta['language'] != 'English':
                    extra_meta.append(meta['language'])
                if 'genres' in meta:
                    g = ', '.join(meta['genres'])
                    if g:
                        extra_meta.append(g)
                extra_meta.append(author)
                print('', file=content_md)
                e = ' \u2022 '.join(extra_meta)
                print(f"**{e}**", file=content_md)
                if 'overview' in meta:
                    print('', file=content_md)
                    print(meta['overview'], file=content_md)
                    print('{ data-search-exclude }', file=content_md)
                if 'gain' in meta:
                    print('', file=content_md)
                    print(f"**MV Adjustment:** {'+' if float(meta['gain']) > 0 else ''}{meta['gain']} dB",
                          file=content_md)
                if 'note' in meta:
                    print('', file=content_md)
                    print(meta['note'], file=content_md)
                    print('{ data-search-exclude }', file=content_md)
                if 'warning' in meta:
                    print('', file=content_md)
                    print(f"**{meta['warning']}**", file=content_md)
                    print('{ data-search-exclude }', file=content_md)
                links = []
                if 'avs' in meta:
                    links.append(f"[Discuss]({meta['avs']})")
                if 'theMovieDB' in meta:
                    tmdb_url = make_tmdb_url('film', parse.quote(meta['title']), meta['theMovieDB'])
                    links.append(f"[TMDB]({tmdb_url})")
                if links:
                    print('', file=content_md)
                    print('  '.join(links), file=content_md)
                    print('{ data-search-exclude }', file=content_md)
                if actual_img_links:
                    print('', file=content_md)
                for img in actual_img_links:
                    print(f"![img {img_idx}]({img})", file=content_md)
                    print('', file=content_md)
                    img_idx = img_idx + 1
                bd_url = generate_index_entry(author, page_name, linked_content_format, meta['title'],
                                              meta.get('year', ''), meta.get('avs', None), meta.get('theMovieDB', None),
                                              len(metas) > 1, index_entries)
                prefix = 'https://beqcatalogue.readthedocs.io/en/latest'
                beq_catalogue_url = f"{prefix}/{author}/{page_name}/#{slugify(linked_content_format, '-')}"
                cols = [
                    meta['title'],
                    meta.get('year', ''),
                    linked_content_format,
                    author,
                    meta.get('avs', ''),
                    beq_catalogue_url,
                    bd_url,
                    meta['filters']
                ]
                db_writer.writerow(cols + actual_img_links)
            else:
                print(f"No audioTypes in {metas[0]['title']}")
            add_to_catalogue({
                'title': meta['title'],
                'year': meta.get('year', ''),
                'audioTypes': meta.get('audioType', []),
                'content_type': 'film',
                'author': author,
                'catalogue_url': beq_catalogue_url,
                'filters': meta['jsonfilters'],
                'images': actual_img_links,
                'warning': meta.get('warning', ''),
                'mv': meta.get('gain', '0'),
                'avs': meta.get('avs', ''),
                'sortTitle': meta.get('sortTitle', ''),
                'edition': meta.get('edition', ''),
                'note': meta.get('note', ''),
                'language': meta.get('language', ''),
                'source': meta.get('source', ''),
                'overview': meta.get('overview', ''),
                'theMovieDB': meta.get('theMovieDB', ''),
                'rating': meta.get('rating', ''),
                'runtime': meta.get('runtime', '0'),
                'genres': meta.get('genres', []),
                'altTitle': meta.get('alt_title', ''),
                'collection': meta.get('collection', {}),
                'underlying': meta['file_name']
            }, meta['git_path'], author)
            generate_shake_eq(meta, author, page_name)


def generate_shake_eq(meta, author, page_name):
    pass


def format_season_episode(m) -> tuple[str, str, str, str]:
    long_season_episode = ''
    short_season_episode = ''
    season = ''
    episodes = ''
    if 'season' in m:
        season_meta = m['season']
        if isinstance(season_meta, str):
            season = season_meta
            long_season_episode = f"Season {season}"
            short_season_episode = f"S{season}"
            if 'episode' in m:
                episodes = m['episode']
                long_season_episode += f" Episode {episodes}"
                short_season_episode += f"E{episodes}"
        else:
            season = season_meta['number']
            long_season_episode = f"Season {season}"
            short_season_episode = f"S{season}"
            if not season_meta['complete']:
                episodes = season_meta['episodes']
                to_print = episodes
                s = ''
                if ',' in episodes:
                    epi_nums = [int(e) for e in episodes.split(',')]
                    if len(epi_nums) > 1:
                        ranges = []
                        for k, g in groupby(enumerate(epi_nums), lambda t: t[0] - t[1]):
                            group = list(map(itemgetter(1), g))
                            if group[0] == group[-1]:
                                ranges.append(f"{group[0]}")
                            else:
                                ranges.append(f"{group[0]}-{group[-1]}")
                        to_print = ', '.join(ranges)
                        s = 's'
                long_season_episode += f" Episode{s} {to_print}"
                short_season_episode += f"E{to_print}"
    return long_season_episode, short_season_episode, season, episodes


def generate_tv_content_page(page_name, metas, content_md, index_entries, author):
    ''' prints the md content page '''
    print(f"# {metas[0]['title']}", file=content_md)
    print("", file=content_md)
    print(f"* Author: {author}", file=content_md)
    img_idx = 0
    print("", file=content_md)

    def sort_meta(m):
        sort_key = ''
        if 'season' in m:
            season_meta = m['season']
            if isinstance(season_meta, str):
                sort_key = season_meta
                if 'episode' in m:
                    sort_key += m['episode']
            else:
                sort_key = season_meta['number']
                if not season_meta.get('complete', False):
                    sort_key += season_meta['episodes']
        return sort_key

    for meta in sorted(metas, key=sort_meta):
        audio_type = meta.get('audioType', '')
        linked_content_format = ''
        actual_img_links = []
        long_season, short_season, season, episodes = format_season_episode(meta)
        if 'pvaURL' in meta:
            actual_img_links.append(meta['pvaURL'])
        if 'spectrumURL' in meta:
            actual_img_links.append(meta['spectrumURL'])
        if long_season:
            print(f"## {long_season}", file=content_md)
            print("", file=content_md)
        if audio_type:
            linked_content_format = ', '.join(audio_type)
            print(f"* {linked_content_format}", file=content_md)
            print("", file=content_md)
        if 'gain' in meta:
            print('', file=content_md)
            print(f"**MV Adjustment:** {'+' if float(meta['gain']) > 0 else ''}{meta['gain']} dB",
                  file=content_md)
        if 'note' in meta:
            print('', file=content_md)
            print(meta['note'], file=content_md)
            print('{ data-search-exclude }', file=content_md)
        if 'warning' in meta:
            print('', file=content_md)
            print(f"**{meta['warning']}**", file=content_md)
            print('{ data-search-exclude }', file=content_md)
        if 'avs' in meta:
            print('', file=content_md)
            print(f"* [Forum Post]({meta['avs']})", file=content_md)
        if 'year' in meta:
            print('', file=content_md)
            print(f"* Production Year: {meta['year']}", file=content_md)
            print("", file=content_md)
        for img in actual_img_links:
            print('', file=content_md)
            print(f"![img {img_idx}]({img})", file=content_md)
            print('', file=content_md)

        extra_slug = f"#{slugify(long_season, '-')}" if long_season else ''
        bd_url = generate_index_entry(author, page_name, linked_content_format, f"{meta['title']} {short_season}",
                                      meta.get('year', ''), meta.get('avs', None), meta.get('theMovieDB', None),
                                      len(metas) > 1, index_entries, content_type='TV', extra_slug=extra_slug)
        prefix = 'https://beqcatalogue.readthedocs.io/en/latest'
        slugified_link = f"/{extra_slug}" if extra_slug else ''
        beq_catalogue_url = f"{prefix}/{author}/{page_name}{slugified_link}"
        cols = [
            meta['title'],
            meta.get('year', ''),
            linked_content_format,
            author,
            meta.get('avs', ''),
            beq_catalogue_url,
            bd_url,
            meta['filters']
        ]
        db_writer.writerow(cols + actual_img_links)

        # TODO remove once metadata is added
        if author == 'mobe1969' and len(actual_img_links) == 0:
            from urllib.parse import quote
            print(f"Generating img link for missing meta in {meta}")
            fp = meta['file_path'].replace('TV BEQs', 'TV Series')
            img = f"https://gitlab.com/Mobe1969/beq-reports/-/raw/master/{quote(fp)}/{quote(meta['file_name'])}.jpg"
            actual_img_links = [img]
            print(f"![img {img_idx}]({img})", file=content_md)
            print('', file=content_md)

        add_to_catalogue({
            'title': meta['title'],
            'year': meta.get('year', ''),
            'audioTypes': meta.get('audioType', []),
            'content_type': 'TV',
            'author': author,
            'catalogue_url': beq_catalogue_url,
            'filters': meta['jsonfilters'],
            'images': actual_img_links,
            'warning': meta.get('warning', ''),
            'season': season,
            'episode': episodes,
            'mv': meta.get('gain', '0'),
            'avs': meta.get('avs', ''),
            'sortTitle': meta.get('sortTitle', ''),
            'edition': meta.get('edition', ''),
            'note': meta.get('note', ''),
            'language': meta.get('language', ''),
            'source': meta.get('source', ''),
            'overview': meta.get('overview', ''),
            'theMovieDB': meta.get('theMovieDB', ''),
            'rating': meta.get('rating', ''),
            'genres': meta.get('genres', []),
            'underlying': meta['file_name']
        }, meta['git_path'], author)


def generate_index_entry(author, page_name, content_format, content_name, year, avs_url, tmdb_id, multiformat,
                         index_entries, content_type='film', extra_slug=None):
    ''' dumps the summary info to the index page '''
    escaped = parse.quote(content_name)
    tmdb_url = make_tmdb_url(content_type, escaped, tmdb_id)
    rt_url = f"https://www.rottentomatoes.com/search?search={escaped}"
    bd_url = f"https://www.blu-ray.com/movies/search.php?keyword={escaped}&submit=Search&action=search&"
    if content_type == 'film':
        extra_slug = f"#{slugify(content_format, '-')}" if multiformat is True else ''
    avs_link = f"[avsforum]({avs_url})" if avs_url else ''
    index_entries.append(
        f"| [{content_name}](./{author}/{page_name}.md{extra_slug}) | {content_type} | {year} | {content_format} | {'Yes' if multiformat else 'No'} | {avs_link} [blu-ray]({bd_url}) [themoviedb]({tmdb_url}) [rottentoms]({rt_url}) |")
    return bd_url


def make_tmdb_url(content_type, escaped, tmdb_id):
    tmdb_ct = 'movie' if content_type == 'film' else 'tv'
    tmdb = 'https://www.themoviedb.org'
    mdb_url = f"{tmdb}/search?query={escaped}" if not tmdb_id else f"{tmdb}/{tmdb_ct}/{tmdb_id}"
    return mdb_url


if os.getcwd() == os.path.dirname(os.path.abspath(__file__)):
    print(f"Switching CWD from {os.getcwd()}")
    os.chdir('..')
else:
    print(f"CWD: {os.getcwd()}")


def slice_dict(keys: list[str], d: dict) -> dict:
    return {k: d[k] for k in keys if k in d}


def detect_duplicate_hashes():
    hashes = defaultdict(list)
    slim_keys = ['title', 'author', 'underlying']

    for j in json_catalogue:
        hashes[j['digest']].append(slice_dict(slim_keys, j))

    unique_count = 0
    ignored_authors = ['mobe1969','aron7awol']
    for k, v in hashes.items():
        if len(v) > 1:
            formatted = set()
            for dupe in v:
                if dupe['author'] not in ignored_authors:
                    formatted.add(f"{dupe['author']}/{dupe['title']} - {dupe['underlying']}")
            if formatted:
                print(f"DUPLICATE HASH: {k} -> {len(v)}x {formatted}")
        unique_count += 1
    print(f"{unique_count} unique catalogue entries generated")


def load_times(author: str) -> dict[str, tuple[int, int]]:
    times = {}
    from csv import reader
    if os.path.isfile(f"meta/{author}.times.csv"):
        with open(f"meta/{author}.times.csv") as f:
            for row in reader(f):
                times[row[0]] = (int(row[1]), int(row[2]))
    return apply_times_diff(times, author)


def apply_times_diff(times: dict[str, tuple[int, int]], author: str) -> dict[str, tuple[int, int]]:
    from csv import reader
    if os.path.isfile(f"meta/{author}.diff"):
        with open(f"meta/{author}.diff") as f:
            for row in reader(f):
                if row[0] in times:
                    old = times[row[0]]
                    times[row[0]] = (old[0], int(row[1]))
                else:
                    times[row[0]] = (int(row[1]), int(row[1]))
    with open(f"meta/{author}.times.csv", mode="w") as f:
        from csv import writer
        w = writer(f)
        for k, v in times.items():
            vals = [k, str(v[0]), str(v[1])]
            w.writerow(vals)
    return times


def dump_audio_types(json_catalogue):
    audio_types = set()
    for c in json_catalogue:
        for at in c.get('audioTypes', []):
            audio_types.add(at)
    print(f"Found {len(audio_types)} audio types- {sorted(list(audio_types))}")


def dump_excess_files(pages_touched: list[str]):
    import glob
    existing_pages = sorted(glob.glob(f"docs/*/*.md", recursive=True))
    for page in sorted(pages_touched):
        try:
            existing_pages.remove(page)
        except ValueError:
            print(f'Touched a page but it does not exist! {page}')
    if existing_pages:
        to_delete = [p for p in existing_pages if not (p.startswith('docs/mobe1969/') or p.startswith('docs/aron7awol/'))]
        if to_delete:
            print(f'{len(to_delete)} files to delete')
            for p in to_delete:
                print(f'rm -f {p}')

def retrieve_retained_rows(retained_authors: list[str]) -> list[list[str]]:
    retained = []
    db_path = 'docs/database.csv'
    if os.path.exists(db_path):
        with open(db_path, newline='', encoding='utf-8') as f:
            reader = csv.reader(f)
            try:
                next(reader)
                for row in reader:
                    if len(row) > 3 and row[3] in retained_authors:
                        retained.append(row)
            except StopIteration:
                pass
    return retained


def retrieve_retained_catalogue(retained_authors: list[str]) -> list[dict]:
    retained = []
    db_path = 'docs/database.json'
    if os.path.exists(db_path):
        try:
            with open(db_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                if isinstance(data, list):
                    for entry in data:
                        if isinstance(entry, dict) and entry.get('author', '') in retained_authors:
                            retained.append(entry)
        except Exception:
            print(f"Failed to load retained entries from {db_path}")
            traceback.print_exc()
    return retained


if __name__ == '__main__':
    repo_configs = [
        ('halcyon888', '.input/halcyon888/miniDSPBEQ/', 'Movie BEQs', 'TV Shows BEQ'),
        ('t1g8rsfan', '.input/t1g8rsfan/miniDSPBEQ/', 'Movie BEQs', 'TV Shows BEQ'),
        ('kaelaria', '.input/kaelaria/Beq1/', 'movies', 'tv'),
        ('remixmark', '.input/remixmark/miniDSPBEQ/', 'Movie BEQs', 'TV BEQs'),
        ('mikejl', '.input/mikejl/xml/', 'Movies', 'TV'),
        # enable when metadata is added
        # ('bombaycat007', '.input/bombaycat007/miniDSPBEQ/', 'Movie BEQs', 'TV BEQs')
    ]

    all_authors = [a[0] for a in repo_configs]
    times = {a: load_times(a) for a in all_authors}
    error_files = {a: [] for a in all_authors}
    film_data = {}
    tv_data = {}

    for author, repo_path, film_sub, tv_sub in repo_configs:
        try:
            film_data[author] = extract_from_repo(repo_path, film_sub, 'film', author)
            print(f"Extracted {len(film_data[author])} {author} film catalogue entries")
            tv_data[author] = extract_from_repo(repo_path, tv_sub, 'TV', author)
            print(f"Extracted {len(tv_data[author])} {author} TV catalogue entries")
        except:
            print(f"Failed to extract for {author}")
            traceback.print_exc()

    retained_rows = retrieve_retained_rows(['aron7awol', 'mobe1969'])
    json_catalogue = retrieve_retained_catalogue(['aron7awol', 'mobe1969'])
    pages_touched: list[str] = []
    assumed_touched: set[str] = set()
    for e in json_catalogue:
        doc_page = f"docs/{e['catalogue_url'][46:]}"
        hash_idx = doc_page.find("/#")
        if hash_idx > -1:
            doc_page = doc_page[0:hash_idx]
        if doc_page[-1] == '/':
            doc_page = doc_page[0:-1]
        assumed_touched.add(f'{doc_page}.md')
    pages_touched.extend(assumed_touched)

    print(f"Retained {len(retained_rows)} csv entries, {len(json_catalogue)} json entries and {len(pages_touched)} touched pages")

    with open('docs/database.csv', 'w+', newline='') as db_csv:
        db_writer = csv.writer(db_csv)
        db_writer.writerow(['Title', 'Year', 'Format', 'Author', 'AVS', 'Catalogue', 'blu-ray.com', 'filters'])
        for r in retained_rows:
            db_writer.writerow(r)

        for author in all_authors:
            index_entries = []
            page_titles = process_content_from_repo(author, film_data[author], index_entries, 'film', pages_touched)
            if author in tv_data:
                process_content_from_repo(author, tv_data[author], index_entries, 'TV', pages_touched, created_titles=page_titles)
            with open(f'docs/{author}.md', mode='w+') as index_md:
                print('---', file=index_md)
                print('search:', file=index_md)
                print('  exclude: true', file=index_md)
                print('---', file=index_md)
                print('', file=index_md)
                print(f"# {author}", file=index_md)
                print('', file=index_md)
                print(f"| Title | Type | Year | Format | Multiformat? | Links |", file=index_md)
                print(f"|-|-|-|-|-|-|", file=index_md)
                for i in sorted(index_entries, key=str.casefold):
                    print(i, file=index_md)
                print('', file=index_md)

    for entry in json_catalogue:
        audio_types = cleanse_audio_types(entry['audioTypes'])
        entry['audioTypes'] = audio_types
        if audio_types:
            codec_channels = [parse_audio_format(at) for at in audio_types]
            entry['audioCodec'] = [a[0] for a in codec_channels]
            entry['audioChannelCounts'] = [a[1] for a in codec_channels]

    detect_duplicate_hashes()
    dump_audio_types(json_catalogue)
    dump_excess_files(pages_touched)

    for author, errors in error_files.items():
        with open(f'meta/{author}.errors', 'w') as f:
            for e in errors:
                f.write(f"{e}\n")

    with open('docs/database.json', 'w+') as db_json:
        json.dump(json_catalogue, db_json, indent=0)

    def txt(parent, title, text, **kwargs):
        e = ET.SubElement(parent, title, kwargs)
        e.text = text
        return e

    guids = set()

    ET.register_namespace('atom', 'http://www.w3.org/2005/Atom')
    rss_feed = ET.Element('rss', attrib={'xmlns:atom': 'http://www.w3.org/2005/Atom', 'version': '2.0'})
    channel = ET.SubElement(rss_feed, 'channel')
    txt(channel, 'title', 'BEQCatalogue')
    txt(channel, 'description', 'A RSS feed containing all BEQs created in the last 2 weeks')
    txt(channel, 'link', 'https://beqcatalogue.readthedocs.io/')
    txt(channel, 'language', 'en-gb')
    txt(channel, 'pubDate', formatdate())
    atom = ET.SubElement(channel, 'atom:link', href='https://beqcatalogue.readthedocs.io/en/latest/rss.xml', ref='self',
                         type='application/rss+xml')
    for fresh in sorted([c for c in json_catalogue if c.get('created_at', 0) >= TWO_WEEKS_AGO
                                                      or c.get('updated_at', 0) >= TWO_WEEKS_AGO],
                        key=lambda c: max(c.get('created_at', 0), c.get('updated_at', 0)), reverse=True):
        guid = fresh['digest']
        sz = len(guids)
        guids.add(guid)
        if len(guids) != sz:
            item = ET.SubElement(channel, 'item')
            txt(item, 'title', fresh['title'])
            txt(item, 'link', fresh['catalogue_url'])
            txt(item, 'description', fresh['overview'])
            txt(item, 'pubDate', formatdate(max(fresh.get('created_at', 0), fresh.get('updated_at', 0))))
            txt(item, 'category', fresh['content_type'])
            txt(item, 'category', fresh['author'])
            txt(item, 'guid', fresh['digest'], isPermaLink='false')
    tree = ET.ElementTree(rss_feed)
    tree.write("docs/rss/rss.xml", xml_declaration=True, encoding='utf-8')
