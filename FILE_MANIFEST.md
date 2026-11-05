# AllSafe AI Trading — Independent Verification File Manifest (`FILE_MANIFEST.md`)

- **Audit Date**: November 5, 2026
- **Repository**: `https://github.com/sanju245/allsafe-ai-trading`
- **Verification Branch**: `audit/landing-auth-integration-verification`

| File Path | Category | Lines | Size (Bytes) | SHA-256 Checksum |
| :--- | :--- | ---: | ---: | :--- |
| `.github/workflows/ci.yml` | CI | 56 | 1677 | `2e04cf563292bc26b0bb5369ec7f6fab95e93923f513930c5b1551cb3870db17` |
| `apps/api/app/config.py` | Source | 105 | 4945 | `42817f110ccd9fbc3606048851c2eac97988f3f9b0e165b5f7c9e1f382b35f6a` |
| `apps/api/app/auth/models.py` | Source | 235 | 7244 | `746be2d30190943e681c55e0585102ceb33ba396b70e889927305fe0e79e43ae` |
| `apps/api/app/auth/security.py` | Source | 749 | 29217 | `526dec0458b350319cab56559cdb16abcc49dd7f86f4d590f41eac54af565ff5` |
| `apps/api/app/auth/store.py` | Source | 1427 | 61374 | `209759b187149beca657a49488f50170146db8ce502ef4f101065668f61d0cf7` |
| `apps/api/app/routers/auth.py` | Source | 277 | 9630 | `95e85b1b1ac23c578fdae27204cd8e3aef5b0e0e961aadd7fa58ebfb0a92b74b` |
| `apps/api/app/routers/admin.py` | Source | 337 | 12254 | `87ba9e46c8a7a8448494ae2914ff02383642067a78ce8f2d07e3d8500aab8771` |
| `apps/api/tests/test_auth_and_admin.py` | Test | 452 | 16841 | `67d0324ea3bd9a3a751e5e20d2dcc03fa462c63296d3c98571b5a85d7d354baa` |
| `apps/api/tests/test_independent_security_revalidation.py` | Test | 442 | 17621 | `d245bbf5edf413043bfb5c7993de66a0c2c3445e6883444010d2264caa32dc3d` |
| `apps/web/src/lib/clientApi.ts` | Source | 91 | 2572 | `fa1a563bf16feb885a631c178010eece0c0e2c41699c6f92c51af2386d5daf76` |
| `apps/web/src/lib/api.ts` | Source | 67 | 1846 | `58f6b791cec36d1838aabb3d5242c2bba5d82a20d53918513407003da26a52e5` |
| `apps/web/src/lib/indianMarketStatus.ts` | Source | 649 | 22024 | `8a75fd4a8f93da7265a8539e2670fff8166a30266ffd149b35434841e74f520a` |
| `apps/web/src/components/auth/AuthProvider.tsx` | Source | 217 | 5470 | `324bd76c4bf0cbf7e89d5676bfbba08085105d4b5276f12adb62fe68bafab466` |
| `apps/web/src/components/auth/DashboardAccessGate.tsx` | Source | 136 | 4896 | `0e49a9ea8cd03345211761a613852e069e17ebaa14e7cf78fb67cb82ecc11de2` |
| `apps/web/src/components/landing/LiveIstClock.tsx` | Source | 95 | 3222 | `5dea6e858e8e322bc8a3475ca1c99e2137d4a01374c07d16cbd89cb9847a1d02` |
| `apps/web/src/components/landing/IndianMarketStatusBadge.tsx` | Source | 187 | 6531 | `12ccba566c795e40d276e874de2a448648fe955bb263e73b157b5170eeb25fb6` |
| `apps/web/src/components/landing/BullBearHeroArena.tsx` | Source | 483 | 17735 | `798a2cc1d71fa5d1f357e3065af994ad089e928fdda584a2e4a2f907338d061f` |
| `apps/web/src/components/landing/ScrollReveal.tsx` | Source | 139 | 3913 | `41690501d54e4f8e909a2fccc6d463304a8cb61e56838e5d50be67ea96b34e06` |
| `apps/web/src/components/landing/LandingPage.tsx` | Source | 2111 | 101463 | `a3e4b168c5de7b9f596911ee9bade6752a65372096f948c53b89cdcfcac82e8b` |
| `apps/web/src/components/landing/WhatWeDonePage.tsx` | Source | 505 | 23364 | `7b207b1b217f2eec97fa9a3a6b2fa588c929d9d851f5a780f2e51fdacaf201d7` |
| `apps/web/src/app/page.tsx` | Source | 17 | 481 | `5ad9cbf8a9eb5920333551fed31a0ac4b65aeca1af6f6820153fb01574825f64` |
| `apps/web/src/app/what-we-done/page.tsx` | Source | 23 | 740 | `7d9fafebc81b07a8f5b7811ca79c7e5cb2012cc991ed227e046f7f8cddb2c2a4` |
| `apps/web/src/app/login/page.tsx` | Source | 204 | 7693 | `cb314b0e59f180584d345ce13ed02264ad5a0c5617e45614a9a55d2bd2294a4b` |
| `apps/web/src/app/admin/login/page.tsx` | Source | 199 | 7612 | `1ff959b49e7a178f7c876aa940a6ec03a35dfcd8ba1ffceafdd78df4be594b35` |
| `apps/web/src/app/admin/page.tsx` | Source | 835 | 38117 | `dd43a97a983bb152ab68094d5c6ed662a951b061a6c4715a0cb2246a95900249` |
| `apps/web/src/app/terminal/page.tsx` | Source | 75 | 3641 | `8288fc457d3e511c4c3609cc3e918f0bfba4b2db9b7bea2face8424bf1b04513` |
| `apps/web/src/app/account/page.tsx` | Source | 211 | 9090 | `6387a8aea500dd01a7c426b1c1a1df77b45fce57e1302f6d718560a84bbc7d22` |
| `apps/web/src/app/globals.css` | Source | 202 | 4134 | `04a981b032a632175c0b4f0e365664e94e9f298e9e61917af556247ce97f95a0` |
| `apps/web/tests/marketData.test.mjs` | Test | 1380 | 48470 | `e9fa66bc11968803e4652a13af969a05bcadc8e247069c7ca3cd99f27b149880` |
| `apps/web/tests/landingPage.test.mjs` | Test | 312 | 12502 | `8fa14f340a6c817c34dade652200e1893aa5a5e2faa1cb2382c030b2a9c7c887` |
| `apps/web/tests/portalIntegrationAndSecurity.test.mjs` | Test | 127 | 5698 | `556aeaac790dc30004a91d42724e49b080ab69c6400c5cba3fc0a02b6a9dc9ea` |
| `supabase/migrations/20261101000001_auth_users_super_admin_and_audit.sql` | Source | 197 | 9149 | `92d2beb016a7d0ab1fe4f76d8b03a697f8b280bd846fc230ab95bce544d19cfa` |
| `INDEPENDENT_VERIFICATION_REPORT.md` | Report | 41 | 7345 | `3b0a73753cd942eff54b10aea70a6607b552365955283405e71bc63cba4b8493` |
| `SECURITY_AUDIT_REVALIDATION_REPORT.md` | Report | 19 | 4980 | `5303b7152525c3a5c8da7d07fd87a1974a98d4c8937f57c493d26e66ca5950e6` |
| `LANDING_PAGE_AUTH_INTEGRATION_REPORT.md` | Report | 29 | 4029 | `05c840c5e2113393f9444365a75a5f220e0f83a60efed86ccd5ade1cbb437807` |
| `ADMIN_CUSTOMER_PORTAL_VERIFICATION_REPORT.md` | Report | 17 | 2555 | `98e553ce8562cc0798ab9694bdd7bd00ec3b7f861b802ca1970dfa5fdf068c0a` |
| `CI_BUILD_VERIFICATION_REPORT.md` | Report | 56 | 5037 | `bb5a912d815c732811373a29bdcca1dd9845b1be088dd99c346795b9ea270b4a` |
| `TEST_EVIDENCE_REPORT.md` | Report | 174 | 9344 | `b62990db8d259d3e1cff147df437875f3ddb82faf2be090c50a5b71d046a4099` |
| `KNOWN_LIMITATIONS_AND_RESIDUAL_RISKS.md` | Report | 13 | 3387 | `14dea1897d691b75a46ea229fa40890d4e82396b2e1b345c31d07e72f90b428d` |
| `HANDOVER_REPORT.md` | Report | 47 | 2730 | `b91cd1202f6b3aacc6f7c51b9394c60e6fa7dbfb945b19d6d5b16e8c942d8fb5` |
