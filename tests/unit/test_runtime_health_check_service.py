from immich_doctor.core.models import CheckStatus
from immich_doctor.runtime.health.service import RuntimeHealthCheckService


def test_runtime_health_check_returns_pass_report() -> None:
    report = RuntimeHealthCheckService().run()

    assert report.domain == "runtime.health"
    assert report.action == "check"
    assert report.overall_status == CheckStatus.PASS
    assert report.exit_code == 0
