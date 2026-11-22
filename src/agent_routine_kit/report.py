"""Render a report as stable JSON and as text with the same findings."""

from __future__ import annotations

import json


def render_json(report):
    return json.dumps(report, indent=2, sort_keys=True) + "\n"


def render_text(report):
    lines = [
        "agent-routine-kit",
        f"report_version: {report['report_version']}",
        f"contract_version: {report['contract_version']}",
        f"schema_version: {report['schema_version']}",
        f"rules_version: {report['rules_version']}",
        f"kit_version: {report['kit_version']}",
        f"all_clear: {str(report['all_clear']).lower()}",
        f"coverage_status: {report['coverage']['status']}",
        f"routine_count: {report['summary']['routine_count']}",
        f"finding_count: {report['summary']['finding_count']}",
    ]
    for item in report["findings"]:
        subjects = ",".join(item["subjects"])
        fields = ",".join(item["fields"])
        detail = str(item["detail"]).replace("\n", " ")
        lines.append(
            "finding: {code} severity={severity} subjects={subjects} reason={reason} "
            "blocks={blocks} fields={fields} detail={detail}".format(
                code=item["code"],
                severity=item["severity"],
                subjects=subjects,
                reason=item["reason"],
                blocks=str(item["blocks_all_clear"]).lower(),
                fields=fields,
                detail=detail,
            )
        )
    for routine in report["routines"]:
        lines.append(
            "routine: {id} delivery={delivery} schedule={schedule} scope={scope}".format(
                id=routine["id"],
                delivery=routine["delivery_status"],
                schedule=routine["schedule_status"],
                scope=routine["scope_status"],
            )
        )
    for pair in report["pairs"]:
        left, right = pair["routines"]
        lines.append(
            "pair: {left},{right} duplicate={duplicate} schedule={schedule} auth_policy={auth}".format(
                left=left,
                right=right,
                duplicate=pair["duplicate"],
                schedule=pair["schedule"],
                auth=pair["auth_policy"],
            )
        )
    return "\n".join(lines) + "\n"
