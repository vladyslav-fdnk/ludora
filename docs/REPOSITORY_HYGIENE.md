# Repository hygiene review

Reviewed against the current backend, bot, Compose topology, dependency
manifests, tests, and documentation.

## Findings

| Area | Finding | Why it matters / recommendation |
| --- | --- | --- |
| Documentation | README and architecture text described payments as local-only although Stripe Checkout and signed webhooks are implemented. | This could cause incorrect deployment and client behavior. The project docs now describe the actual asynchronous Stripe flow and configuration. |
| TODO/FIXME | Placeholder TODOs remain in `games/apps.py`, `orders/apps.py`, `payments/apps.py`, and `bot/app/services/__init__.py`. The model/provider work they mention already exists. | They are outdated navigation noise. Remove them in a production-code cleanup; no behavior change is needed. |
| TODO/FIXME | Compose contained a future-Nginx TODO. | It was directionally valid, but deployment limitations are clearer as documentation than an indefinite TODO. The comment and Docker docs now state that Nginx is not active. |
| Dead code | Empty Django scaffolding modules and the empty bot `services` package are importable structure, not proven runtime defects. The legacy direct-order fields and auth aliases are used compatibility paths. | Do not delete them solely because they are small or transitional. Confirm downstream compatibility before removing legacy paths. |
| Imports | Ruff's configured `E`, `F`, and `I` checks pass for the repository. | No unused-import change is indicated. |
| Dependencies | Each direct dependency has a current role: Django/DRF/auth/filter/schema, PostgreSQL, image handling, Celery/Redis, Stripe, test tooling, aiogram, and HTTPX. Both lockfiles contain the matching project dependency sets. | No dependency can be removed confidently from static inspection. Keep runtime tools such as Ruff in a dev group in a future manifest-only cleanup if production image size matters. |
| Duplication | Payment creation is represented in both `create_payment` and the backward-compatible `pay_order` command. | The shared rules currently differ: one creates hosted checkout, while the other also confirms the local provider. Consolidating internals could reduce drift, but changing it is production refactoring and is outside this documentation update. |
| Queries | List, cart, order history/detail, admin, fulfilment, and email paths already use targeted `select_related`/`prefetch_related`. `ProductDetailAPIView` serializes `platform` and `categories` without eager loading. | A single-object detail currently pays at most two extra queries, so this is low priority; adding `select_related("platform").prefetch_related("categories")` would make the access pattern explicit. Query-count tests should accompany the change. |
| Type hints | Domain services and payment/webhook boundaries are substantially typed; Django views, serializers, models, and some bot handlers remain partially typed. | Add types first at public service/helper boundaries. Avoid annotating framework overrides merely for coverage. |
| Docstrings | Transactional services and provider/webhook abstractions have useful docstrings; many conventional framework classes do not. | Add docstrings where they describe invariants, security boundaries, or non-obvious state transitions, not boilerplate CRUD behavior. |
| Naming | The code uses both “fulfilment/licence” prose and `fulfill`/`license` domain identifiers; the product also retains “game key store” package descriptions. | Keep API/model identifiers stable. Use “fulfilment” and “license key” consistently in project documentation; rename package descriptions only with a deliberate branding change. |
| OpenAPI naming | Schema validation succeeds but drf-spectacular warns that multiple fields named `status` produce automatically suffixed enum component names. | Add explicit `ENUM_NAME_OVERRIDES` when stable generated enum names matter to SDK consumers. This is contract cleanup, not a runtime defect. |
| Inline comments | A non-English arrow comment remains beside the admin URL in `config/urls.py`. | It is stale and inconsistent with the codebase language. Remove it during the next production-code cleanup. |

## Verification scope

Ruff, Django system checks, migration consistency, lockfile checks, OpenAPI
validation, 259 backend tests, and 91 bot tests completed successfully in
Docker. OpenAPI reported the two enum naming warnings described above. The
workspace's virtual environments may be container-owned, so Docker is the
reproducible validation path.

This review does not claim that static inspection proves the absence of all
dead code or redundant transitive packages. A stricter future audit can add
runtime coverage analysis and a dependency checker, but their findings should
be reviewed manually because Django imports apps, models, admin modules, and
management integrations dynamically.
