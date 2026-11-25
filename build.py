#!/usr/bin/env python3
"""Builds the Sileo / Zebra source into ./site from the .debs in ./debs.

Run by the Publish workflow on every change to main. Usage: build.py <base URL ending in />
"""
import bz2
import gzip
import hashlib
import lzma
import os
import shutil
import subprocess
import sys
from email.utils import formatdate

ROOT = os.path.dirname(os.path.abspath(__file__))
SITE = os.path.join(ROOT, "site")
BASE_URL = sys.argv[1] if len(sys.argv) > 1 else ""


def add_icons(packages):
    """Adds an Icon: field to each package that has icons/<package id>.png, so Sileo shows it."""
    if not BASE_URL:
        return packages
    stanzas = []
    for stanza in packages.strip().split("\n\n"):
        fields = stanza.split("\n")
        package = next((f.split(":", 1)[1].strip() for f in fields if f.startswith("Package:")), None)
        has_icon = any(f.startswith("Icon:") for f in fields)
        if package and not has_icon and os.path.exists(os.path.join(ROOT, "icons", package + ".png")):
            fields.append("Icon: %sicons/%s.png" % (BASE_URL, package))
        stanzas.append("\n".join(fields))
    return "\n\n".join(stanzas) + "\n"


def main():
    shutil.rmtree(SITE, ignore_errors=True)
    os.makedirs(SITE)
    for name in ("debs", "icons"):
        if os.path.isdir(os.path.join(ROOT, name)):
            shutil.copytree(os.path.join(ROOT, name), os.path.join(SITE, name))
    for name in ("index.html", "CydiaIcon.png"):
        if os.path.exists(os.path.join(ROOT, name)):
            shutil.copy2(os.path.join(ROOT, name), SITE)

    # The package index: one entry per .deb, read from its control file (-m keeps older versions too).
    packages = subprocess.run(["dpkg-scanpackages", "-m", "debs", "/dev/null"], cwd=SITE,
                              check=True, capture_output=True, text=True).stdout
    if not packages.strip():
        sys.exit("No .deb files found in debs/")
    data = add_icons(packages).encode()
    files = {
        "Packages": data,
        "Packages.bz2": bz2.compress(data, 9),
        "Packages.gz": gzip.compress(data, 9, mtime=0),
        "Packages.xz": lzma.compress(data),
    }
    for name, blob in files.items():
        with open(os.path.join(SITE, name), "wb") as f:
            f.write(blob)

    # Release: the source's name and description from ./Release, plus checksums of the index.
    with open(os.path.join(ROOT, "Release")) as f:
        lines = [line for line in f.read().strip().split("\n") if not line.startswith("Date:")]
    lines.append("Date: " + formatdate(usegmt=True))
    for title, algorithm in (("MD5Sum", "md5"), ("SHA256", "sha256")):
        lines.append(title + ":")
        for name, blob in files.items():
            lines.append(" %s %d %s" % (hashlib.new(algorithm, blob).hexdigest(), len(blob), name))
    with open(os.path.join(SITE, "Release"), "w") as f:
        f.write("\n".join(lines) + "\n")

    count = data.decode().count("\nPackage: ") + data.decode().startswith("Package: ")
    print("Built the source: %d package version(s)" % count)


if __name__ == "__main__":
    main()
