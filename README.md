# Identity Applications REST API: how to call it

A practical guide to the REST API of NetIQ / OpenText Identity Manager's Identity Applications (the User Application,
or RBPM): authentication, tasks, requests, role and resource assignments and revocation, the catalog, and the
administration calls.

The vendor's reference (the Swagger UI at `https://<apps host>/idmappsdoc/`, backed by `openapi.json`) names every
endpoint: 264 paths and 339 operations in the copy checked here. But most of its request bodies are empty schemas
(213 of its 404 schemas have no fields), and its examples are placeholders (`"..."`, `12345`). It rarely says which
field is required, which values are accepted, where an endpoint lives, or what a working call looks like. This guide
records that.

- **How it was made:** by inspection and observation of a running system: Identity Manager 4.10 (its `/idmappsdoc`
  reference reports version 4.10.2), in October 2026. Where these pages say "the test system", they mean that one.
- **Other versions** may behave differently.

> Made by [Point Blue Technology](https://pointbluetech.com). Not affiliated with, endorsed by or supported by
> OpenText. NetIQ, Identity Manager and OpenText are trademarks of OpenText or its affiliates; other names belong to
> their owners. These notes describe observed behavior; they are not the vendor's documentation, and they carry no
> warranty. Try any change on a test system first.

## Contents

- [Authenticating](docs/authentication.md): OSP tokens, refresh, lifetimes, and the trap that locks a user out
- [Every endpoint](docs/endpoints.md): all 339 operations, each with whether it was tested and a link to its section
- The reference, by area: one section per operation, with its parameters, body fields, answer, an example and the
  behavior seen:
  - [Workflow](docs/reference/workflow.md): tasks, requests, the cart, forms, teams, proxies, delegation, availability
  - [Catalog](docs/reference/catalog.md): roles, resources, SoDs, entitlements, categories, drivers, administrators
  - [People](docs/reference/people.md): users, groups, containers, entities, the organization chart, the DAL
  - [Settings](docs/reference/settings.md): configuration, administration, display, logging, caches, workflow engines
  - [Not in the reference](docs/reference/unlisted.md): routes the server answers that the reference leaves out

In this page:

1. [Basics](#1-basics): where each endpoint lives, signing in, errors, and the two kinds of values
2. [Tasks](#2-tasks): list, read, approve and deny
3. [Requests](#3-requests): start a PRD, request a role or a resource, history, retract
4. [Assignments](#4-assignments): who has what, assigning and revoking
5. [Catalog](#5-catalog): roles, resources, PRDs and users
6. [Other reads](#6-other-reads): separation of duties, proxy, delegation, availability
7. [Index and caches](#7-the-permission-index-and-the-caches)
8. [States and codes seen](#8-states-and-codes-seen)
9. [Gotchas](#9-gotchas)
10. [Known problems and cautions](#10-known-problems-and-cautions)

---

## 1. Basics

### 1.1 Where each endpoint lives

The reference lists every path without its base. Each operation carries a tag, and the tag gives the base:

| Tag in the reference | Base | Examples |
|---|---|---|
| Access (219 operations) | `https://<apps host>/IDMProv/rest/access` | `/tasks`, `/requests`, `/assignments`, `/permissions`, `/users/list` |
| Catalog (79) | `https://<apps host>/IDMProv/rest/catalog` | `/roles`, `/resources`, `/prds`, `/sods`, `/users` |
| Admin (41) | `https://<apps host>/IDMProv/rest/admin` | `/cache`, `/logging`, `/workflowengines` |

A path called under the wrong base answers Tomcat's HTML 404. Some paths exist under two bases with different
meanings, so the base matters:

- `/users` is a user search under Catalog, and a different call under Access.
- `/sods` exists under Catalog only; under Access it answers 404.

### 1.2 Signing in

The full page is [docs/authentication.md](docs/authentication.md). In short:

- **Getting a token:** `POST https://<apps host>/osp/a/idm/auth/oauth2/token`, with the client's id and secret as HTTP
  Basic (`rbpmrest`), and body `grant_type=password&username=<user or DN>&password=<password>`. The answer is an
  access token (120 seconds by default) and a refresh token (30 days).
- **Keeping going:** `grant_type=refresh_token&refresh_token=<token>` gives a new access token. The refresh token is
  not rotated, and it needs the client's secret.
- **On every call:** `Authorization: Bearer <access_token>`, `Accept: application/json`, and
  `Content-Type: application/json` when there is a body.
- **Sign in once, then refresh.** Every password sign-in writes to the user's `oidpInstanceData`, and when it is full
  (about 32 KB) that user can no longer sign in
  ([the oidpInstanceData trap](docs/authentication.md#the-oidpinstancedata-trap)).

### 1.3 Errors

- **489** (or 400 for input the XSS filter rejects), body
  `{"Fault": {"Code": {"Value": "Sender", "Subcode": {"Value": "<code>"}}, "Reason": {"Text": "<message>"}}}`.
  - Subcodes seen: `InvalidInput`, `InternalExceptionOccured` (sic), `PermissionIndexException`, `SecurityException`,
    `NotFound`, `InvalidEnumValue`, `XSSValidationFailure`.
  - The message often names the missing field, for example "Role id is required" or
    "Permission id (id:) is required".
  - "Internal Error. Please contact Administrator." is the usual answer to a missing or malformed field the server does
    not check by name. Each operation's notes list the inputs that produced it.
- **200 with `"success": false`:** a refusal in a list answer, with `failed[].reason` saying why. Always check
  `success`.
- **HTML pages:** 404 for a wrong path, 405 for a wrong method, and 500 (an "Error Page") for some missing query
  parameters (§4.2).

### 1.4 Two kinds of values

Every "accepted values" entry is marked as one of:

- **fixed:** the server accepts only a fixed set, such as task actions or `entityType`.
- **per installation:** each system defines the values in its own configuration. They are not a fixed set; read them
  from your system. Examples:
  - category ids (the Directory Abstraction Layer and the role and resource categories);
  - role levels (`GET /catalog/roles/levels`);
  - the user search root;
  - form field keys (the request and approval forms);
  - DAL entity and attribute keys;
  - client ids (OSP), and the applications' clients (`GET /access/config/clients`).

  Values shown for these are examples from the test system, not lists.

---

## 2. Tasks

### 2.1 List my tasks: `GET /access/tasks/list`

Every parameter is optional:

| Parameter | Default | Accepted values |
|---|---|---|
| `fromIndex` | 1 | 1-based start |
| `size` | 10 | page size |
| `q` | `*` | search text |
| `sortOrder` | `asc` | `asc`, `desc` (fixed; anything else gives 489 "invalid sort order") |
| `sortBy` | `createTime` | a task-list column; `createTime` is safe |
| `status`, `assignStatus`, `recipient`, `assignedTo`, `expireWithin`, `expireUnit`, `proxyUser`, `onlyHelpdeskTask`, `delegatedTasks` | | filters |

**Answer:** `{"tasks": [...], "nextIndex", "arraySize"}`.

- **Fields per task:** `taskId`, `processName`, `activityName`, `recipient`, `initiator`, `createTime` and
  `expirationTime` (epoch ms), `approvalFormId`, `isNewForm` (true for a JSON form), `taskClaimed`, and more.
- **Missing process id:** `processId` is empty in the list. `GET /tasks/workEntries` (§2.4) gives the request id for
  a task.
- **Other people's tasks:** signed in as the provisioning administrator, the list also holds tasks addressed to other
  users, while `GET /access/tasks` answers `{"total": 0}`.
- **Stale tasks:** a task stays in the list after its process is terminated (`POST /access/monitoring/process/terminate`),
  as after a retraction (§3.5).
- **Task ids can change:** after a workflow migration import (`POST /access/data/migration/workflow`) the same open
  tasks came back with new `taskId`s.

### 2.2 One task: `POST /access/tasks/item`

`{"taskId": "<id>"}` (**required**) returns the task with its comments, `processId` (the request definition's DN),
`initiator`, `recipient` and `approvalFormId`. On a legacy form, it also returns resolved `dataItems`.

### 2.3 Approve, deny and more

**`POST /access/tasks`:** the action for any number of tasks, when the approval form has no fields to fill.

```json
{"tasks": [{"taskId": "a563c8e938fa4b48b0cc754ed3f5eed2"}], "action": "approve", "comment": "approved by script"}
```

| Field | Required | Accepted values |
|---|---|---|
| `tasks[].taskId` | yes | from the task list |
| `action` | yes | fixed: `approve`, `deny`, `comment`, `refuse`, `claim`, `release`, `reassign`, `return` (case does not matter; anything else gives 489 `InvalidEnumValue`) |
| `comment` | no | text for the request's history |
| `approver` | for `reassign` | a DN |
| `dataItems` | no | `[{"name", "values": [...]}]` for a legacy approval form |

**Answer:** `{"success": true, "succeeded": [{"id": "<taskId>"}], "failed": []}`.

**`POST /access/tasks/v2`:** one task, the way the JSON approval form does it. Use this when the approval form has
fields. The reference's schema for this body is a generic object with no real fields.

```json
{"taskId": "23acb508539a455284d872b619a6a722", "taskAction": "ApprovalAction", "comments": "approved by script", "data": []}
```

| Field | Required | Accepted values |
|---|---|---|
| `taskId` | yes | |
| `taskAction` | yes | fixed: `ApprovalAction`, `DenyAction`. `ClaimAction` is what the form renderer sends to claim |
| `comments` | no | text |
| `data` | no | `[{"key": "<field key>", "value": [...]}]`; the keys are the approval form's (per installation) |

**Answer:** `{"success": true, "message": "Form submission successfully processed."}`.

**Every failure gives the same answer:** 489 `InvalidInput` "Form submission failed to process." That covers a
missing `taskId`, an unknown action, and a task whose workflow is gone. Check the inputs yourself first.

A role request approved with `ApprovalAction` went on to `Completed`, and one denied with `DenyAction` read
`Denied` (§8).

**Reassign as an administrator:** `POST /access/monitoring/reassign` with
`{"afTaskNode": {"tasks": [{"taskId": "<id>", "addressee": "<new addressee DN>"}], "comment": "<text>"}}`. Other body
shapes also answer `{"success": true}` and change nothing; see its
[reference section](docs/reference/workflow.md#post-idmprov-rest-access-monitoring-reassign).

### 2.4 Around tasks

| Call | What it gives |
|---|---|
| `GET /access/tasks/badge` | `{"badge": <open tasks of the caller>}` |
| `GET /access/tasks/list/others?size=` | tasks of other people, for a help desk user or an administrator; same shape as the list, plus `hasMore`, `totalSize` |
| `GET /access/tasks/workEntries?processId=<request id>&size=` | the work entries of a request. Each has `id` (the task id), `activityName`, `Addressee`, `Recipient`, `owner`, `availableActions` (`[{"code": "0", "value": "Approve"}, {"code": "1", "value": "Deny"}]`), `processId` (the request definition's DN) and `requestId` |
| `GET /access/tasks/list/others/team?memberDn=<DN>&teamDN=<DN>` | a team member's tasks, for the team's manager. The team needs the "Manage Addressee Task" permission on the task's PRD, or the list is empty |

Despite the parameter's name, `processId` in `workEntries` takes the request id from the history (§3.4).

---

## 3. Requests

### 3.1 Start a PRD with a JSON request form: `POST /access/requests/permissions/v2`

```json
{
  "reqPermissions": [{"id": "cn=Access Request,cn=RequestDefs,cn=AppConfig,cn=User Application Driver,cn=driverset1,o=system", "entityType": "PRD"}],
  "data": [{"key": "reason", "value": ["needed for the project"]}],
  "recipients": [{"dn": "cn=jsmith,ou=users,o=data", "type": "user"}]
}
```

| Field | Required | Accepted values |
|---|---|---|
| `reqPermissions` | yes, not empty | only the first entry is used |
| `reqPermissions[0].id` | yes | the PRD's DN. It must be in the permission index (§7), or the answer is 200 `"success": false` with no reason |
| `reqPermissions[0].entityType` | yes | fixed: `PRD` |
| `reqPermissions[0].proxyFor` | no | a user DN, to request on their behalf |
| `data` | in practice | one entry per request-form field. `key` is the form's field key (per installation, matched without regard to case); `value` is always a list. Fields left out keep their default |
| `recipients` | no | `[{"dn", "type"}]`, `type` fixed: `user`, `group`, `team`. Absent means the caller. One workflow starts per recipient |

**Answer:** `{"success": true, "OperationNodes": [{"success": true, "userDn", "succeeded": [{"id", "requestId"}]}]}`.
`requestId` is the request id in the history.

### 3.2 Request a role or a resource: `POST /access/requests/permissions/item`

```json
{"id": "cn=AccessRole,cn=Level10,cn=RoleDefs,cn=RoleConfig,cn=AppConfig,cn=User Application Driver,cn=driverset1,o=system",
 "entityType": "role", "reason": "needed for the project",
 "recipients": [{"dn": "cn=jsmith,ou=users,o=data", "type": "user"}]}
```

| Field | Required | Accepted values |
|---|---|---|
| `id` | yes | the role's or resource's DN, in the permission index (else 489 "Permission with id [...] does not exist") |
| `entityType` | yes | fixed: `role`, `resource` (`prd` only for a PRD with a legacy form) |
| `reason` | no | text, kept as the request description |
| `recipients` | no | as in §3.1 |
| `effDate`, `expDate` | no | epoch ms |
| `permReqParams` | no | `[{"key", "value"}]`: a resource's parameters |
| `sodJustification`, `proxyUser` | no | |

**Answer:** `{"success": true, "OperationNodes": [{"success": true, "userDn", "succeeded": [{"id", "instanceId"}]}]}`.

- **`instanceId`:** the DN of the request object the call makes, under `cn=Requests` (roles) or
  `cn=ResourceRequests` (resources) in `cn=RoleConfig,cn=AppConfig,<User Application driver>`.
- **Timing:** without an approval, the role or resource was assigned within 10 seconds.
- **With approval:** the request waits for its approval task (§2.3) and reads `Approval Pending`.
- **JSON-form PRDs:** this endpoint does not handle them. It answers 200 `"success": false`; use §3.1.

### 3.3 Many permissions for many people: `POST /access/requests/permissions`

```json
{"reason": "needed for the project",
 "reqPermissions": [{"id": "<role DN>", "entityType": "role"}],
 "recipients": [{"dn": "cn=jsmith,ou=users,o=data", "type": "user"}]}
```

| Field | Required | Accepted values |
|---|---|---|
| `reason` | yes (else 489 invalid reason) | text |
| `reqPermissions` | yes, not empty | `[{"id", "entityType", "proxyFor"}]`; `entityType` fixed: `role`, `resource`, `prd` |
| `recipients` | no | `[{"dn", "type"}]`; absent means the caller. Groups are expanded to their members, unless the caller is a Roles or Security domain administrator |
| `effDate`, `expDate` | no | epoch ms |
| `sodJustification`, `proxyUser` | no | |

**Answer:** as in §3.2, one `OperationNodes` entry per recipient. A role with an approval made a task for its
approver, as in §3.2.

### 3.4 History

**My requests:** `GET /access/requests/historylist?nextIndex=1&size=20&q=*&sortOrder=desc&sortBy=requestDate`
returns `{"requests": [...]}`.

- **Fields per request:** `id`, `name`, `entityType`, `requestState`, `processState`, `requestStatus`, `requestOper`,
  `requester`, `recipient`, `requestDate` and `confirmationNumber`.
- **One request, two entries:** a role or resource request that needs approval appears twice. One entry is the role
  request itself (`entityType` `role`, `id` = the request object's DN, `requestStatus` such as `Approval Pending`). The
  other is the approval workflow (`entityType` `prd`, `id` = a 32-character request id).
- **Codes:** the state codes are in §8.

**All requests for one role or resource** (administrators):
`POST /access/requests/historylist/permission?item=<role DN>&type=role` with body `{}`. The permission's DN goes in
the `item` query parameter; with `id` or `permissionId` instead the answer is 489 "Permission id (id:) is required".
The answer is `{"totalSize", "total", "nextIndex", …}`.

**Someone else's requests:** `POST /access/requests/historyForUser` with `{"dn": "<user DN>"}` (domain
administrators, or help desk users for their clients).

**One request with its comments:** `POST /access/requests/history/item`.

```json
{"id": "954d7ba428214842bedd0021d6671645", "entityType": "prd"}
```

- **Required:** both fields, or 489 `InvalidInput` naming the missing one. `entityType` takes the history entry's
  value.
- **Comments:** newest first, with `user`, `comment`, `date`, `activity`, `commentDn` and `msgId`
  (`User_Task_Assigned`, `User_Task_Denied` and others).
- **Whose actions:** an action by a person carries that person's DN. The OAuth client is not recorded.

**The workflow behind a request:** `GET /access/requests/processes?processId=<request id>&size=`. Returns
`{"processes": [{"processId" (the PRD's DN), "Initiator", "Recipient", "Definition", "processStatus" (Running …),
"approvalStatus" (Processing …), "requestId", "correlationId", "creationTime", "engineId", "version"}]}`.

### 3.5 Retract a request: `DELETE /access/requests/history`

```json
{"requests": [{"id": "f51751ecd0234e69bf4092155d63862b", "entityType": "prd"}]}
```

**Answer:** `{"success": true, "succeeded": [{"id", "entityType"}]}`.

- **What it does:** the workflow ends (`requestState` 3, `processState` 2), and its history gets the comment
  "Request was retracted through REST interface".
- **What it leaves behind** for a role request that was waiting for approval:
  - the role request object still reads `Approval Pending`;
  - the approval task was still in the approver's list 45 seconds later; acting on it then failed, and a little later
    it was gone.

  Clean up the request object if you retract this way. Terminating the workflow
  (`POST /access/monitoring/process/terminate`) leaves the same behind.
- **`retractable`:** the history said `retractable: false` for this request, and the retraction still went through.

---

## 4. Assignments

### 4.1 A person's roles and resources

| Call | Body | Answer |
|---|---|---|
| `POST /access/assignments/list` | `{"dn": "<person>", "nextIndex": 1, "size": 20}` | roles and resources: `{"total", "nextIndex", "token", "assignments": [...]}` |
| `POST /access/assignments/role/list?nextIndex=1&size=20` | `{"dn": "<person>"}` (**required**: an empty body gives 489 internal error) | roles; `onlyDirectAssignments=true` leaves out inherited ones |
| `POST /access/assignments/resource/list?nextIndex=1&size=20` | `{"dn": "<person>"}` | resources |
| `POST /access/assignments/list/v2` | `{"dn": "<person>"}` | roles, with paging, caching (`token`) and many filters (`forceRefresh`, `noCache`, …) |
| `GET /access/assignments` | | the caller's own |
| `GET /access/assignments/advanced?nextIndex=1&size=20` | | the caller's, filtered (`name`, `userAssigned`, …) |
| `POST /access/assignments/item` | `{"id": "<permission DN>", "entityType": "role"}` | the caller's assignment of one permission |

- **Fields per assignment:** `id`, `name`, `description`, `entityType`, `requestedBy`, `effectiveDate` (epoch ms)
  and `categories` (`[{"categoryId", "categoryName"}]`; the ids are per installation).
- **`total`:** in `list/v2` and `advanced` it is the page's count; in `role/list` it is everything.
- **Lower-cased ids:** `GET /access/assignments` returns the permission DNs in lower case
  (`cn=…,cn=level10,cn=roledefs,…`); compare DNs case-insensitively.
- **Not here:** the assignment's instance id, which a resource revocation needs (§4.3). Read it from §4.2.

### 4.2 Who has a role or a resource

**Who has a permission:** `GET /access/assignments/identities?permissionId=<DN>&permissionType=role&nextIndex=1&size=20`.

```json
{"assignmentToList": [{"subtype": "USER", "assignedToDn": "cn=jsmith,ou=users,o=data", "assigneeFullName": "Jo Smith"}],
 "nextIndex": -1, "totalCount": 1}
```

- **No error when empty:** a holder outside the user search root is left out without an error (§9).
- **Required parameter:** without `permissionType`, the answer is an HTML 500.

**A role's assignments:** `POST /catalog/roles/role/assignments?nextIndex=1&size=20` with body `{"id": "<role DN>"}`.
Returns `{"dn", "arraySize", "roleAssignments": [{"identity", "identityDisplayName", "assignmentType"
("User Assigned to Role"), "assignmentStatus", "effectiveDate", "reason"}]}`. The v2 call
(`…/role/assignments/v2`) takes `{"dn": "<role DN>"}` instead of `id`.

**A resource's assignments:** `POST /catalog/resources/resource/assignments?nextIndex=1&size=20` with body
`{"dn": "<resource DN>"}`. Returns `{"assignmentStatusList": [{"recipientDn", "recipientFullName", "statusCode",
"statusDisplay", "requestDate", "requesterDn", "description", "instanceGuId"}]}`.

- **`instanceGuId`** (that spelling) is what a resource revocation needs.
- **`grant` is not the state:** a completed assignment made with `…/assignments/assign` is listed with
  `"grant": false` and `statusCode` "50" (Completed). Go by `statusCode`/`statusDisplay`.
- **Resource parameters:** a helpdesk resource assigned through the client's helpdesk settings carries
  `"dynamicParams": {"dynamicParamList": [{"paramName": "param1", "paramValues": ["\"client1(1)\""]}]}` (the client).

### 4.3 Revoke: `DELETE /access/assignments/list`

The reference's example is a copy of an assignment list. What the server reads:

```json
{
  "reason": "no longer needed",
  "assignments": [
    {"id": "cn=AccessRole,cn=Level10,cn=RoleDefs,cn=RoleConfig,cn=AppConfig,cn=User Application Driver,cn=driverset1,o=system",
     "entityType": "role",
     "assignmentToList": [{"subtype": "user", "assignedToDn": "cn=jsmith,ou=users,o=data"},
                          {"subtype": "user", "assignedToDn": "cn=pjones,ou=users,o=data"}]}
  ]
}
```

| Field | Required | Accepted values |
|---|---|---|
| `reason` | yes (else 489 "Reason for request is required.") | text |
| `assignments[].id` | yes | the permission's DN |
| `assignments[].entityType` | yes | fixed: `role`, `resource` |
| `assignments[].assignmentToList` | **yes in practice** (see below) | whom to revoke from |
| `assignmentToList[].assignedToDn` | yes | the holder's DN |
| `assignmentToList[].subtype` | yes | fixed: `user`, `group`, `container`, in lower case. The identities read answers `USER`; send `user` (`USER` is refused) |
| `assignmentToList[].instanceId` | **for a resource** (else "Assignment instance GUID (instanceId:) is required for resource revocation") | the assignment's `instanceGuId` from §4.2; not needed for a role |

**Answer:** `{"success": true, "succeeded": [{"id", "name", "revokeFrom": "<holder>", "instanceId"?}]}`, or
`"success": false` with `failed[].reason`.

- **Many at once:** several holders can be listed, and are revoked in one call.
- **Timing:** the assignment was gone within 10 seconds, and the history shows the revocation as `requestOper` 15.
- **Missing `assignmentToList` revokes nothing:** the answer is still 200 `{"success": true}`. It looks like it means
  "revoke from the caller", and the caller held nothing.
- **Your own assignments:** `DELETE /access/assignments` with `{"reason", "assignments": [{"id", "entityType"}]}`
  removes the caller's own direct assignments.

### 4.4 Assign directly

These assign without a request or approval. Each completed within about 12 seconds.

**A role:** `POST /catalog/roles/role/assignments/assign`

```json
{"reason": "<why>", "assignments": [{"id": "<role DN>", "entityType": "role",
  "assignmentToList": [{"assignedToDn": "cn=jsmith,ou=users,o=data", "subtype": "user"}]}]}
```

The recipient field is `subtype` (as in the revocation). An assignment that breaks a separation of duties constraint
is refused with 200 `"success": false`, `errCode` "SoD-Violation", and a `sods` list naming the constraint and both
roles.

**A resource:** `POST /catalog/resources/resource/assignments/assign`, and the same body to `…/assignments/revoke`:

```json
{"dn": "<resource DN>", "recipientDns": ["cn=jsmith,ou=users,o=data"], "recipientType": "user", "description": "<why>"}
```

The revoke needs no instance id. A resource with parameters takes `dynamicParamList`.

---

## 5. Catalog

### 5.1 Search

| Call | Answer |
|---|---|
| `GET /catalog/roles/listV2?q=*&nextIndex=1&size=20` | `{"roles": [{"id", "name", "description", "level", "roleLevel"}], "nextIndex", "arraySize", "total"}`; the permission index's roles |
| `GET /catalog/resources/listV2?q=*&nextIndex=1&size=20` | `{"resources": [...]}` |
| `GET /catalog/roles?q=*` and `GET /catalog/resources?q=*` | the catalog's lists |
| `GET /catalog/prds?q=*&nextIndex=1&size=50` | `{"requestDefs": [{"id", "name", "description"}]}` |
| `GET /catalog/roles/levels` | `{"roleLevels": [{"name", "level", "cn"}]}`: the role levels (per installation; the test system had Business Role 30, IT Role 20, Permission Role 10) |

**The catalog keeps entries the vault no longer has.** `catalog/prds`, `catalog/roles` and `catalog/resources` listed
items that had been deleted from the vault directly with LDAP. A request for one answered "Permission with id [...]
does not exist". Check an item with `POST /access/permissions/item` (§7) before requesting it, and create and delete
roles through the catalog API (§5.2) so it stays in step.

`GET /access/permissions?q=*` (the index search the reference describes) answered `arraySize 0` every time. Use the
`listV2` calls instead.

### 5.2 Roles: create, read, change, delete

**Create:** `POST /catalog/roles`.

```json
{"id": "accessrole", "name": "Access Role", "description": "what the role gives", "level": 10}
```

| Field | Required | Accepted values |
|---|---|---|
| `id` | yes (else 489 "Role id is required") | the role's `cn` (not a DN) |
| `name` | yes | display name |
| `level` | yes | a level from `GET /catalog/roles/levels` (per installation). The role is created under that level's container, as `cn=<id>,cn=Level<n>,cn=RoleDefs,…` |
| `description`, `categories`, `owners`, `approvalRequired`, … | no | see change, below |

- **Answer:** the role, with `id` its DN.
- **Requestable at once:** the role is requestable immediately, without waiting for the permission index.

**Read:** `POST /catalog/roles/role` with body `{"roles": [{"id": "<role DN>"}]}` returns
`{"roles": [{... "approvalRequired", "approvalIsStandard", "status": 50, "localizedNames", …}]}`. A role that was
deleted gives 489 "Permission with id [] does not exist." (empty brackets) when it is the only one asked for; with
several deleted roles the message names one of them.

**Change:** `PUT /catalog/roles/role` with the role, its `id` the DN. To require a standard approval:

```json
{"id": "<role DN>", "name": "Access Role", "level": 10,
 "approvalRequired": true, "approvalIsStandard": true,
 "approvalApprovers": [{"id": "cn=approver,ou=users,o=data", "type": "user", "sequence": 1}]}
```

- **What the server sets:** the answer shows `approvalRequestDef` set to the installation's standard role-approval
  PRD (`cn=Role Approval,cn=RequestDefs,…` by default).
- **What a request then makes:** each request makes an approval task with the JSON approval form "Role Approval Form".

**Hierarchy and mappings:** `POST /catalog/roles/subRoles` (a parent of a higher level over a child),
`POST /catalog/roles/mappedResources` (resources a role grants), and their `…/list` reads. See the
[catalog reference](docs/reference/catalog.md).

**Delete:** `DELETE /catalog/roles/role` with body `{"roles": [{"id": "<role DN>"}]}` returns
`{"success": true, "succeeded": [{"id"}]}`. The role leaves the index and the vault.

### 5.3 Users

| Call | Answer |
|---|---|
| `GET /catalog/users?q=<text>&nextIndex=1&size=20` | `{"users": [{"id", "firstName", "lastName", "cn"}], "arraySize"}`. `q` matches first and last names (`Api*`), not `cn` |
| `GET /access/users/list?q=<text>&nextIndex=1&size=20` | `{"usersList": [{"dn", "fullName", "primaryAttributes", …}], "totalSize"}`; `clientId`, `columnCustomization` and `filter` shape the columns |
| `GET /access/users/details?userDn=<DN>` | the person as the dashboard shows them: `fullName`, `primaryAttributes`, `secondaryAttributes`, `groupMemberof`, `disabledLogin`, … (attribute keys per installation). A DN that does not exist gives 489 with the raw LDAP error text (`javax.naming.NameNotFoundException: [LDAP: error code 32 - NDS error: no such entry (-601)]`) |

**Creating users:** `POST /access/user` creates a user with an initial password, which must meet the password policy
that applies (per installation; every attribute needs `isRequired`). `POST /access/entities/item` with key `user`
creates one without a password. See the [people reference](docs/reference/people.md).

User searches, and the "who has" reads (§4.2), only see users under the applications' user search root. That's
`DirectoryService/realms/jndi/params/USER_ROOT_CONTAINER` in the applications' `ism-configuration.properties` (per
installation). A user elsewhere is simply not found.

---

## 6. Other reads

| Call | Notes |
|---|---|
| `GET /catalog/sods` | `{"sods": [...], "arraySize", "nextIndex"}`: the separation of duties constraints |
| `POST /catalog/sods/list` | `{"roles": [{"id": "<role DN>"}]}`: the constraints those roles are part of (`{}` finds nothing) |
| `GET /access/sods/violations?sodDn=<DN>` | **`sodDn` required** (else 489 "Value for sodDn is missing in payload"). Returns `{"sodId", "sodViolations"}`; with no violations just `{"sodId"}` |
| `GET /access/sods/violations/user?userDn=<DN>` | `{"id", "sods": [...]}`: the constraints a person violates; with none just `{"id"}` |
| `GET /access/delegation` | `{"totalDelegations", …}`: the caller's delegations |
| `GET /access/proxy/all` | `{"configureProxy", "userType", …}` |
| `GET /access/proxy/for` | the people the caller may act for: `{"userArraySize", …}` |
| `GET /access/availability` | `{"totalAvailability", "availabilityStatus", "hasDelegatesAssigned", "newable"}` |

**Creating a constraint:** `POST /catalog/sods` takes `sodApprovalType` as `alwaysAllow` or `allowWithWorkflow`, the
names the reads return. The enum names (`ALWAYS_ALLOW`) and the codes (`"0"`) are not accepted: the answer is a
generic 489 "Internal Error". The two roles must differ and be of the same level.

An assignment that breaks a constraint is refused (§4.4), so the violation reads stay short unless an approved
exception exists. The full answers are on the [reference pages](docs/reference/).

---

## 7. The permission index and the caches

**Is it requestable?** `POST /access/permissions/item` with body `{"id": "<DN>", "entityType": "prd"}` returns the
item's detail when it is in the index.

- **Required:** both fields.
- **Not in the index:** 489 `PermissionIndexException`.
- **PRDs only:** `{"id": "<role DN>", "entityType": "role"}` answers 489 "Permission type [role] is not supported for
  this operation."; check roles and resources in the catalog instead.
- **For a PRD:** the detail includes `requestFormId`, `isNewForm`, `categories`, and `dataItems` for a legacy form.

**Deployment timing.** A PRD deployed straight to the vault reaches the index only on the index's refresh interval
(`com.netiq.idm.cis.rbpm.updateInterval.prd`, in minutes, default 10). To make it requestable at once, flush the
caches:

```
DELETE /admin/cache/holder/items
{"cacheHolderItems": [{"cacheHolderID": "All Cache"}]}
```

- **Answer:** 204.
- **Holder names:** `GET /admin/cache/holders` lists them.
- **No shortcut:** `POST /access/index/permissions` with
  `{"permIndexChanges": [{"operation": "ADD_OR_MODIFY", "permId", "permType": "PRD"}]}` answers success but does not
  make the PRD requestable any sooner.
- **Catalog changes:** roles made through the catalog API (§5.2) are requestable at once.
- **New users and drivers:** after users or an entitlement driver were added, some reads (the organization chart, the
  driver lists) failed or showed nothing until the caches were flushed.

---

## 8. States and codes seen

These are the values seen. The server sets them; none is configurable, but other versions may add more.

**A role or resource request** (`requestState` of the role or resource entry in the history, and `nrfStatus` on the
request object):

| Code | `requestStatus` |
|---|---|
| 15 | Approval Pending |
| 50 | Completed |
| 95 | Denied |

**`requestOper`:** 10 for a grant, 15 for a revocation.

**The approval workflow behind a request** (`entityType` `prd` in the history):

| `requestState` / `processState` | Meaning |
|---|---|
| 0 / 0 | running, waiting for approval |
| 2 / 3 | approved, completed |
| 1 / 3 | denied |
| 3 / 2 | retracted |
| 4 / 2 | failed in the engine |

A terminated process reads `processStatus` 2 in `GET /access/monitoring/process/list`.

**Work entry `availableActions`:** code 0 Approve, code 1 Deny.

---

## 9. Gotchas

1. **The base is the tag.** Catalog paths under `/IDMProv/rest/access` answer 404 (§1.1).
2. **Sign in once.** A password grant per call fills `oidpInstanceData`, and the user can no longer sign in ([authentication](docs/authentication.md#the-oidpinstancedata-trap)).
3. **`success: false` comes with a 200.** Read `success` and `failed[].reason`.
4. **Some calls answer success and do nothing:** a revocation that names no one (§4.3), a reassign with the wrong body
   shape (§2.3), and `POST /access/user/dn`, which renames a user only in the workflow database.
5. **`subtype` is lower case in a revocation** (`user`), but upper case in the identities answer (`USER`).
6. **A resource revocation needs the assignment's instance id** (`instanceGuId` from the resource's assignments,
   sent as `instanceId`); a role revocation does not.
7. **`tasks/v2` explains nothing:** every failure is "Form submission failed to process."
8. **The catalog lists items deleted from the vault.** Check the permission index before requesting (§5.1).
9. **User searches and "who has" see only the user search root.** Holders elsewhere are left out without an error
   (§5.3).
10. **Retracting or terminating an approval workflow leaves the role request "Approval Pending"** (§3.5).
11. **`retractable: false` did not stop a retraction** (§3.5).
12. **Values per installation are not lists:** category ids, role levels, form keys, client ids (§1.4).
13. **Compare DNs case-insensitively:** several answers return them lower-cased (§4.1).
14. **Saving a setting's own read back is not always harmless** (§10).

---

## 10. Known problems and cautions

**Calls that did not work on the test system** (details in [every endpoint](docs/endpoints.md) and each operation's
section):

- `GET /access/tasks/historyList` (tasks the caller acted on): 489 "An error occurred while obtaining the process or
  comment details from the database" with every combination of its parameters.
- `GET /access/requests/history`: always 489 "Failed to get process request history". Use
  `GET /access/requests/historylist` instead.
- `GET /access/config/access`, `/branding`, `/custom`, `/dashboard`, `/helpdesk`: answer 200 with
  `{"escapeForwardSlashAlways", "recursionDepthLimit"}` instead of the section. Read the section from
  `GET /access/config/clients/{id}` (its `config` field) or one value from `GET /access/config?key=<section>.<item>&client=<id>`.
- `GET /catalog/supportedlocales/userlocale` and `/defaultlocale`: the same empty settings object instead of a locale.
- `POST /access/workflow` (create a PRD from a template): 489 "Failed to create the PRD." on the test system. Store a
  PRD from its XML with `POST /access/workflow/prd` instead.
- `POST /catalog/roles/category` and `POST /catalog/resources/category`: 489 "Unable to find abstract layer object
  definition…" where the installation does not define the category entity.
- `POST /access/cprs/cprsrequest/status`: 489 for a request that is still running.
- The `/IDMProv/roa/v1` routes of older releases are not deployed on 4.10.2.

**Saves that change more than they say:**

- **`POST /admin/cache/customizedHolders` can stop the applications from starting.** Posting its read back unchanged
  marked the read-only `GlobalCacheHolder` active, and after the next restart the cache service failed and every
  `/IDMProv` call answered 404. Send only the holders you change, never `GlobalCacheHolder`, and keep a copy of the
  User Application driver's `cn=configuration,cn=AppDefs` object, where these settings live: restoring it fixes it.
- `PUT /admin/display/settings/request` and `/task` rewrite older stored column and sort keys in the new names.
- `PUT /access/ulp/items` and `PUT /access/ulp/landingItems/v2` share one name per item and locale, so saving one list
  can change the other's names.
- `POST /access/administration/emailApproval` fills in defaults the read left out.

**The workflow data export and import** (`GET` and `POST /access/data/migration/workflow`) work only while the
workflow engine is stopped: stop it (`POST /admin/workflowengines/status {"engineStatus": 1}`), export or import, and
start it again (`{"engineStatus": 0}`). The zip holds the workflow tables, including the workflow settings, so keep it
like a secret. After a start over REST the engine list may show "Starting" until the applications are restarted.

**A hung cart:** if `DELETE /access/queue/entry` hangs, an earlier cart call has left a database transaction open; a
restart of the applications clears it.

**Not tested:** `POST /access/cprs/assignments/publish`, which needs a finished CPRS delta. Its page gives the body
from inspection.

Corrections and results from other versions are welcome.
