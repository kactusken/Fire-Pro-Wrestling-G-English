#!/usr/bin/env python3
"""Build the standalone story route map (docs/route-map/index.html).

Runs the branch analysis in storyflow.py, adds scene titles and summaries from
docs/story_titles.csv and assigns each scene to its route, then embeds the data
in tools/storymap_template.html. The page needs internet access only for the
dagre layout library (cdnjs) and Google Fonts.

Usage: storymap.py [--out PATH] [--titles PATH] [--template PATH]
                   [--extracted PATH] [--script PATH] [--text PATH]
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import paths  # noqa: E402
import storyflow  # noqa: E402
import table  # noqa: E402

# first scene of each route (scene 3 offers); 0-3 are the prologue
ROUTE_STARTS = {"NJPW": 4, "AJPW": 95, "FMW": 158, "UWF": 249, "America": 397, "Michinoku": 458}
DEMO = (520, 521)  # title-screen demo only


def titles(path=paths.repo(os.path.join(paths.DOCS, "story_titles.csv"))):
    out = {}
    for f in table.read(path):
        out[int(f[0])] = (f[1].strip(), f[2].strip() if len(f) > 2 else "")
    return out


def routes(scenes):
    route = {s: "Prologue" for s in range(4)}
    for name, start in ROUTE_STARTS.items():
        todo = [start]
        while todo:
            s = todo.pop()
            if s in route:
                continue
            route[s] = name
            todo += [e["to"] for e in scenes[s]["exits"] if e["to"] is not None]
    for s in DEMO:
        route[s] = "Demo"
    return route


def main(argv=None):
    ap = argparse.ArgumentParser(description="Build the standalone story route map page.")
    paths.add(ap, "--out", os.path.join(paths.DOCS, "route-map", "index.html"), "output page")
    paths.add(ap, "--titles", os.path.join(paths.DOCS, "story_titles.csv"), "scene titles and summaries")
    paths.add(ap, "--template", os.path.join("tools", "storymap_template.html"), "page template")
    storyflow.add_options(ap)
    args = ap.parse_args(argv)
    storyflow.configure(args.extracted, args.script, args.text)
    out_path = args.out
    d = storyflow.build()
    scenes = d["scenes"]
    route = routes(scenes)
    names = titles(args.titles)
    for s in scenes:
        s["route"] = route.get(s["id"], "Demo")
        s["title"], s["summary"] = names.get(s["id"], (s["first"][:40], ""))
        for e in s["effects"]:
            e.pop("context", None)
    missing = [s["id"] for s in scenes if s["id"] not in names]
    if missing:
        print(f"warning: no title for scenes {missing}")
    data = json.dumps(d, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    html = open(args.template, encoding="utf-8").read().replace("/*DATA*/", data)
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", encoding="utf-8", newline="\n") as f:
        f.write(html)
    print(f"{len(scenes)} scenes -> {out_path} ({len(html) // 1024} KB)")


if __name__ == "__main__":
    main()
