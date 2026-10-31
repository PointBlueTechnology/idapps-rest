#!/usr/bin/env python3
"""Write docs/endpoints.md: every operation in a system's /idmappsdoc/openapi.json, with where it lives and whether
these notes have validated it. Only methods and paths are taken from the reference, never its text.

    curl -sk https://<apps host>/idmappsdoc/openapi.json -o /tmp/openapi.json
    python3 tools/endpoints.py /tmp/openapi.json > docs/endpoints.md
"""
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

BASES = {"Access": "/IDMProv/rest/access", "Catalog": "/IDMProv/rest/catalog", "Admin": "/IDMProv/rest/admin"}

# validated calls: (method, base + path) -> the section of README.md that describes them
VALIDATED = {
    ("POST", "/IDMProv/rest/access/tasks"): "23-approve-deny-and-more",
    ("POST", "/IDMProv/rest/access/tasks/v2"): "23-approve-deny-and-more",
    ("GET", "/IDMProv/rest/access/tasks/list"): "21-list-my-tasks-get-accesstaskslist",
    ("POST", "/IDMProv/rest/access/tasks/item"): "22-one-task-post-accesstasksitem",
    ("GET", "/IDMProv/rest/access/tasks/badge"): "24-around-tasks",
    ("GET", "/IDMProv/rest/access/tasks/list/others"): "24-around-tasks",
    ("GET", "/IDMProv/rest/access/tasks/workEntries"): "24-around-tasks",
    ("POST", "/IDMProv/rest/access/requests/permissions/v2"): "31-start-a-prd-with-a-json-request-form-post-accessrequestspermissionsv2",
    ("POST", "/IDMProv/rest/access/requests/permissions/item"): "32-request-a-role-or-a-resource-post-accessrequestspermissionsitem",
    ("GET", "/IDMProv/rest/access/requests/historylist"): "34-history",
    ("POST", "/IDMProv/rest/access/requests/history/item"): "34-history",
    ("GET", "/IDMProv/rest/access/requests/processes"): "34-history",
    ("DELETE", "/IDMProv/rest/access/requests/history"): "35-retract-a-request-delete-accessrequestshistory",
    ("POST", "/IDMProv/rest/access/assignments/list"): "41-a-persons-roles-and-resources",
    ("POST", "/IDMProv/rest/access/assignments/role/list"): "41-a-persons-roles-and-resources",
    ("POST", "/IDMProv/rest/access/assignments/resource/list"): "41-a-persons-roles-and-resources",
    ("POST", "/IDMProv/rest/access/assignments/list/v2"): "41-a-persons-roles-and-resources",
    ("GET", "/IDMProv/rest/access/assignments"): "41-a-persons-roles-and-resources",
    ("GET", "/IDMProv/rest/access/assignments/advanced"): "41-a-persons-roles-and-resources",
    ("POST", "/IDMProv/rest/access/assignments/item"): "41-a-persons-roles-and-resources",
    ("GET", "/IDMProv/rest/access/assignments/identities"): "42-who-has-a-role-or-a-resource",
    ("POST", "/IDMProv/rest/catalog/roles/role/assignments"): "42-who-has-a-role-or-a-resource",
    ("POST", "/IDMProv/rest/catalog/resources/resource/assignments"): "42-who-has-a-role-or-a-resource",
    ("DELETE", "/IDMProv/rest/access/assignments/list"): "43-revoke-delete-accessassignmentslist",
    ("GET", "/IDMProv/rest/catalog/roles/listV2"): "51-search",
    ("GET", "/IDMProv/rest/catalog/resources/listV2"): "51-search",
    ("GET", "/IDMProv/rest/catalog/roles"): "51-search",
    ("GET", "/IDMProv/rest/catalog/resources"): "51-search",
    ("GET", "/IDMProv/rest/catalog/prds"): "51-search",
    ("GET", "/IDMProv/rest/catalog/roles/levels"): "51-search",
    ("POST", "/IDMProv/rest/catalog/roles"): "52-roles-create-read-change-delete",
    ("POST", "/IDMProv/rest/catalog/roles/role"): "52-roles-create-read-change-delete",
    ("PUT", "/IDMProv/rest/catalog/roles/role"): "52-roles-create-read-change-delete",
    ("DELETE", "/IDMProv/rest/catalog/roles/role"): "52-roles-create-read-change-delete",
    ("GET", "/IDMProv/rest/catalog/users"): "53-users",
    ("GET", "/IDMProv/rest/access/users/list"): "53-users",
    ("GET", "/IDMProv/rest/access/users/details"): "53-users",
    ("GET", "/IDMProv/rest/catalog/sods"): "6-other-reads",
    ("GET", "/IDMProv/rest/access/sods/violations"): "6-other-reads",
    ("GET", "/IDMProv/rest/access/sods/violations/user"): "6-other-reads",
    ("GET", "/IDMProv/rest/access/delegation"): "6-other-reads",
    ("GET", "/IDMProv/rest/access/proxy/all"): "6-other-reads",
    ("GET", "/IDMProv/rest/access/proxy/for"): "6-other-reads",
    ("GET", "/IDMProv/rest/access/availability"): "6-other-reads",
    ("POST", "/IDMProv/rest/access/permissions/item"): "7-the-permission-index-and-the-caches",
    ("POST", "/IDMProv/rest/access/index/permissions"): "7-the-permission-index-and-the-caches",
    ("GET", "/IDMProv/rest/admin/cache/holders"): "7-the-permission-index-and-the-caches",
    ("DELETE", "/IDMProv/rest/admin/cache/holder/items"): "7-the-permission-index-and-the-caches",
}
# called on a lab and did not work, or answered nothing useful
NOT_WORKING = {
    ("GET", "/IDMProv/rest/access/tasks/historyList"): "database error every time",
    ("GET", "/IDMProv/rest/access/permissions"): "answered empty every time; use the catalog's listV2",
}


def findings():
    """(method, path) -> (group, finding) from data/<group>.json, as written up in docs/reference/<group>.md."""
    out = {}
    for f in sorted(os.listdir(os.path.join(ROOT, "data"))):
        if f.endswith(".json"):
            for x in json.load(open(os.path.join(ROOT, "data", f))):
                out[(x["method"], x["path"])] = (f[:-5], x)
    return out


def anchor(m, path):
    return re.sub(r"[^a-z0-9]+", "-", f"{m} {path}".lower()).strip("-")


LABEL = {"validated": "tested, works", "empty-on-lab": "tested (no data on the test system)",
         "from-ui": "not tested: from inspection", "not-working": "tested, does not work", "unknown": "not known yet"}


def main(path):
    d = json.load(open(path))
    F = findings()
    rows = []
    for p, ops in d["paths"].items():
        for m, op in ops.items():
            if m not in ("get", "post", "put", "delete", "patch"):
                continue
            tag = (op.get("tags") or ["?"])[0]
            full = BASES.get(tag, "?") + p
            rows.append((tag, p.strip("/").split("/")[0], m.upper(), full))
    version = d.get("info", {}).get("version", "?")
    def status(key):
        if key in VALIDATED:
            return "validated", f"tested, works: [README](../README.md#{VALIDATED[key]})"
        if key in NOT_WORKING:
            return "not-working", f"tested, does not work ({NOT_WORKING[key]})"
        if key in F:
            g, x = F[key]
            return x["status"], f"{LABEL.get(x['status'], x['status'])}: [{g}](reference/{g}.md#{anchor(*key)})"
        return "none", "_not checked yet_"
    st = [status((r[2], r[3]))[0] for r in rows]
    ok = st.count("validated")
    bad = st.count("not-working")
    seen = st.count("empty-on-lab")
    code = st.count("from-ui") + st.count("unknown")
    out = ["# Every endpoint", "",
           f"All {len(rows)} operations of the Identity Applications REST API reference (version {version}), with the base each one",
           "lives under and whether it was tested. Generated by `tools/endpoints.py` from a system's",
           "`/idmappsdoc/openapi.json`; only methods and paths are taken from it.", "",
           f"- **Tested, works:** {ok}.",
           f"- **Tested, but the test system had no data to show:** {seen}.",
           f"- **Not tested, described from inspection:** {code}: calls whose preconditions the test system",
           "  could not meet (see its notes).",
           f"- **Tested, does not work:** {bad}.",
           f"- **Not checked yet:** {len(rows) - ok - bad - seen - code}.", "",
           "Each status links to the operation's section: the README for the first calls written up, and the pages under",
           "[reference/](reference/) for the rest. The server also answers routes the reference leaves out; they are in",
           "[Not in the reference](reference/unlisted.md).", ""]
    for tag in ("Access", "Catalog", "Admin"):
        out += [f"## {tag}: `{BASES[tag]}`", ""]
        area = None
        for t, a, m, full in sorted((r for r in rows if r[0] == tag), key=lambda r: (r[1].lower(), r[3], r[2])):
            if a != area:
                out += ["", f"### /{a}", "", "| Method | Path | Status |", "|---|---|---|"]
                area = a
            out.append(f"| {m} | `{full}` | {status((m, full))[1]} |")
        out.append("")
    print("\n".join(out))


if __name__ == "__main__":
    main(sys.argv[1])
