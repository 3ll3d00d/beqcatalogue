import csv
import re
from collections import OrderedDict
from datetime import datetime
from os import listdir
from os.path import isfile, join
from urllib import parse

import requests
from markdown.extensions.toc import slugify
from selectolax.parser import HTMLParser


def extract_mobe1969():
    root_path = '../../../../gitlab/Mobe1969/beq-reports'
    movie_path = f"{root_path}/Movies"
    movies = sorted([f for f in listdir(movie_path) if isfile(join(movie_path, f))])
    # name -> [year, content type, img url]
    metadata = OrderedDict()
    for m in movies:
        # name, year, content type
        match = re.match(r"(.*)\((\d{4})\)(.*)", m)
        if match:
            name = match.group(1).strip()
            t = match.group(3).strip()
            vals = [match.group(2), t[:-4], f"https://gitlab.com/Mobe1969/beq-reports/-/raw/master/Movies/{parse.quote(m)}"]
            if name in metadata:
                metadata[name].append(vals)
            else:
                metadata[name] = [vals]
        else:
            print(f"Ignoring file {m}")
    return metadata


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
    ''' extracts the content links from the 1st few posts of the avs thread '''
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


def extract_from_md_line(idx, trimmed):
    '''
    extracts the relevant info from the line of markdown
    :param idx:
    :param trimmed:
    :return:
    '''
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
        return post_id, name, release_date, tags
    else:
        print(f"Ignoring line {idx + 1} : {trimmed}")
        return None


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
        actual_date = extract_as_datetime(['%b%d-%Y', '%b-%d-%y', '%b-%d%Y', '%b-%d-%y', '%B%d-%y'], release_date)
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
    with open('../../beqwiki/BEQ-List.md') as f:
        for idx, l in enumerate(f.readlines()):
            trimmed = l.strip()
            if trimmed and trimmed[0] == '[':
                post_id, *vals = extract_from_md_line(idx, trimmed)
                if post_id:
                    by_id[post_id] = vals
    return by_id


def extract_aron7awol():
    try:
        return extract_from_md()
    except Exception as e:
        print(e)
        return extract_from_html()


def format_post_text(txt):
    ''' formats the basseq post header, assumes a specific format '''
    m = re.search(r".*B(?:ass|ASS)?EQ *([\w\s.:\-'\"’&,/!·()+]+) +\((\d{4})\)?(?: |\n)+(.*).*", txt)
    if m:
        name = m.group(1)
        year = m.group(2)
        format = m.group(3).replace('\u200b', '')
        return name, year, format
    else:
        m = re.search(r".*B(?:ass|ASS)?EQ *(.*)", txt)
        if m:
            return m.group(1)
        return txt


def get_post(post_id, url):
    ''' gets the post html from either the cache or from AVS directly. '''
    html = get_text(post_id)
    should_cache = False
    if html is None:
        r = requests.get(url)
        if r.status_code == 200:
            html = r.text
            should_cache = True
        else:
            print(f"Failed to get {url} - {r.status_code}")
    if should_cache:
        write_text(post_id, html)
    return html


def find_post_content(post_id, tree):
    '''
    extracts the img links out of a post.
    :param post_id: the post id.
    :param tree: the content tree.
    :return: all links, links inside a spoiler
    '''
    links_by_txt = OrderedDict()
    chunks = []
    post_matcher = f"article[data-content={post_id}] article[qid=\"post-text\"]"
    post_html = tree.css_first(post_matcher, strict=True).html
    post_node = HTMLParser(post_html)
    # have to parse this manually because node order is not preserved by this library
    # img_or_txt = f"b,img[data-src],div[class=\"bbMediaWrapper\"] a"
    # nodes = post_node.css(img_or_txt)
    # for node in nodes:
    for node in post_node.root.traverse(include_text=False):
        if node.tag == 'b':
            if not chunks or next((x for x in chunks[-1] if x[0:4] == 'IMG|'), None) is not None:
                chunks.append([node.text().strip()])
            else:
                chunks[-1].append(node.text().strip())
        elif node.tag == 'img' and 'data-src' in node.attributes:
            chunks[-1].append(f"IMG|{node.attributes['data-src']}")
        elif node.tag == 'a' and 'href' in node.attributes:
            href = node.attributes['href']
            if '%5B' in href and is_descendant_of(node.parent, lambda n: n and n.tag == 'div' and 'class' in n.attributes and n.attributes['class'] == 'bbMediaWrapper'):
                chunks[-1].append(f"IMG|{href[0:href.index('%5B')]}")

    for idx, chunk in enumerate(chunks):
        if len(chunk) < 2:
            print(f"Ignoring chunk {idx} in {post_id}")
        else:
            links_by_txt[chunk[0]] = chunk[1:]

    spoiler_links = [img.attributes['data-src'] for img in tree.css(f"article[data-content={post_id}] div[class=\"bbCodeSpoiler\"] img[data-src]")]
    return links_by_txt, spoiler_links


def is_descendant_of(node, predicate):
    '''
    :param node: the node to test
    :param predicate: the predicate to test
    :return: true if the node meets the predicate or its parent does.
    '''
    return predicate(node) or is_descendant_of(node.parent, predicate)


def process_aron7awol_content(post_id, content_meta, index_entries):
    post_id_suffix = f"post-{post_id}"
    url = f"https://www.avsforum.com/threads/bass-eq-for-filtered-movies.2995212/{post_id_suffix}"
    html = get_post(post_id_suffix, url)
    if isinstance(content_meta, list):
        content_name = content_meta[0]
        release_date = content_meta[1]
        content_format = content_meta[2]
    else:
        content_name = content_meta
        release_date = ''
        content_format = ''
    production_year = ''
    release_year = ''
    if release_date != '':
        release_year = datetime.strptime(release_date, '%Y-%m-%d').strftime('%Y')
    if html is not None:
        tree = HTMLParser(html)
        found = False
        if tree.body is not None:
            links_by_txt, spoiler_links = find_post_content(post_id_suffix, tree)
            if links_by_txt:
                found = True
                with open(f"../docs/aron7awol/{post_id}.md", mode='w+') as content_md:
                    generate_aron7awol_content_page(post_id, content_format, content_name, links_by_txt,
                                                    production_year, release_date, release_year, spoiler_links,
                                                    content_md, url, index_entries)
        if not found:
            print(f"Failed to find content in {url} for {content_name}")
            index_entries.append(f"| [{content_name}](./{post_id}.md) | | | | | [AVS Post]({url}) | | **NO DATA** |")
            with open(f"../docs/aron7awol/{post_id}.md", mode='w+') as content_md:
                print(f"**NO CONTENT FOUND**", file=content_md)


def generate_index_entry(author, page_name, content_format, content_name, production_year, release_date, release_year,
                         avs_url, multiformat, index_entries):
    ''' dumps the summary info to the index page '''
    escaped = parse.quote(content_name)
    # y:{year}
    mdb_url = f"https://www.themoviedb.org/search?query={escaped}"
    rt_url = f"https://www.rottentomatoes.com/search?search={escaped}"
    # &yearfrom={production_year}&yearto={production_year}
    # &releaseyear=2006
    release_filter = ''
    if release_year != '':
        release_filter = f"&releaseyear={release_year}"
    bd_url = f"https://www.blu-ray.com/movies/search.php?keyword={escaped}{release_filter}&submit=Search&action=search&"
    extra_slug = f"#{slugify(content_format, '-')}" if multiformat is True else ''
    index_entries.append(f"| [{content_name}](./{author}/{page_name}.md{extra_slug}) | {release_date} | {production_year} | {content_format} | {'Yes' if multiformat else 'No'} | {author} | [avsforum]({avs_url}) [blu-ray]({bd_url}) [themoviedb]({mdb_url}) [rottentoms]({rt_url}) |")
    return bd_url


def generate_aron7awol_content_page(post_id, content_format, content_name, links_by_text, production_year, release_date,
                                    release_year, spoiler_links, content_md, avs_post_url, index_entries):
    ''' prints the md content page '''
    print(f"# {content_name}", file=content_md)
    print("", file=content_md)
    print("* Author: aron7awol", file=content_md)
    print("", file=content_md)
    print(f"* [Forum Post]({avs_post_url})", file=content_md)
    print("", file=content_md)
    if release_date != '':
        print(f"* Release Date: {release_date}", file=content_md)
    first = True
    img_idx = 0
    is_multiformat = len([k for k in links_by_text.keys() if not k.startswith('Advanced Users Only')]) > 1
    for pt, image_links in links_by_text.items():
        actual_img_links = []
        linked_content_format = None
        if image_links:
            if first:
                formatted = format_post_text(pt)
                if isinstance(formatted, tuple):
                    if content_format != formatted[2]:
                        print(f"FORMAT,{content_name},{content_format},{formatted[2]}", file=delta)
                    content_format = formatted[2]
                    if release_year != '' and release_year != formatted[1]:
                        print(f"DATE,{content_name},{release_year},{formatted[1]}", file=delta)
                    production_year = formatted[1]
                    print(f"* Production Year: {production_year}", file=content_md)
                    print('', file=content_md)
                    print(f"## {content_format}", file=content_md)
                    print('', file=content_md)

                else:
                    print(f"* Production Year: {production_year}", file=content_md)
                    print('', file=content_md)
                    print(f"## {content_format}", file=content_md)
                    print(formatted, file=content_md)
                    print('', file=content_md)
                print(f"{content_name},{content_format}", file=link_titles)
                linked_content_format = content_format
            else:
                pt = pt if pt[-1] != ':' else pt[0:-1]
                print(f"## {pt}", file=content_md)
                print('', file=content_md)
                print(f"{content_name},{pt}", file=link_titles)
                linked_content_format = pt
            i = 0
            for l in image_links:
                if len(l) >= 4 and l[0:4] == 'IMG|':
                    print(f"![img {i + img_idx}]({l[4:]})", file=content_md)
                    print('', file=content_md)
                    i += 1
                    actual_img_links.append(l[4:])
                else:
                    print(f"Ignoring post content {avs_post_url} - {l}")
            img_idx += i
            if i > 2:
                print(f"{avs_post_url} - {content_name} - {i}", file=excess)
            if spoiler_links:
                print(f"{avs_post_url} - {content_name} - {len(spoiler_links)}", file=spoilers)
        first = False
        # special case for Arrival
        if not linked_content_format.startswith('Advanced Users Only'):
            bd_url = generate_index_entry('aron7awol', post_id, linked_content_format, content_name, production_year, release_date,
                                          release_year, avs_post_url, is_multiformat, index_entries)
            db_writer.writerow([content_name, release_date, production_year, linked_content_format, 'aron7awol', avs_post_url,
                                f"https://beqcatalogue.readthedocs.io/en/latest/aron7awol/{post_id}/#{slugify(linked_content_format, '-')}", bd_url] + actual_img_links)


def process_mobe1969_content(content_name, content_meta, index_entries):
    page_name = slugify(content_name, '-')
    with open(f"../docs/mobe1969/{page_name}.md", mode='w+') as content_md:
        generate_mobe1969_content_page(page_name, content_name, content_meta, index_entries, content_md)


def generate_mobe1969_content_page(page_name, content_name, content_meta, index_entries, content_md):
    '''
    Creates a content page for an entry in Mobe1969's repo.
    :param content_name:
    :param content_meta:
    :param index_entries:
    :param content_md:
    '''
    print(f"# {content_name}", file=content_md)
    print("", file=content_md)
    print("* Author: mobe1969", file=content_md)
    print("", file=content_md)
    for meta in content_meta:
        print(f"## {meta[1]}", file=content_md)
        print('', file=content_md)
        print(f"* Release Date: {meta[0]}", file=content_md)
        print('', file=content_md)
        print(f"![img0]({meta[2]})", file=content_md)
        print('', file=content_md)
        bd_url = generate_index_entry('mobe1969', page_name, meta[1], content_name, meta[0], meta[0],
                                      meta[0], None, len(content_meta) > 1, index_entries)
        db_writer.writerow([content_name, meta[0], meta[0], meta[1], 'mobe1969', None,
                            f"https://beqcatalogue.readthedocs.io/en/latest/mobe1969/{page_name}/#{slugify(meta[1], '-')}",
                            bd_url, meta[2]])


if __name__ == '__main__':
    aron7awol_posts = extract_aron7awol()
    print(f"Extracted {len(aron7awol_posts.keys())} aron7awol catalogue entries")
    mobe1969_files = extract_mobe1969()
    print(f"Extracted {len(mobe1969_files.keys())} mobe1969 catalogue entries")
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

    with open('../tmp/spoilers.txt', mode='w+') as spoilers:
        with open('../tmp/delta.txt', mode='w+') as delta:
            with open('../tmp/link_titles.txt', mode='w+') as link_titles:
                with open('../tmp/excess.txt', mode='w+') as excess:
                    with open('../docs/index.md', mode='w+') as index_md:
                        with open('../docs/database.csv', 'w+', newline='') as db_csv:
                            db_writer = csv.writer(db_csv)
                            db_writer.writerow(['Title', 'Release Date', 'Production Year', 'Format', 'Author', 'AVS', 'Catalogue', 'blu-ray.com'])
                            print(f"| Title | Release Date | Production Year | Format | Multiformat? | Author | Links |", file=index_md)
                            print(f"|-|-|-|-|-|-|-|", file=index_md)
                            index_entries = []
                            for post_id, content_meta in aron7awol_posts.items():
                                process_aron7awol_content(post_id, content_meta, index_entries)

                            for content_name, content_meta in mobe1969_files.items():
                                process_mobe1969_content(content_name, content_meta, index_entries)

                            for i in sorted(index_entries, key=str.casefold):
                                print(i, file=index_md)
                            print('', file=index_md)
