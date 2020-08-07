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


posts = OrderedDict()
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
            if 'xenforo.local' not in name:
                posts[post_id] = name

print(f"Extracted {len(posts.keys())} catalogue entries")

with open('../docs/catalogue.md', mode='w+') as cat:
    for k, v in posts.items():
        post_id = f"post-{k}"
        url = f"https://www.avsforum.com/threads/bass-eq-for-filtered-movies.2995212/{post_id}"
        # print(f"{k} - {v} - {url}")

        html = get_text(post_id)
        should_cache = False
        if html is None:
            r = requests.get(url)
            if r.status_code == 200:
                html = r.text
                should_cache = True
            else:
                print(f"Failed to get {url} - {r.status_code}")

        if html is not None:
            tree = HTMLParser(html)
            found = False
            if tree.body is not None:
                imgs = tree.css(f"article[data-content={post_id}] img[data-src]")
                links = [img.attributes['data-src'] for img in imgs]
                if links:
                    found = True
                    print(f"* [{v}](./{k}.md)", file=cat)
                    with open(f"../docs/{k}.md", mode='w+') as sub:
                        print(f"# {v}", file=sub)
                        print("", file=sub)
                        for idx, l in enumerate(links):
                            print(f"![img {idx}]({l})", file=sub)
                            print('', file=sub)
            if not found:
                print(f"Failed to find content in {url}")
            elif should_cache is True:
                write_text(post_id, html)
