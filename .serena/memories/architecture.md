# Architecture Notes

- Service-layer workflow logic belongs in `immich_doctor/services` or domain packages, not in UI components or route handlers.
- API routes should adapt service results into response models and keep business workflow decisions out of the transport layer.
- Reports and persistent workflow artifacts are part of traceability; avoid replacing them with UI-only state.
- Repair and quarantine flows must stay narrow, explicit, and reversible where the existing model requires it.
- Catalog-backed consistency state is a canonical direction; avoid adding competing ad-hoc scan state unless a migration plan exists.
- Frontend stores/components should consume typed API contracts from `ui/frontend/src/api/types` and avoid duplicating backend rules.