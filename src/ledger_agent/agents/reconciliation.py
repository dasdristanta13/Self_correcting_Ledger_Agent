from ledger_agent.models import AuditRecord, Evidence, Ledger, Patch
from ledger_agent.paths import PathError, get_field, set_field


class PatchRejected(Exception):
    pass


def propose_patches(ledger: Ledger, evidence: list[Evidence]) -> list[Patch]:
    best: dict[str, Patch] = {}
    for ev in evidence:
        try:
            current = get_field(ledger, ev.field)
        except PathError:
            continue
        if current is None or current == ev.value:
            continue
        patch = Patch(path=ev.field, old_value=current, new_value=ev.value,
                      reason="Source invoice evidence", source_page=ev.source.page,
                      source_table=ev.source.table_id, source_row=ev.source.row,
                      confidence=ev.confidence)
        if ev.field not in best or patch.confidence > best[ev.field].confidence:
            best[ev.field] = patch
    return list(best.values())


def check_patch(ledger: Ledger, patch: Patch, threshold: float) -> None:
    try:
        current = get_field(ledger, patch.path)
    except PathError as exc:
        raise PatchRejected(f"field does not exist: {patch.path}") from exc
    if current is None:
        raise PatchRejected(f"field is not set: {patch.path}")
    if current != patch.old_value:
        raise PatchRejected(f"old value mismatch for {patch.path}")
    if patch.source_page is None:
        raise PatchRejected(f"no source evidence for {patch.path}")
    if not patch.new_value.is_finite():
        raise PatchRejected(f"new value is not finite for {patch.path}")
    if not (patch.confidence >= threshold):
        raise PatchRejected(f"confidence {patch.confidence:.2f} below threshold for {patch.path}")


def apply_patches(ledger: Ledger, patches: list[Patch], revision: int,
                  threshold: float) -> tuple[Ledger, list[AuditRecord]]:
    current = ledger
    records: list[AuditRecord] = []
    for p in patches:
        check_patch(current, p, threshold)
        current = set_field(current, p.path, p.new_value)
        records.append(AuditRecord(revision=revision, field=p.path, old_value=p.old_value,
                                   new_value=p.new_value, reason=p.reason, source_page=p.source_page,
                                   source_table=p.source_table, source_row=p.source_row,
                                   confidence=p.confidence))
    return current, records
