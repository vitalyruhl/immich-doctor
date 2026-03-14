from immich_doctor.core.models import CheckStatus, ValidationReport, ValidationSection
from immich_doctor.reports.text_writer import render_text_report


def test_default_db_index_text_output_is_compact() -> None:
    report = ValidationReport(
        domain="db.performance.indexes",
        action="check",
        summary="Database index checks completed.",
        checks=[],
        sections=[
            ValidationSection(
                name="INDEX_LIST",
                status=CheckStatus.PASS,
                rows=[
                    {
                        "schemaname": "public",
                        "tablename": "face_search",
                        "indexname": "face_index",
                        "indexdef": (
                            "CREATE INDEX face_index ON public.face_search USING hnsw (embedding)"
                        ),
                    }
                ],
            ),
            ValidationSection(
                name="UNUSED_INDEXES",
                status=CheckStatus.WARN,
                rows=[
                    {"table_name": "a", "index_name": "a_idx", "idx_scan": 0},
                    {"table_name": "b", "index_name": "b_idx", "idx_scan": 0},
                    {"table_name": "c", "index_name": "c_idx", "idx_scan": 0},
                    {"table_name": "d", "index_name": "d_idx", "idx_scan": 0},
                ],
            ),
            ValidationSection(
                name="LARGE_INDEXES",
                status=CheckStatus.PASS,
                rows=[
                    {
                        "table_name": "face_search",
                        "index_name": "face_index",
                        "index_size": "0 bytes",
                    },
                    {
                        "table_name": "assets",
                        "index_name": "assets_pkey",
                        "index_size": "16 kB",
                    },
                ],
            ),
            ValidationSection(name="INVALID_INDEXES", status=CheckStatus.PASS),
            ValidationSection(name="MISSING_FK_INDEXES", status=CheckStatus.PASS),
        ],
    )

    output = render_text_report(report)

    assert "CREATE INDEX face_index" not in output
    assert "index_size=0 bytes" not in output
    assert "index_name=d_idx" not in output
    assert "Hint: Use --verbose for full diagnostic details." in output
    assert "INDEX_LIST: 1 indexes found." in output


def test_verbose_db_index_text_output_keeps_full_details() -> None:
    report = ValidationReport(
        domain="db.performance.indexes",
        action="check",
        summary="Database index checks completed.",
        checks=[],
        sections=[
            ValidationSection(
                name="INDEX_LIST",
                status=CheckStatus.PASS,
                rows=[
                    {
                        "schemaname": "public",
                        "tablename": "face_search",
                        "indexname": "face_index",
                        "indexdef": (
                            "CREATE INDEX face_index ON public.face_search USING hnsw (embedding)"
                        ),
                    }
                ],
            ),
            ValidationSection(
                name="LARGE_INDEXES",
                status=CheckStatus.PASS,
                rows=[
                    {
                        "table_name": "face_search",
                        "index_name": "face_index",
                        "index_size": "0 bytes",
                    },
                ],
            ),
        ],
    )

    output = render_text_report(report, verbose=True)

    assert "CREATE INDEX face_index" in output
    assert "0 bytes" in output
    assert "Hint: Use --verbose for full diagnostic details." not in output
