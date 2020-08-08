import csv
import re
from collections import OrderedDict

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


def extract_titles():
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
                    by_id[post_id] = name
    return by_id


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


posts = extract_titles()

print(f"Extracted {len(posts.keys())} catalogue entries")


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


with open('../tmp/errors.txt', mode='w+') as err:
    with open('../docs/index.md', mode='w+') as cat:
        with open('../docs/database.csv', 'w+', newline='') as db:
            db_writer = csv.writer(db)
            db_writer.writerow(['Title', 'Year', 'Format', 'AVS', 'Catalogue'])
            print('## Titles', file=cat)
            print('', file=cat)
            print(f"| Title | Year | Format | Discussion | |", file=cat)
            print(f"|-|-|-|-|-|", file=cat)

            for k, v in posts.items():
                post_id = f"post-{k}"
                url = f"https://www.avsforum.com/threads/bass-eq-for-filtered-movies.2995212/{post_id}"
                # print(f"{k} - {v} - {url}")

                html, should_cache = get_post(post_id, url)

                year = ''
                content_format = ''

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
                                print(f"# {v}", file=sub)
                                print("", file=sub)
                                print(f"[Discussion Post]({url})", file=sub)
                                print("", file=sub)
                                formatted = format_post_text(post_text)
                                if isinstance(formatted, tuple):
                                    year = formatted[1]
                                    content_format = formatted[2]
                                    print(f"* Year: {year}", file=sub)
                                    print(f"* Format: {content_format}", file=sub)
                                    print("", file=sub)
                                else:
                                    print(formatted, file=sub)
                                    print("", file=sub)
                                for idx, l in enumerate(links):
                                    print(f"![img {idx}]({l})", file=sub)
                                    print('', file=sub)
                            if len(links) != 2:
                                print(f"{url} - {v} - {len(links)}", file=err)
                    if not found:
                        print(f"Failed to find content in {url} for {v}")
                        print(f"| [{v}](./{k}.md) | [AVS Post]({url}) | **NO DATA** |", file=cat)
                        with open(f"../docs/{k}.md", mode='w+') as sub:
                            print(f"**NO CONTENT FOUND**", file=sub)
                    elif should_cache is True:
                        write_text(post_id, html)

                print(f"| [{v}](./{k}.md) | {year} | {content_format} | [AVS Post]({url}) | |", file=cat)
                db_writer.writerow([v, year, content_format, url, f"https://beqcatalogue.readthedocs.io/en/latest/{k}/"])

            print('', file=cat)
            print(f"## Offline Access", file=cat)
            print(f"Content is available in csv form via the [database](./database.csv)", file=cat)
