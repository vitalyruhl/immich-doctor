from immich_doctor.core.models import CheckStatus
from immich_doctor.services.health_service import HealthService


def test_health_ping_returns_pass_report() -> None:
    report = HealthService().run_ping()

    assert report.command == "health ping"
    assert report.overall_status == CheckStatus.PASS
    assert report.exit_code == 0
