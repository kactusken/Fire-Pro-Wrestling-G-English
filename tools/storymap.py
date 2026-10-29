#!/usr/bin/env python3
"""Fighting Road's route data for the guide's route map (docs/guide/, tools/guidedata.py).

Runs the branch analysis in storyflow.py, adds scene titles and summaries from
docs/story_titles.csv and assigns each scene to its route.
"""
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


def page_data(titles_path=paths.repo(os.path.join(paths.DOCS, "story_titles.csv"))):
    """The route map's data: storyflow.build() with each scene's route, title and summary."""
    d = storyflow.build()
    scenes = d["scenes"]
    route = routes(scenes)
    names = titles(titles_path)
    for s in scenes:
        s["route"] = route.get(s["id"], "Demo")
        s["title"], s["summary"] = names.get(s["id"], (s["first"][:40], ""))
        for e in s["effects"]:
            e.pop("context", None)
    missing = [s["id"] for s in scenes if s["id"] not in names]
    if missing:
        print(f"warning: no title for scenes {missing}")
    return d
