import csv
from datetime import datetime
import re
from collections import OrderedDict
from urllib import parse

import requests
from selectolax.parser import HTMLParser


def get_text(p_id):
    try:
        with open(f"../tmp/{p_id}.html") as f:
            return f.read()
    except:
        return None


def write_text(p_id, txt):
    with open(f"../tmp/{p_id}.html", mode='w') as f:
        f.write(txt)


def extract_from_html():
    ignored = ['Take the Red Pill (BassEQ)', 'BassEQ Demo Clips', 'TR Curves']
    by_id = OrderedDict()
    first_page = get_text('first')
    if first_page is None:
        r = requests.get('https://www.avsforum.com/threads/bass-eq-for-filtered-movies.2995212')
        if r.status_code == 200:
            first_page = r.text
            write_text('first', first_page)
        else:
            print(f"Failed to get first page - {r.status_code}")
            exit(1)
    tree = HTMLParser(first_page)
    if tree.body is not None:
        for href in tree.css('a[href]'):
            link = href.attributes['href']
            if link.startswith('https://xenforo.local.svc.cluster.local'):
                post_id = [l for l in link.split('/') if l][-1]
                name = href.child.text()
                if 'xenforo.local' not in name and name not in ignored:
                    by_id[post_id] = name.strip()
    return by_id

def scrub_links(txt):
    ''' scrub additional MD links from the text '''
    match = re.search(r"(.*)\[([\w\s\d.:\-'\"’&,/!·•+()\[\]]+)]\((?:https://.*)\)", txt)
    if match:
        return match.group(1)
    return txt


def extract_from_md_line(by_id, idx, trimmed):
    match = re.search(r"^\[([\w\s\d.:\-'\"’&,/!·•+()]+)]\((?:https://[\w\d./\-\.?=#]+post-)(\d+)( \".*\")?\)", trimmed)
    if match:
        name, post_id, extras = match.groups()
        extra_fragment = scrub_links(trimmed[match.span(3 if extras else 2)[1] + 1:].strip())
        release_date = ''
        match = re.search(r"^.*(?:\((.*)\))+.*", extra_fragment)
        if match:
            release_date = cleanse_release_date(idx, match, trimmed)
            tags_fragment = extra_fragment[0:match.span(1)[0]-1].strip()
        else:
            tags_fragment = extra_fragment
        tags = ''
        match = re.search(r"^([\w\s\d\-/\.:()+]+)", tags_fragment)
        if match:
            tags = match.group(1)
        # if not release_date and not tags:
        #     print(f"Missing extra info at line {idx + 1} [{name}] | {extra_fragment}")
        # elif not release_date:
        #     print(f"Missing release_date at line {idx + 1} [{name}] | {extra_fragment}")
        if not tags:
            print(f"Missing tags at line {idx + 1} [{name}] | {extra_fragment}")
        by_id[post_id] = (name, release_date, tags)
    else:
        print(f"Ignoring line {idx + 1} : {trimmed}")


def cleanse_release_date(idx, match, trimmed):
    log_suffix = f"{idx + 1}: {trimmed}"
    # use - as the only delimiter
    release_date = match.group(1).replace('.', '-').replace(' ', '-').replace('/', '-').replace(',', '-').replace('--', '-')
    # remove cruft
    previous_rd = release_date
    release_date = release_date.replace(')', '')
    if len(release_date) != len(previous_rd):
        print(f"Junk text in trimmed from release date '{previous_rd}' {log_suffix}")
    # fix typos
    release_date = release_date.replace('Sept', 'Sep').replace('Setp', 'Sep').replace('Mat', 'May')
    # remove question marks
    match = re.match(r"(\?+[-/])(\d{4})", release_date)
    if match:
        print(f"Redundant text trimmed from release date {log_suffix}")
        release_date = match.group(2)
    # parse
    actual_date = extract_as_datetime(['%b-%d-%Y', '%B-%d-%Y', '%b-%Y', '%B-%Y', '%Y'], release_date)
    if not actual_date:
        actual_date = extract_as_datetime(['%b%d-%Y', '%b-%d-%y', '%b-%d%Y'], release_date)
        if actual_date:
            print(f"Non standard date format {release_date} {log_suffix}")
    if not actual_date:
        print(f"Incompatible date format {release_date} {log_suffix}")
        return ''
    else:
        if actual_date.year < 1100:
            actual_date = actual_date.replace(actual_date.year + 1000)
            print(f"Year typo {release_date} {log_suffix}")
        return actual_date.strftime('%Y-%m-%d')


def extract_as_datetime(formats, release_date):
    actual_date = None
    for f in formats:
        try:
            actual_date = datetime.strptime(release_date, f)
        except:
            pass
    return actual_date


def extract_from_md():
    by_id = OrderedDict()
    with open('../../../bmiller/miniDSPBEQ.wiki/BEQ-List.md') as f:
        for idx, l in enumerate(f.readlines()):
            trimmed = l.strip()
            if trimmed and trimmed[0] == '[':
                for f in fix_formatting(idx, trimmed):
                    extract_from_md_line(by_id, idx, f)
    return by_id


def fix_formatting(idx, trimmed):
    if idx == 91:
        return (
            '[Assimilate](https://www.avsforum.com/threads/bass-eq-for-filtered-movies.2995212/post-58501200 "AVS Forum | Home Theater Discussions And Reviews - Post 58501200") BD/DTS-HD MA 5.1 (July 23/2019)',
        )
    elif idx == 97:
        return (
            '[The Avengers](https://www.avsforum.com/threads/bass-eq-for-filtered-movies.2995212/post-56612552 "AVS Forum | Home Theater Discussions And Reviews - Post 56612552") 4K/UHD/ATMOS (Aug.14/2018)',
            '[The Avengers](https://www.avsforum.com/threads/bass-eq-for-filtered-movies.2995212/post-57968986 "AVS Forum | Home Theater Discussions And Reviews - Post 57968986") BD/DTS-HD MA 7.1 (Aug.14/2018)'
        )
    elif idx == 250:
        return (
            '[Crank](https://www.avsforum.com/threads/bass-eq-for-filtered-movies.2995212/post-58041054 "AVS Forum | Home Theater Discussions And Reviews - Post 58041054") 4K/UHD/ATMOS (May 21/2019)',
            '[Crank](https://www.avsforum.com/threads/bass-eq-for-filtered-movies.2995212/post-57968136 "AVS Forum | Home Theater Discussions And Reviews - Post 57968136") BD/LPCM 5.1 (May 21/2019)'        )
    elif idx == 502:
        return (
            '[Hellboy II: The Golden Army](https://www.avsforum.com/threads/bass-eq-for-filtered-movies.2995212/post-58021942 "AVS Forum | Home Theater Discussions And Reviews - Post 58021942") 4K/UHD/DTS:X (May 7/2019)',
            '[Hellboy II: The Golden Army](https://www.avsforum.com/threads/bass-eq-for-filtered-movies.2995212/post-57965174 "AVS Forum | Home Theater Discussions And Reviews - Post 57965174") BD/DTS-HD MA 7.1 (May 7/2019)'        )
    elif idx == 523:
        return (
            '[Hot Fuzz](https://www.avsforum.com/threads/bass-eq-for-filtered-movies.2995212/post-58526692 "AVS Forum | Home Theater Discussions And Reviews - Post 58526692") 4K/UHD/DTS:X (Sept.10/2019)',
            '[Hot Fuzz](https://www.avsforum.com/threads/bass-eq-for-filtered-movies.2995212/post-58015214 "AVS Forum | Home Theater Discussions And Reviews - Post 58015214") BD/DTS-HD MA 5.1 (June 25/2013)'
        )
    elif idx == 646:
        return (
            '[Jurassic Park](https://www.avsforum.com/threads/bass-eq-for-filtered-movies.2995212/post-56894464 "AVS Forum | Home Theater Discussions And Reviews - Post 56894464") 4K/UHD/DTS:X (May22/2018)',
            '[Jurassic Park](https://www.avsforum.com/threads/bass-eq-for-filtered-movies.2995212/post-57964114 "AVS Forum | Home Theater Discussions And Reviews - Post 57964114") BD/DTS-HD MA 7.1 (May22/2018)'        )
    elif idx == 1039:
        return (
            '[Shaun of the Dead](https://www.avsforum.com/threads/bass-eq-for-filtered-movies.2995212/post-58526330 "AVS Forum | Home Theater Discussions And Reviews - Post 58526330") 4K/UHD/DTS:X (Sept.10/2019)',
            '[Shaun of the Dead](https://www.avsforum.com/threads/bass-eq-for-filtered-movies.2995212/post-58013966 "AVS Forum | Home Theater Discussions And Reviews - Post 58013966") BD/DTS-HD MA 5.1 (Sept.22/2009)'
        )
    elif idx == 1088:
        return (
            '[Spies in Disguise](https://www.avsforum.com/threads/bass-eq-for-filtered-movies.2995212/post-59312546 "AVS Forum | Home Theater Discussions And Reviews - Post 59312546") 4K/UHD/ATMOS (Mar.10/2020)',
        )
    elif idx == 1245:
        return (
            '[The Wave](https://www.avsforum.com/threads/bass-eq-for-filtered-movies.2995212/post-57481870 "AVS Forum | Home Theater Discussions And Reviews - Post 57481870") BD/ATMOS (2016)',
        )
    elif idx == 1268:
        return (
            '[The Worlds End](https://www.avsforum.com/threads/bass-eq-for-filtered-movies.2995212/post-58526424 "AVS Forum | Home Theater Discussions And Reviews - Post 58526424") 4K/UHD/DTS:X (Sept.10/2019)',
            '[The Worlds End](https://www.avsforum.com/threads/bass-eq-for-filtered-movies.2995212/post-58015350 "AVS Forum | Home Theater Discussions And Reviews - Post 58015350") BD/DTS-HD MA 5.1 (Nov.19/2013)'
        )
    return trimmed,


def extract_titles():
    try:
        return extract_from_md()
    except Exception as e:
        print(e)
        return extract_from_html()


def format_post_text(pt):
    txt = [p.text().strip() for p in pt if p.text().strip()]
    for t in txt:
        m = re.search(r".*B(?:ass|ASS)?EQ *([\w\s.:\-'\"’&,/!·()+]+) +\((\d{4})\)?(?: |\n)+(.*).*", t)
        if m:
            name = m.group(1)
            year = m.group(2)
            format = m.group(3).replace('\u200b', '')
            return name, year, format
    txt = [t.replace('BEQ', '').replace('BassEQ', '').replace('BASSEQ', '').replace('&#8203;', '') for t in txt]
    return '\n'.join(txt)


def get_post(post_id, url):
    html = get_text(post_id)
    should_cache = False
    if html is None:
        r = requests.get(url)
        if r.status_code == 200:
            html = r.text
            should_cache = True
        else:
            print(f"Failed to get {url} - {r.status_code}")
    return html, should_cache


posts = extract_titles()
# posts = extract_from_html()
# p2 = extract_from_md()
#
# for k,v in p2.items():
#     if k not in posts:
#         print(f"Missing from html {k} -> {v}")
# for k,v in posts.items():
#     if k not in p2:
#         print(f"Missing from md {k} -> {v}")
#
# exit(1)
print(f"Extracted {len(posts.keys())} catalogue entries")


with open('../tmp/delta.txt', mode='w+') as delta:
    with open('../tmp/errors.txt', mode='w+') as err:
        with open('../docs/index.md', mode='w+') as cat:
            with open('../docs/database.csv', 'w+', newline='') as db:
                db_writer = csv.writer(db)
                db_writer.writerow(['Title', 'Release Date', 'Production Year', 'Format', 'AVS', 'Catalogue', 'blu-ray.com'])
                print(f"| Title | Release Date | Production Year | Format | Discussion | Lookup | Notes |", file=cat)
                print(f"|-|-|-|-|-|-|-|", file=cat)

                for k, v in posts.items():
                    post_id = f"post-{k}"
                    url = f"https://www.avsforum.com/threads/bass-eq-for-filtered-movies.2995212/{post_id}"

                    html, should_cache = get_post(post_id, url)
                    if isinstance(v, tuple):
                        content_name = v[0]
                        release_date = v[1]
                        content_format = v[2]
                    else:
                        content_name = v
                        release_date = ''
                        content_format = ''
                    production_year = ''
                    release_year = ''
                    bd_url = ''
                    if release_date != '':
                        release_year = datetime.strptime(release_date, '%Y-%m-%d').strftime('%Y')

                    if html is not None:
                        tree = HTMLParser(html)
                        found = False
                        if tree.body is not None:
                            imgs = tree.css(f"article[data-content={post_id}] img[data-src]")
                            links = [img.attributes['data-src'] for img in imgs]
                            if links:
                                found = True
                                post_text = tree.css(f"article[data-content={post_id}] article[qid=\"post-text\"] div[class=\"bbWrapper\"]")
                                with open(f"../docs/{k}.md", mode='w+') as sub:
                                    print(f"# {content_name}", file=sub)
                                    print("", file=sub)
                                    print(f"[Discussion Post]({url})", file=sub)
                                    print("", file=sub)
                                    if release_date != '':
                                        print(f"* Release Date: {release_date}", file=sub)
                                    formatted = format_post_text(post_text)
                                    if isinstance(formatted, tuple):
                                        if content_format == '':
                                            content_format = formatted[2]
                                        if content_format != formatted[2]:
                                            print(f"{content_name},{content_format},{formatted[2]}", file=delta)
                                        if release_year != '' and release_year != formatted[1]:
                                            print(f"{content_name},{release_year},{formatted[1]}", file=delta)
                                        production_year = formatted[1]
                                        print(f"* Production Year: {production_year}", file=sub)
                                        print(f"* Format: {content_format}", file=sub)
                                        print("", file=sub)
                                    else:
                                        print(f"* Production Year: {production_year}", file=sub)
                                        print(f"* Format: {content_format}", file=sub)
                                        print(formatted, file=sub)
                                        print("", file=sub)
                                    for idx, l in enumerate(links):
                                        print(f"![img {idx}]({l})", file=sub)
                                        print('', file=sub)
                                if len(links) != 2:
                                    print(f"{url} - {content_name} - {len(links)}", file=err)
                                query = content_name
                                escaped = parse.quote(query)
                                # y:{year}
                                mdb_url = f"https://www.themoviedb.org/search?query={escaped}"
                                rt_url = f"https://www.rottentomatoes.com/search?search={escaped}"
                                # &yearfrom={production_year}&yearto={production_year}
                                # &releaseyear=2006
                                release_filter = ''
                                if release_year != '':
                                    release_filter = f"&releaseyear={release_year}"
                                bd_url = f"https://www.blu-ray.com/movies/search.php?keyword={escaped}{release_filter}&submit=Search&action=search&"
                                print(f"| [{content_name}](./{k}.md) | {release_date} | {production_year} | {content_format} | [avsforum]({url}) | [blu-ray]({bd_url}) [themoviedb]({mdb_url}) [rottentoms]({rt_url}) | |",
                                      file=cat)
                        if not found:
                            print(f"Failed to find content in {url} for {content_name}")
                            print(f"| [{content_name}](./{k}.md) | | | | [AVS Post]({url}) | | **NO DATA** |", file=cat)
                            with open(f"../docs/{k}.md", mode='w+') as sub:
                                print(f"**NO CONTENT FOUND**", file=sub)
                        elif should_cache is True:
                            write_text(post_id, html)

                    db_writer.writerow([content_name, release_date, production_year, content_format, url, f"https://beqcatalogue.readthedocs.io/en/latest/{k}/", bd_url])

                print('', file=cat)
