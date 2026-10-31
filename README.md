# Identity Applications REST API: what the server actually reads

Field notes on the REST API of NetIQ / OpenText Identity Manager's Identity Applications (the User Application, or
RBPM). They cover authentication, tasks, requests, role and resource assignments and revocation, and the catalog.

The vendor's reference (the Swagger UI at `https://<apps host>/idmappsdoc/`, backed by `openapi.json`) names every
endpoint: 264 paths and 339 operations in the copy checked here. But most of its request bodies are empty schemas
(213 of its 404 schemas have no fields), and its examples are placeholders (`"..."`, `12345`). It rarely says which
field is required, which values are accepted, where an endpoint lives, or what a working call looks like. These notes
record that, from calls made against a running system.

- **Checked against:** Identity Manager 4.10 (its `/idmappsdoc` reference reports version 4.10.2), on a lab system,
  in October 2026.
- **Not covered:** the calls not listed here. They may behave differently on other versions.

> Not affiliated with or endorsed by OpenText. NetIQ, Identity Manager and related names are trademarks of their
> owners. These notes describe observed behavior; they are not the vendor's documentation, and they carry no
> warranty. Try any change on a test system first.

## Contents

- [Authenticating](docs/authentication.md): OSP tokens, refresh, lifetimes, and the trap that locks a user out
- [Every endpoint](docs/endpoints.md): all 339 operations, each with its status and a link to its section
- The reference, by area: one section per operation, with its parameters, body fields, answer and an example:
  - [Workflow](docs/reference/workflow.md): tasks, requests, the cart, forms, teams, proxies, delegation, availability
  - [Catalog](docs/reference/catalog.md): roles, resources, SoDs, entitlements, categories, drivers, administrators
  - [People](docs/reference/people.md): users, groups, containers, entities, the organization chart, the DAL
  - [Settings](docs/reference/settings.md): configuration, administration, display, logging, caches, workflow engines
  - [Not in the reference](docs/reference/unlisted.md): routes the server answers that the reference leaves out

In this page:

1. [Basics](#1-basics): where each endpoint lives, signing in, errors, and the two kinds of values
2. [Tasks](#2-tasks): list, read, approve and deny
3. [Requests](#3-requests): start a PRD, request a role or a resource, history, retract
4. [Assignments](#4-assignments): who has what, and revoking
5. [Catalog](#5-catalog): roles, resources, PRDs and users
6. [Other reads](#6-other-reads): separation of duties, proxy, delegation, availability
7. [Index and caches](#7-the-permission-index-and-the-caches)
8. [States and codes seen](#8-states-and-codes-seen)
9. [Gotchas](#9-gotchas)
10. [Not working, or not checked](#10-not-working-or-not-checked)

How each fact is known:

- **[live]:** called on the lab system, with the answer shown.
- **[server]:** read from the applications' own error messages, which name the field they want.
- **[server code]:** read from the 4.10.2 server's REST classes: their routes, defaults, the fields they check and
  the values they compare against. The reference pages say so in each operation's status. The code itself is not
  reproduced here.
- **[server log]:** read from the applications' own log (`catalina.out`) after a call failed with a generic error.
- **[reference]:** only from the vendor's reference.

---

## 1. Basics

### 1.1 Where each endpoint lives

The reference lists every path without its base. Each operation carries a tag, and the tag gives the base
**[live]**:

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
  access token (120 seconds on the lab) and a refresh token (30 days).
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
    "Permission id (id:) is required". That is how several required fields below were found.
- **200 with `"success": false`:** a refusal in a list answer, with `failed[].reason` saying why. Always check
  `success`.
- **HTML pages:** 404 for a wrong path, 405 for a wrong method, and 500 (an "Error Page") for some missing query
  parameters (§4.6).

### 1.4 Two kinds of values

Every "accepted values" entry below is marked as one of:

- **fixed:** the server's code compares against a set, such as task actions or `entityType`.
- **per installation:** each system defines the values in its own configuration. They are not a fixed set; read them
  from the system. Examples:
  - category ids (the Directory Abstraction Layer and the role and resource categories);
  - role levels (`GET /catalog/roles/levels`);
  - the user search root;
  - form field keys (the request and approval forms);
  - DAL entity and attribute keys;
  - client ids (OSP).

  Values shown for these are examples from one lab, not lists.

---

## 2. Tasks

### 2.1 List my tasks: `GET /access/tasks/list` [live]

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
- **Missing process id:** `processId` was empty in the list. `GET /tasks/workEntries` (§2.4) gives the request id for
  a task.
- **Other people's tasks:** signed in as the provisioning administrator, the list also held tasks addressed to other
  users (an approval waiting for a test user), while `GET /access/tasks` answered `{"total": 0}` **[live]**.
- **Stale tasks:** a task stayed in the list after its process was terminated (`POST /access/monitoring/process/terminate`),
  as after a retraction (§3.5) **[live]**.
- **Task ids can change:** after a workflow migration import (`POST /access/data/migration/workflow`) the same open
  tasks came back with new `taskId`s **[live]**.

### 2.2 One task: `POST /access/tasks/item` [live]

`{"taskId": "<id>"}` (**required**) returns the task with its comments, `processId` (the request definition's DN),
`initiator`, `recipient` and `approvalFormId`. On a legacy form, it also returns resolved `dataItems`.

### 2.3 Approve, deny and more

**`POST /access/tasks`:** the action for any number of tasks, when the approval form has no fields to fill **[live]**.

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
fields **[live]**. The reference's schema for this body is a generic object with no real fields.

```json
{"taskId": "23acb508539a455284d872b619a6a722", "taskAction": "ApprovalAction", "comments": "approved by script", "data": []}
```

| Field | Required | Accepted values |
|---|---|---|
| `taskId` | yes | |
| `taskAction` | yes | fixed: `ApprovalAction`, `DenyAction` (both checked). `ClaimAction` is what the form renderer sends to claim (not checked) |
| `comments` | no | text |
| `data` | no | `[{"key": "<field key>", "value": [...]}]`; the keys are the approval form's (per installation) |

**Answer:** `{"success": true, "message": "Form submission successfully processed."}`.

**Every failure gives the same answer:** 489 `InvalidInput` "Form submission failed to process." That covers a
missing `taskId`, an unknown action, and a task whose workflow is gone. Check the inputs yourself first.

On the lab, a role request approved with `ApprovalAction` went on to `Completed`, and one denied with `DenyAction`
read `Denied` (§8).

### 2.4 Around tasks [live]

| Call | What it gives |
|---|---|
| `GET /access/tasks/badge` | `{"badge": <open tasks of the caller>}` |
| `GET /access/tasks/list/others?size=` | tasks of other people, for a help desk user or an administrator; same shape as the list, plus `hasMore`, `totalSize` |
| `GET /access/tasks/workEntries?processId=<request id>&size=` | the work entries of a request. Each has `id` (the task id), `activityName`, `Addressee`, `Recipient`, `owner`, `availableActions` (`[{"code": "0", "value": "Approve"}, {"code": "1", "value": "Deny"}]`), `processId` (the request definition's DN) and `requestId` |

Despite the parameter's name, `processId` here takes the request id from the history (§3.4).

---

## 3. Requests

### 3.1 Start a PRD with a JSON request form: `POST /access/requests/permissions/v2` [live]

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

### 3.2 Request a role or a resource: `POST /access/requests/permissions/item` [live]

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
- **Timing:** without an approval, the lab's role and resource were assigned within 10 seconds.
- **With approval:** the request waits for its approval task (§2.3) and reads `Approval Pending`.
- **JSON-form PRDs:** this endpoint does not handle them. It answers 200 `"success": false`; use §3.1.

### 3.3 Many permissions for many people: `POST /access/requests/permissions` [reference]

Body: `reqPermissions[{id, entityType}]`, `recipients[]`, `reason`, `effDate`, `expDate`. It was not called on the lab.

### 3.4 History [live]

**My requests:** `GET /access/requests/historylist?nextIndex=1&size=20&q=*&sortOrder=desc&sortBy=requestDate`
returns `{"requests": [...]}`.

- **Fields per request:** `id`, `name`, `entityType`, `requestState`, `processState`, `requestStatus`, `requestOper`,
  `requester`, `recipient`, `requestDate` and `confirmationNumber`.
- **One request, two entries:** a role or resource request that needs approval appears twice. One entry is the role
  request itself (`entityType` `role`, `id` = the request object's DN, `requestStatus` such as `Approval Pending`). The
  other is the approval workflow (`entityType` `prd`, `id` = a 32-character request id).
- **Codes:** the state codes are in §8.

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

### 3.5 Retract a request: `DELETE /access/requests/history` [live]

```json
{"requests": [{"id": "f51751ecd0234e69bf4092155d63862b", "entityType": "prd"}]}
```

**Answer:** `{"success": true, "succeeded": [{"id", "entityType"}]}`.

- **What it does:** the workflow ends (`requestState` 3, `processState` 2), and its history gets the comment
  "Request was retracted through REST interface".
- **What it leaves behind** for a role request that was waiting for approval:
  - the role request object still read `Approval Pending`;
  - the approval task was still in the approver's list 45 seconds later; acting on it then failed, and a little later
    it was gone.

  Clean up the request object if you retract this way.
- **`retractable`:** the history said `retractable: false` for this request, and the retraction still went through.

---

## 4. Assignments

### 4.1 A person's roles and resources [live]

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
- **`total`:** in `list/v2` and `advanced` it was the page's count; in `role/list` it was everything.
- **Lower-cased ids:** `GET /access/assignments` returned the permission DNs in lower case
  (`cn=…,cn=level10,cn=roledefs,…`); compare DNs case-insensitively **[live]**.
- **Not here:** the assignment's instance id, which a resource revocation needs (§4.3). Read it from §4.2.

### 4.2 Who has a role or a resource [live]

**Who has a permission:** `GET /access/assignments/identities?permissionId=<DN>&permissionType=role&nextIndex=1&size=20`.

```json
{"assignmentToList": [{"subtype": "USER", "assignedToDn": "cn=jsmith,ou=users,o=data", "assigneeFullName": "Jo Smith"}],
 "nextIndex": -1, "totalCount": 1}
```

- **No error when empty:** a holder outside the user search root is left out without an error (§9).
- **Required parameter:** without `permissionType`, the answer is an HTML 500.

**A role's assignments:** `POST /catalog/roles/role/assignments?nextIndex=1&size=20` with body `{"id": "<role DN>"}`.
Returns `{"dn", "arraySize", "roleAssignments": [{"identity", "identityDisplayName", "assignmentType"
("User Assigned to Role"), "assignmentStatus", "effectiveDate", "reason"}]}`.

**A resource's assignments:** `POST /catalog/resources/resource/assignments?nextIndex=1&size=20` with body
`{"dn": "<resource DN>"}`. Returns `{"assignmentStatusList": [{"recipientDn", "recipientFullName", "statusCode",
"statusDisplay", "requestDate", "requesterDn", "description", "instanceGuId"}]}`.

- **`instanceGuId`** (that spelling) is what a resource revocation needs.
- **`grant` is not the state:** a completed assignment made with `…/assignments/assign` was listed with
  `"grant": false` and `statusCode` "50" (Completed) **[live]**. Go by `statusCode`/`statusDisplay`.
- **Resource parameters:** a helpdesk resource assigned through the client's helpdesk settings carried
  `"dynamicParams": {"dynamicParamList": [{"paramName": "param1", "paramValues": ["\"client1(1)\""]}]}` (the client)
  **[live]**.

### 4.3 Revoke: `DELETE /access/assignments/list` [live]

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
| `assignmentToList[].subtype` | yes | fixed: `user`, `group`, `container`, in lower case. The identities read answers `USER`; send `user` (`USER` was refused) |
| `assignmentToList[].instanceId` | **for a resource** (else "Assignment instance GUID (instanceId:) is required for resource revocation") | the assignment's `instanceGuId` from §4.2; not needed for a role |

**Answer:** `{"success": true, "succeeded": [{"id", "name", "revokeFrom": "<holder>", "instanceId"?}]}`, or
`"success": false` with `failed[].reason`.

- **Many at once:** several holders can be listed, and are revoked in one call.
- **Timing:** on the lab the assignment was gone within 10 seconds, and the history shows the revocation as
  `requestOper` 15.
- **Missing `assignmentToList` revokes nothing:** the answer is still 200 `{"success": true}`. It looks like it means
  "revoke from the caller", and the caller held nothing.

### 4.4 Assign directly [reference]

These were not called on the lab; the request endpoints (§3.2) were used instead:

- `POST /catalog/roles/role/assignments/assign`
- `POST /catalog/resources/resource/assignments/assign`
- `POST /catalog/resources/resource/assignments/revoke`

---

## 5. Catalog

### 5.1 Search [live]

| Call | Answer |
|---|---|
| `GET /catalog/roles/listV2?q=*&nextIndex=1&size=20` | `{"roles": [{"id", "name", "description", "level", "roleLevel"}], "nextIndex", "arraySize", "total"}`; the permission index's roles |
| `GET /catalog/resources/listV2?q=*&nextIndex=1&size=20` | `{"resources": [...]}` |
| `GET /catalog/roles?q=*` and `GET /catalog/resources?q=*` | the catalog's lists |
| `GET /catalog/prds?q=*&nextIndex=1&size=50` | `{"requestDefs": [{"id", "name", "description"}]}` |
| `GET /catalog/roles/levels` | `{"roleLevels": [{"name", "level", "cn"}]}`: the role levels (per installation; the lab had Business Role 30, IT Role 20, Permission Role 10) |

**The catalog keeps entries the vault no longer has.** On the lab, `catalog/prds`, `catalog/roles` and
`catalog/resources` listed items that had been deleted from the vault directly with LDAP. A request for one answered
"Permission with id [...] does not exist". Check an item with `POST /access/permissions/item` (§7) before requesting
it, and create and delete roles through the catalog API (§5.2) so it stays in step.

`GET /access/permissions?q=*` (the index search the reference describes) answered `arraySize 0` every time. Use the
`listV2` calls instead.

### 5.2 Roles: create, read, change, delete [live]

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
- **Requestable at once:** the role was requestable immediately, without waiting for the permission index.

**Read:** `POST /catalog/roles/role` with body `{"roles": [{"id": "<role DN>"}]}` returns
`{"roles": [{... "approvalRequired", "approvalIsStandard", "status": 50, "localizedNames", …}]}`. A role that was
deleted gives 489 "Permission with id [] does not exist." (empty brackets) when it is the only one asked for; with
several deleted roles the message named one of them **[live]**.

**Change:** `PUT /catalog/roles/role` with the role, its `id` the DN. To require a standard approval:

```json
{"id": "<role DN>", "name": "Access Role", "level": 10,
 "approvalRequired": true, "approvalIsStandard": true,
 "approvalApprovers": [{"id": "cn=approver,ou=users,o=data", "type": "user", "sequence": 1}]}
```

- **What the server sets:** the answer shows `approvalRequestDef` set to the installation's standard role-approval
  PRD (`cn=Role Approval,cn=RequestDefs,…` on the lab).
- **What a request then makes:** each request makes an approval task with the JSON approval form "Role Approval Form".

**Delete:** `DELETE /catalog/roles/role` with body `{"roles": [{"id": "<role DN>"}]}` returns
`{"success": true, "succeeded": [{"id"}]}`. The role leaves the index and the vault.

### 5.3 Users [live]

| Call | Answer |
|---|---|
| `GET /catalog/users?q=<text>&nextIndex=1&size=20` | `{"users": [{"id", "firstName", "lastName", "cn"}], "arraySize"}`. `q` matched first and last names (`Api*`), not `cn` |
| `GET /access/users/list?q=<text>&nextIndex=1&size=20` | `{"usersList": [{"dn", "fullName", "primaryAttributes", …}], "totalSize"}`; `clientId`, `columnCustomization` and `filter` shape the columns |
| `GET /access/users/details?userDn=<DN>` | the person as the dashboard shows them: `fullName`, `primaryAttributes`, `secondaryAttributes`, `groupMemberof`, `disabledLogin`, … (attribute keys per installation). A DN that does not exist gives 489 with the raw LDAP error text (`javax.naming.NameNotFoundException: [LDAP: error code 32 - NDS error: no such entry (-601)]`) **[live]** |

User searches, and the "who has" reads (§4.2), only see users under the applications' user search root. That's
`DirectoryService/realms/jndi/params/USER_ROOT_CONTAINER` in the applications' `ism-configuration.properties` (per
installation). A user elsewhere is simply not found.

---

## 6. Other reads

All **[live]**:

| Call | Notes |
|---|---|
| `GET /catalog/sods` | `{"arraySize", "nextIndex", …}`: the separation of duties constraints |
| `GET /access/sods/violations?sodDn=<DN>` | **`sodDn` required** (else 489 "Value for sodDn is missing in payload"). Returns `{"sodId", "sodViolations"}`; with no violations just `{"sodId"}` |
| `GET /access/sods/violations/user?userDn=<DN>` | `{"id", "sods": [...]}`: the constraints a person violates; with none just `{"id"}` |
| `GET /access/delegation` | `{"totalDelegations", …}`: the caller's delegations |
| `GET /access/proxy/all` | `{"configureProxy", "userType", …}` |
| `GET /access/proxy/for` | the people the caller may act for: `{"userArraySize", …}` |
| `GET /access/availability` | `{"totalAvailability", "availabilityStatus", "hasDelegatesAssigned", "newable"}` |

With test data in place (two SoD constraints, a delegation and a proxy), the full answers are on the
[reference pages](docs/reference/). An assignment that breaks an SoD is refused with `errCode` "SoD-Violation", so
the violation reads stay short unless an approved exception exists.

---

## 7. The permission index and the caches

**Is it requestable?** `POST /access/permissions/item` with body `{"id": "<DN>", "entityType": "prd"}` returns the
item's detail when it is in the index **[live]**.

- **Required:** both fields; `entityType` is fixed: `prd`, `role`, `resource`.
- **Not in the index:** 489 `PermissionIndexException`.
- **Roles refused:** `{"id": "<role DN>", "entityType": "role"}` answered 489 "Permission type [role] is not supported
  for this operation." **[live]**: it works for PRDs; check roles and resources in the catalog instead.
- **For a PRD:** the detail includes `requestFormId`, `isNewForm`, `categories`, and `dataItems` for a legacy form.

**Deployment timing.** A PRD deployed straight to the vault reaches the index only on the index's refresh interval
(`com.netiq.idm.cis.rbpm.updateInterval.prd`, in minutes, default 10) **[live]**. To make it requestable at once,
flush the caches:

```
DELETE /admin/cache/holder/items
{"cacheHolderItems": [{"cacheHolderID": "All Cache"}]}
```

- **Answer:** 204.
- **Holder names:** `GET /admin/cache/holders` lists them.
- **No shortcut:** `POST /access/index/permissions` with
  `{"permIndexChanges": [{"operation": "ADD_OR_MODIFY", "permId", "permType": "PRD"}]}` answered success but did not
  make the PRD requestable any sooner.
- **Catalog changes:** roles made through the catalog API (§5.2) were requestable at once.

---

## 8. States and codes seen

These are the values seen on the lab. The server sets them; none is configurable, but other versions may add more.

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

**Work entry `availableActions`:** code 0 Approve, code 1 Deny.

---

## 9. Gotchas

1. **The base is the tag.** Catalog paths under `/IDMProv/rest/access` answer 404 (§1.1).
2. **Sign in once.** A password grant per call fills `oidpInstanceData`, and the user can no longer sign in ([authentication](docs/authentication.md#the-oidpinstancedata-trap)).
3. **`success: false` comes with a 200.** Read `success` and `failed[].reason`.
4. **A revocation that names no one succeeds and does nothing** (§4.3).
5. **`subtype` is lower case in a revocation** (`user`), but upper case in the identities answer (`USER`).
6. **A resource revocation needs the assignment's instance id** (`instanceGuId` from the resource's assignments,
   sent as `instanceId`); a role revocation does not.
7. **`tasks/v2` explains nothing:** every failure is "Form submission failed to process."
8. **The catalog lists items deleted from the vault.** Check the permission index before requesting (§5.1).
9. **User searches and "who has" see only the user search root.** Holders elsewhere are left out without an error
   (§5.3).
10. **Retracting an approval workflow leaves the role request "Approval Pending"** (§3.5).
11. **`retractable: false` did not stop a retraction** (§3.5).
12. **Values per installation are not lists:** category ids, role levels, form keys, client ids (§1.4).

---

## 10. Not working, or not checked

**Did not work on the lab:**

- `GET /access/tasks/historyList` (tasks the caller acted on). It answered 489 "An error occurred while obtaining the
  process or comment details from the database" with every combination of its parameters.

**Since fixed:** `POST /access/requests/historylist/permission` (all requests for one role or resource, for
administrators) takes the permission's DN in the `item` **query** parameter, not in `id`
(`?item=<role DN>&type=role`, body `{}`) **[server code, live]**. The answer is
`{"totalSize", "total", "nextIndex", …}`.

**Also since fixed:**

- `POST /catalog/sods` (create an SoD constraint) takes `sodApprovalType` as `alwaysAllow` or `allowWithWorkflow`,
  the names the reads return. The enum names (`ALWAYS_ALLOW`) and the codes (`"0"`) arrive as no value, and the
  server fails with a generic 489 **[server log, live]**.
- `DELETE /access/queue/entry` (empty a cart) hung because of an uncommitted transaction left by an earlier call. It
  worked at once after the applications were restarted **[live]**.

**Not run to the end on the lab:** `POST /access/cprs/assignments/publish` (it needs a finished CPRS delta, which
the lab's test driver can't produce) and `POST /access/user` (the lab's password policy needs an initial password).
Their pages under [docs/reference/](docs/reference/) give the body as worked out from the server's code, marked
"not run". [Every endpoint](docs/endpoints.md) has the counts.

**Saves that change more than they say** **[live]**:

- `POST /admin/cache/customizedHolders` with the read posted back unchanged stopped the applications from starting
  after the next restart: it marks the read-only `GlobalCacheHolder` active, and the cache service then fails. Send
  only the holders you change, and keep a copy of the User Application driver's `cn=configuration,cn=AppDefs`
  object, where these settings live.
- `PUT /admin/display/settings/request` and `/task` rewrite older stored column and sort keys in the new names.
- `PUT /access/ulp/items` and `PUT /access/ulp/landingItems/v2` share one name per item and locale, so saving one
  list can change the other's names.
- `POST /access/administration/emailApproval` fills in defaults the read left out.

**The workflow data export** (`GET /access/data/migration/workflow`) works only while the workflow engine is stopped:
stop it (`POST /admin/workflowengines/status {"engineStatus": 1}`), export, and start it again (`{"engineStatus": 0}`)
**[live]**. The zip holds the workflow tables, including its settings, so keep it like a secret.

Corrections and results from other versions are welcome.
