import json
from pathlib import Path

from job_store_contract import JobStoreContract

from ledger_agent.graph import ReconciliationResult
from ledger_agent.storage.base import Job
from ledger_agent.storage.memory import InMemoryJobStore


class TestInMemoryStore(JobStoreContract):
    def make_store(self):
        return InMemoryJobStore()


def test_example_job_fixture_matches_models():
    raw = json.loads((Path(__file__).parents[2] / "contracts" / "example-job.json").read_text(encoding="utf-8"))
    job = Job.model_validate(raw)
    result = ReconciliationResult.model_validate(job.result)
    assert result.status.value == "RECONCILED" and result.corrections[0].field == "items[line_01].amount"
