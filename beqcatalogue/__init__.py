import csv
import os
from urllib import parse

from markdown.extensions.toc import slugify


def extract_from_repo(path):
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
                <beq_poster>/usfcQZRqdXTSSQ55esiPHJZKkIU.jpg</beq_poster>
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
    :return:
    '''
    import xml.etree.ElementTree as ET
    import glob
    elements = []
    for xml in glob.glob(f"{path}/**/*.xml", recursive=True):
        et_tree = ET.parse(str(xml))
        root = et_tree.getroot()
        meta = {'repo_file': str(xml)}
        for child in root:
            if child.tag == 'beq_metadata':
                for m in child:
                    if len(m) == 0:
                        txt = m.text
                        if txt:
                            meta[m.tag[4:]] = m.text
                    elif m.tag == 'beq_audioTypes':
                        audio_types = [c.text.strip() for c in m]
                        meta['audioType'] = [at for at in audio_types if at]
        if len(meta.keys()) > 0:
            elements.append(meta)
    return elements


def process_mobe1969_content_from_repo(content_meta, index_entries):
    ''' converts beq_metadata into md '''
    by_title = {}
    for meta in content_meta:
        if 'title' in meta:
            title = meta['title']
            if title in by_title:
                by_title[title].append(meta)
            else:
                by_title[title] = [meta]
        else:
            print(f"Missing title entry for {meta['repo_file']}")
    for title, metas in by_title.items():
        if len(metas) > 2:
            print(f"Multi meta in {title}")
        title_md = slugify(title, '-')
        with open(f"docs/mobe1969/{title_md}.md", mode='w+') as content_md:
            generate_content_page(title_md, metas, content_md, index_entries, 'mobe1969')


def process_aron7awol_content_from_repo(content_meta, index_entries):
    ''' converts beq_metadata into md '''
    by_post_id = {}
    for meta in content_meta:
        if 'avs' in meta:
            avs = meta['avs']
            idx = avs.find('post?id=')
            avs_post_id = None
            if idx == -1:
                idx = avs.find('post-')
                if idx == -1:
                    print(f"Unparsable post id {meta['repo_file']} - {avs}")
                else:
                    avs_post_id = avs[idx + 5:]
            else:
                avs_post_id = avs[idx + 8:]
            if avs_post_id:
                if avs_post_id in by_post_id:
                    by_post_id[avs_post_id].append(meta)
                else:
                    by_post_id[avs_post_id] = [meta]
        else:
            print(f"Missing beq_avs entry for {meta['repo_file']}")
    for post_id, metas in by_post_id.items():
        if len(metas) > 2:
            print(f"Multi meta in post {post_id} - {metas[0]['title']}")
        with open(f"docs/aron7awol/{post_id}.md", mode='w+') as content_md:
            generate_content_page(post_id, metas, content_md, index_entries, 'aron7awol')


def generate_content_page(page_name, metas, content_md, index_entries, author):
    ''' prints the md content page '''
    print(f"# {metas[0]['title']}", file=content_md)
    print("", file=content_md)
    print(f"* Author: {author}", file=content_md)
    if 'avs' in metas[0]:
        print(f"* [Forum Post]({metas[0]['avs']})", file=content_md)
    production_years = {m['year'] for m in metas}
    img_idx = 0
    if len(production_years) == 1:
        print(f"* Production Year: {production_years.pop()}", file=content_md)
    print("", file=content_md)
    for meta in metas:
        if 'pvaURL' not in meta and 'spectrumURL' not in meta:
            print(f"No charts found in {meta}")
        else:
            linked_content_format = ', '.join(meta['audioType'])
            print(f"## {linked_content_format}", file=content_md)
            print("", file=content_md)
            if production_years:
                print(f"* Production Year: {meta['year']}", file=content_md)
                print("", file=content_md)
            actual_img_links = []
            if 'pvaURL' in meta:
                print(f"![img {img_idx}]({meta['pvaURL']})", file=content_md)
                print('', file=content_md)
                actual_img_links.append(meta['pvaURL'])
                img_idx = img_idx + 1
            if 'spectrumURL' in meta:
                print(f"![img {img_idx}]({meta['spectrumURL']})", file=content_md)
                print('', file=content_md)
                actual_img_links.append(meta['spectrumURL'])
                img_idx = img_idx + 1

            bd_url = generate_index_entry(author, page_name, linked_content_format, meta['title'], meta['year'],
                                          meta.get('avs', None), len(metas) > 1, index_entries)
            db_writer.writerow([meta['title'], meta['year'], linked_content_format, author, meta.get('avs', ''),
                                f"https://beqcatalogue.readthedocs.io/en/latest/{author}/{page_name}/#{slugify(linked_content_format, '-')}", bd_url] + actual_img_links)


def generate_index_entry(author, page_name, content_format, content_name, year, avs_url, multiformat, index_entries):
    ''' dumps the summary info to the index page '''
    escaped = parse.quote(content_name)
    mdb_url = f"https://www.themoviedb.org/search?query={escaped}"
    rt_url = f"https://www.rottentomatoes.com/search?search={escaped}"
    bd_url = f"https://www.blu-ray.com/movies/search.php?keyword={escaped}&submit=Search&action=search&"
    extra_slug = f"#{slugify(content_format, '-')}" if multiformat is True else ''
    avs_link = f"[avsforum]({avs_url})" if avs_url else ''
    index_entries.append(f"| [{content_name}](./{author}/{page_name}.md{extra_slug}) | {year} | {content_format} | {'Yes' if multiformat else 'No'} | {avs_link} [blu-ray]({bd_url}) [themoviedb]({mdb_url}) [rottentoms]({rt_url}) |")
    return bd_url


if os.getcwd() == os.path.dirname(os.path.abspath(__file__)):
    print(f"Switching CWD from {os.getcwd()}")
    os.chdir('..')
else:
    print(f"CWD: {os.getcwd()}")


if __name__ == '__main__':
    aron7awol = extract_from_repo('.input/bmiller/miniDSPBEQ/Movie BEQs')
    print(f"Extracted {len(aron7awol)} aron7awol catalogue entries")

    mobe1969 = extract_from_repo('.input/Mobe1969/miniDSPBEQ/Movie BEQs')
    print(f"Extracted {len(mobe1969)} mobe1969 catalogue entries")

    with open('docs/database.csv', 'w+', newline='') as db_csv:
        db_writer = csv.writer(db_csv)
        db_writer.writerow(['Title', 'Year', 'Format', 'Author', 'AVS', 'Catalogue', 'blu-ray.com'])
        index_entries = []
        process_aron7awol_content_from_repo(aron7awol, index_entries)
        with open('docs/aron7awol.md', mode='w+') as index_md:
            print(f"# aron7awol", file=index_md)
            print('', file=index_md)
            print(f"| Title | Year | Format | Multiformat? | Links |", file=index_md)
            print(f"|-|-|-|-|-|", file=index_md)
            for i in sorted(index_entries, key=str.casefold):
                print(i, file=index_md)

        with open('docs/mobe1969.md', mode='w+') as index_md:
            print(f"# Mobe1969", file=index_md)
            print('', file=index_md)
            print(f"| Title | Year | Format | Multiformat? | Links |", file=index_md)
            print(f"|-|-|-|-|-|", file=index_md)
            index_entries = []
            process_mobe1969_content_from_repo(mobe1969, index_entries)
            for i in sorted(index_entries, key=str.casefold):
                print(i, file=index_md)
            print('', file=index_md)
