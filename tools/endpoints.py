#!/usr/bin/env python3
"""Write docs/endpoints.md: every operation in a system's /idmappsdoc/openapi.json, with where it lives and whether
these notes have validated it. Only methods and paths are taken from the reference, never its text.

    curl -sk https://<apps host>/idmappsdoc/openapi.json -o /tmp/openapi.json
    python3 tools/endpoints.py /tmp/openapi.json > docs/endpoints.md
"""
import json
import sys

BASES = {"Access": "/IDMProv/rest/access", "Catalog": "/IDMProv/rest/catalog", "Admin": "/IDMProv/rest/admin"}

# validated calls: (method, base + path) -> the section of README.md that describes them
VALIDATED = {
    ("POST", "/IDMProv/rest/access/tasks"): "23-approve-deny-and-more",
    ("POST", "/IDMProv/rest/access/tasks/v2"): "23-approve-deny-and-more",
    ("GET", "/IDMProv/rest/access/tasks/list"): "21-list-my-tasks-get-accesstaskslist-live",
    ("POST", "/IDMProv/rest/access/tasks/item"): "22-one-task-post-accesstasksitem-live",
    ("GET", "/IDMProv/rest/access/tasks/badge"): "24-around-tasks-live",
    ("GET", "/IDMProv/rest/access/tasks/list/others"): "24-around-tasks-live",
    ("GET", "/IDMProv/rest/access/tasks/workEntries"): "24-around-tasks-live",
    ("POST", "/IDMProv/rest/access/requests/permissions/v2"): "31-start-a-prd-with-a-json-request-form-post-accessrequestspermissionsv2-live",
    ("POST", "/IDMProv/rest/access/requests/permissions/item"): "32-request-a-role-or-a-resource-post-accessrequestspermissionsitem-live",
    ("GET", "/IDMProv/rest/access/requests/historylist"): "34-history-live",
    ("POST", "/IDMProv/rest/access/requests/history/item"): "34-history-live",
    ("GET", "/IDMProv/rest/access/requests/processes"): "34-history-live",
    ("DELETE", "/IDMProv/rest/access/requests/history"): "35-retract-a-request-delete-accessrequestshistory-live",
    ("POST", "/IDMProv/rest/access/assignments/list"): "41-a-persons-roles-and-resources-live",
    ("POST", "/IDMProv/rest/access/assignments/role/list"): "41-a-persons-roles-and-resources-live",
    ("POST", "/IDMProv/rest/access/assignments/resource/list"): "41-a-persons-roles-and-resources-live",
    ("POST", "/IDMProv/rest/access/assignments/list/v2"): "41-a-persons-roles-and-resources-live",
    ("GET", "/IDMProv/rest/access/assignments"): "41-a-persons-roles-and-resources-live",
    ("GET", "/IDMProv/rest/access/assignments/advanced"): "41-a-persons-roles-and-resources-live",
    ("POST", "/IDMProv/rest/access/assignments/item"): "41-a-persons-roles-and-resources-live",
    ("GET", "/IDMProv/rest/access/assignments/identities"): "42-who-has-a-role-or-a-resource-live",
    ("POST", "/IDMProv/rest/catalog/roles/role/assignments"): "42-who-has-a-role-or-a-resource-live",
    ("POST", "/IDMProv/rest/catalog/resources/resource/assignments"): "42-who-has-a-role-or-a-resource-live",
    ("DELETE", "/IDMProv/rest/access/assignments/list"): "43-revoke-delete-accessassignmentslist-live",
    ("GET", "/IDMProv/rest/catalog/roles/listV2"): "51-search-live",
    ("GET", "/IDMProv/rest/catalog/resources/listV2"): "51-search-live",
    ("GET", "/IDMProv/rest/catalog/roles"): "51-search-live",
    ("GET", "/IDMProv/rest/catalog/resources"): "51-search-live",
    ("GET", "/IDMProv/rest/catalog/prds"): "51-search-live",
    ("GET", "/IDMProv/rest/catalog/roles/levels"): "51-search-live",
    ("POST", "/IDMProv/rest/catalog/roles"): "52-roles-create-read-change-delete-live",
    ("POST", "/IDMProv/rest/catalog/roles/role"): "52-roles-create-read-change-delete-live",
    ("PUT", "/IDMProv/rest/catalog/roles/role"): "52-roles-create-read-change-delete-live",
    ("DELETE", "/IDMProv/rest/catalog/roles/role"): "52-roles-create-read-change-delete-live",
    ("GET", "/IDMProv/rest/catalog/users"): "53-users-live",
    ("GET", "/IDMProv/rest/access/users/list"): "53-users-live",
    ("GET", "/IDMProv/rest/access/users/details"): "53-users-live",
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
    ("POST", "/IDMProv/rest/access/requests/historylist/permission"): "always asked for the permission id",
    ("GET", "/IDMProv/rest/access/permissions"): "answered empty every time; use the catalog's listV2",
}


def main(path):
    d = json.load(open(path))
    rows = []
    for p, ops in d["paths"].items():
        for m, op in ops.items():
            if m not in ("get", "post", "put", "delete", "patch"):
                continue
            tag = (op.get("tags") or ["?"])[0]
            full = BASES.get(tag, "?") + p
            rows.append((tag, p.strip("/").split("/")[0], m.upper(), full))
    version = d.get("info", {}).get("version", "?")
    ok = sum(1 for r in rows if (r[2], r[3]) in VALIDATED)
    bad = sum(1 for r in rows if (r[2], r[3]) in NOT_WORKING)
    out = ["# Every endpoint", "",
           f"All {len(rows)} operations of the Identity Applications REST API reference (version {version}), with the base each one",
           "lives under and how far these notes have got with it. Generated by `tools/endpoints.py` from a system's",
           "`/idmappsdoc/openapi.json`; only methods and paths are taken from it.", "",
           f"- **Validated:** {ok}, each linked to its section of the [README](../README.md).",
           f"- **Did not work on the lab:** {bad} (see [§10](../README.md#10-not-working-or-not-checked)).",
           f"- **Not validated yet:** {len(rows) - ok - bad}. These are placeholders: the reference names them, but nobody has",
           "  checked what they need yet.", "",
           "To validate one, call it on a test system, then write it up in the README in the form below and update",
           "`VALIDATED` in `tools/endpoints.py`.", "",
           "```markdown", "### <What it does>: `<METHOD> /<base>/<path>` [live]", "",
           "<One sentence: what it is for.>", "",
           "| Field | Required | Accepted values |", "|---|---|---|",
           "| `<field>` | yes / no / when … | fixed: … / per installation: where to read them |", "",
           "A body that worked, the answer's shape, and anything surprising.", "```", ""]
    for tag in ("Access", "Catalog", "Admin"):
        out += [f"## {tag}: `{BASES[tag]}`", ""]
        area = None
        for t, a, m, full in sorted((r for r in rows if r[0] == tag), key=lambda r: (r[1].lower(), r[3], r[2])):
            if a != area:
                out += ["", f"### /{a}", "", "| Method | Path | Status |", "|---|---|---|"]
                area = a
            key = (m, full)
            if key in VALIDATED:
                status = f"validated: [README](../README.md#{VALIDATED[key]})"
            elif key in NOT_WORKING:
                status = f"did not work on the lab ({NOT_WORKING[key]})"
            else:
                status = "_not validated yet_"
            out.append(f"| {m} | `{full}` | {status} |")
        out.append("")
    print("\n".join(out))


if __name__ == "__main__":
    main(sys.argv[1])
