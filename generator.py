#!/usr/bin/env python3

import sys
import argparse
import tempfile
import re

import requests as req, zipfile, io, markdown2 as md, sqlite3, os, shutil, tarfile

p = argparse.ArgumentParser()
p.add_argument('--url', '-u')
p.add_argument('--dir', '-d')
args = p.parse_args()

if not any((args.url, args.dir)):
    sys.stderr.write('Please specify either -u or -d\n')
    sys.exit(1)

html_tmpl = """<html><head><meta charset="UTF8"><link rel="stylesheet" type="text/css" href="../style.css"/></head><body><section id="tldr"><div id="page">%content%</div></section></body></html>"""

doc_source         = "https://github.com/tldr-pages/tldr/archive/master.zip"
docset_path        = "tldrpages.docset"
doc_path_contents  = docset_path + "/Contents/"
doc_path_resources = docset_path + "/Contents/Resources/"
doc_path           = docset_path + "/Contents/Resources/Documents/"
doc_pref           = "tldr-master/pages"

if os.path.exists(doc_path):
    try: shutil.rmtree(doc_path)
    except OSError as e:
        print("Could not delete dirs " + e.strerror)
        raise SystemExit
os.makedirs(doc_path)

cleanup = None

def get_doc_zip():
    if args.url:
        try: r = req.get(doc_source)
        except req.exceptions.ConnectionError:
            print("Could not load tldr-pages from " + doc_source)
            raise SystemExit
        if r.status_code != 200:
            print("Could not load tldr-pages.")
            raise SystemExit
        ret = r.content
        r.close()
        return ret
    elif args.dir:
        if not os.path.isdir(args.dir):
            sys.stderr.write("Not a directory: %s" % args.dir)
            sys.exit(1)
        zip_out = tempfile.mktemp('.zip')
        global doc_pref
        dirpath = os.path.expanduser(args.dir)
        if not os.path.isdir(dirpath):
            sys.stderr.write("Not a directory: {}".format(dirpath))
            sys.exit(1)
        doc_pref = 'pages/'
        os.system('cd {}; zip --exclude "*.git*" -r {} .'.format(dirpath, zip_out))
        with open(zip_out, 'rb') as f:
            ret = f.read()
        def cleanup_zip():
            os.unlink(zip_out)

        global cleanup
        cleanup = cleanup_zip
        return ret
    else:
        sys.exit(1)


db = sqlite3.connect(doc_path_resources+"/"+"docSet.dsidx")
cur = db.cursor()

try: cur.execute('DROP TABLE searchIndex;')
except: pass
cur.execute('CREATE TABLE searchIndex(id INTEGER PRIMARY KEY, name TEXT, type TEXT, path TEXT);')
cur.execute('CREATE UNIQUE INDEX anchor ON searchIndex (name, type, path);')

# Generate tldr pages to HTML documents
markdowner = md.Markdown()
with zipfile.ZipFile(io.BytesIO(get_doc_zip()), "r") as archive:
    for path in archive.namelist():
        if path.startswith(doc_pref) and path.endswith(".md"):
            sys.stderr.write('Compiling: {}\n'.format(path))
            cmd_name = path[path.rfind("/")+1:-3]
            sub_dir = path[len(doc_pref.rstrip('/'))+1:path.rfind("/")]
            sub_path = os.path.join(doc_path, sub_dir)
            if not os.path.exists(sub_path):
                try: os.makedirs(sub_path)
                except OSError as e:
                    print("Could not create dir {}: {}".format(sub_path, e.strerror))
                    raise SystemExit

            if sub_dir != "common":
                cur.execute('INSERT OR IGNORE INTO searchIndex(name, type, path) VALUES (?,?,?)', (sub_dir + " " + cmd_name, 'Command', sub_dir+'/'+cmd_name+".html"))
            else:
                cur.execute('INSERT OR IGNORE INTO searchIndex(name, type, path) VALUES (?,?,?)', (cmd_name, 'Command', sub_dir+'/'+cmd_name+".html"))
            doc = markdowner.convert(archive.read(path))
            doc = re.sub(r'{{(.*?)}}', r'<em>\1</em>', doc)
            doc = html_tmpl.replace("%content%", doc)
            with open(os.path.join(doc_path, path[len(doc_pref.rstrip('/'))+1:].replace(".md", ".html")), "wb") as html:
                html.write(doc.encode("utf-8"))
db.commit()
db.close()

# Generate tldr pages index.html
with open(os.path.join(doc_path, "index.html"), "w+") as html:
    html.write('<html><head></head><body><h1>TLDR pages Docset</h1><br/>powered by <a href="http://tldr-pages.github.io">tldr-pages.github.io/</a>')
    for dir in os.listdir(doc_path):
        if os.path.isdir(os.path.join(doc_path, dir)):
            html.write("<h2>%s</h2><ul>" % dir)
            html.writelines(['<li><a href="%s/%s">%s</a></li>' % (dir, f, f[:-5]) for f in os.listdir(os.path.join(doc_path, dir))])
            html.write("</ul>")
    html.write('</body></html>')


# copy static content
shutil.copyfile("static/style.css", doc_path+"/style.css")
shutil.copyfile("static/Info.plist", doc_path_contents+"/Info.plist")
shutil.copyfile("static/icon.png", docset_path+"/icon.png")
shutil.copyfile("static/icon@2x.png", docset_path+"/icon@2x.png")

# create tgz
with tarfile.open("tldr_pages.tgz", "w") as docset:
    docset.add(docset_path)

if cleanup:
    cleanup()
