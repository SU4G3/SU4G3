#!/usr/bin/env python3
"""Renders assets/stats.svg and assets/langs.svg in the profile's glass style.

Reads public data through the GitHub GraphQL API (GITHUB_TOKEN, USERNAME).
Runs daily from .github/workflows/stats.yml, so the cards never depend on a
third-party image service being up.
"""
import json
import os
import pathlib
import urllib.request
from html import escape

USER = os.environ.get("USERNAME", "SU4G3")
TOKEN = os.environ["GITHUB_TOKEN"]
ASSETS = pathlib.Path(__file__).resolve().parent.parent / "assets"

QUERY = """
query($login: String!, $after: String) {
  user(login: $login) {
    contributionsCollection { totalCommitContributions restrictedContributionsCount }
    pullRequests { totalCount }
    issues { totalCount }
    repositoriesContributedTo(contributionTypes: [COMMIT, PULL_REQUEST, ISSUE]) { totalCount }
    repositories(first: 100, after: $after, ownerAffiliations: OWNER, privacy: PUBLIC) {
      pageInfo { hasNextPage endCursor }
      nodes {
        stargazerCount
        isFork
        languages(first: 20, orderBy: {field: SIZE, direction: DESC}) {
          edges { size node { name color } }
        }
      }
    }
  }
}
"""

W, H = 590, 200
STYLE = (
    "text{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Helvetica,Arial,sans-serif}"
    ".t{fill:#fff;font-size:18px;font-weight:600}.k{fill:#fff;fill-opacity:.62;font-size:14px}"
    ".v{fill:#fff;font-size:14px;font-weight:600}"
)
DEFS = """<defs>
<pattern id="dots" width="22" height="22" patternUnits="userSpaceOnUse"><circle cx="11" cy="11" r="1.3" fill="#fff" fill-opacity=".16"/></pattern>
<radialGradient id="vignette" cx=".5" cy=".5" r=".75"><stop offset="0" stop-color="#1c1c22"/><stop offset="1" stop-color="#0b0b0e"/></radialGradient>
<linearGradient id="shine" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#fff" stop-opacity=".08"/><stop offset="1" stop-color="#fff" stop-opacity="0"/></linearGradient>
<clipPath id="outer"><rect width="{w}" height="{h}" rx="22"/></clipPath>
</defs>"""


def graphql(after=None):
    body = json.dumps({"query": QUERY, "variables": {"login": USER, "after": after}}).encode()
    req = urllib.request.Request(
        "https://api.github.com/graphql",
        data=body,
        headers={"Authorization": f"bearer {TOKEN}", "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = json.load(resp)
    if "errors" in data:
        raise SystemExit(f"GraphQL errors: {data['errors']}")
    return data["data"]["user"]


def fetch():
    user = graphql()
    repos = list(user["repositories"]["nodes"])
    page = user["repositories"]["pageInfo"]
    while page["hasNextPage"]:
        more = graphql(page["endCursor"])["repositories"]
        repos += more["nodes"]
        page = more["pageInfo"]
    langs = {}
    # Forks count for languages only once they have stars of their own (a maintained
    # fork such as OpSec-Enhanced), not a fork made to send one pull request upstream.
    for repo in repos:
        if repo["isFork"] and not repo["stargazerCount"]:
            continue
        for edge in repo["languages"]["edges"]:
            name = edge["node"]["name"]
            size, color = langs.get(name, (0, edge["node"]["color"] or "#8b8b94"))
            langs[name] = (size + edge["size"], color)
    c = user["contributionsCollection"]
    return {
        "stars": sum(r["stargazerCount"] for r in repos),
        "commits": c["totalCommitContributions"] + c["restrictedContributionsCount"],
        "prs": user["pullRequests"]["totalCount"],
        "issues": user["issues"]["totalCount"],
        "contributed": user["repositoriesContributedTo"]["totalCount"],
    }, sorted(langs.items(), key=lambda kv: -kv[1][0])[:6]


def card(title, inner):
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}">'
        f"<style>{STYLE}</style>{DEFS.format(w=W, h=H)}"
        f'<g clip-path="url(#outer)"><rect width="{W}" height="{H}" fill="url(#vignette)"/>'
        f'<rect width="{W}" height="{H}" fill="url(#dots)"/>'
        f'<rect width="{W}" height="{H * 0.45}" fill="url(#shine)"/>'
        f'<rect x=".5" y=".5" width="{W - 1}" height="{H - 1}" rx="22" fill="none" stroke="#fff" stroke-opacity=".14"/>'
        f'<text class="t" x="28" y="42">{escape(title)}</text>{inner}</g></svg>\n'
    )


def stats_svg(s):
    rows = [
        ("Total stars", s["stars"]),
        ("Commits this year", s["commits"]),
        ("Pull requests", s["prs"]),
        ("Issues", s["issues"]),
        ("Contributed to", s["contributed"]),
    ]
    inner = ""
    for i, (key, value) in enumerate(rows):
        y = 76 + i * 25
        inner += f'<text class="k" x="28" y="{y}">{key}</text>'
        inner += f'<text class="v" x="{W - 28}" y="{y}" text-anchor="end">{value:,}</text>'
    return card(f"{USER}'s GitHub stats", inner)


def langs_svg(langs):
    total = sum(size for _, (size, _) in langs) or 1
    bar_w, x = W - 56, 28.0
    inner = '<clipPath id="bar"><rect x="28" y="62" width="%d" height="10" rx="5"/></clipPath><g clip-path="url(#bar)">' % bar_w
    for _, (size, color) in langs:
        w = bar_w * size / total
        inner += f'<rect x="{x:.1f}" y="62" width="{w + 0.5:.1f}" height="10" fill="{color}"/>'
        x += w
    inner += "</g>"
    for i, (name, (size, color)) in enumerate(langs):
        cx = 28 + (i % 2) * (W - 56) / 2
        cy = 104 + (i // 2) * 30
        inner += f'<circle cx="{cx + 6}" cy="{cy - 5}" r="6" fill="{color}"/>'
        inner += f'<text class="v" x="{cx + 20}" y="{cy}">{escape(name)}</text>'
        inner += f'<text class="k" x="{cx + (W - 56) / 2 - 16}" y="{cy}" text-anchor="end">{100 * size / total:.1f}%</text>'
    return card("Most used languages", inner)


def main():
    stats, langs = fetch()
    ASSETS.mkdir(exist_ok=True)
    (ASSETS / "stats.svg").write_text(stats_svg(stats))
    (ASSETS / "langs.svg").write_text(langs_svg(langs))
    print(json.dumps(stats), [name for name, _ in langs])


if __name__ == "__main__":
    main()
