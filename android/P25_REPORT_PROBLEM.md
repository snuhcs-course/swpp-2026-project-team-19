# I5-P25 — 문제 신고하기

## Scope and behavior

Android only, based on `main` after Firebase PR #216 and location PR #218 were merged.
Branch: `feature/i5-p25-report-problem`. No backend contract, AI, owner web or new dependency.

The user approved changing the existing account row to `문제 신고하기`, retaining its
position and appearance. Tapping opens the published Google Form in an external
browser. Guest and signed-in users use the same row. No new screen, retry button,
automatic submission or submission-success message is introduced.

A browser exception only calls the existing top-toast callback with
`문제 신고 폼을 열지 못했어요. 브라우저를 확인해 주세요.` and stops the action.
The user retries by tapping the same row. Successful launches have a one-second
monotonic debounce, retained by the destination ViewModel/SavedStateHandle across
configuration changes. Failed launches allow immediate explicit retry. Returning,
resuming or recomposing never automatically launches the form.

## Form and privacy boundary

Published destination:
https://docs.google.com/forms/d/e/1FAIpQLSfVkgDygNzY2pL45XXu3H10izoblKCRa5LXaIiOS-PARnB1dg/viewform

| Field | Google Forms entry | App behavior |
|---|---|---|
| 문의 유형 | `1151544135` | User input; omitted from URL |
| 문제가 발생한 기능 | `399876014` | User input; omitted from URL |
| 문제 또는 문의 내용 | `777503106` | User input; omitted from URL |
| 문제가 발생한 시점 | `57279747` | User input; omitted from URL |
| 앱 버전 | `258607485` | Installed package versionName and long versionCode |
| 사용 기기 및 Android 버전 | `604351798` | Build.MANUFACTURER, MODEL and VERSION.RELEASE |

`Uri.Builder` encodes the two diagnostic values; the only additional query
parameter is `usp=pp_url`. Account data, tokens, coordinates, address, searches,
logs, stack traces, persistent identifiers and report contents are not read or
added. The form remains editable by the user before submission.

`ReportProblemOpened` is emitted by the ViewModel only after `startActivity`
accepts the action. The existing ConsentTelemetry and build gate control delivery.
Failed/debounced launches do not emit it. It measures browser handoff, not form
rendering or report submission. Firebase/NoOp implementation is reused unchanged.

## Verification record

- 2026-11-26: anonymous HTTP GET returned 200 for the official published form.
- A GET with synthetic diagnostic values returned exactly those two field IDs in
  the form's prefill response; an ampersand and parentheses were retained correctly.
  No response was submitted. The four user-input IDs match the published form.
- The public form shows no name/email/phone question and offers optional Google
  sign-in for saving progress. On 2026-11-26 the user confirmed the owner-side
  settings: email collection disabled, no sign-in/organization account restriction.
  The user subsequently confirmed a test submission and receipt with both diagnostic fields.
- Automated verification (2026-11-26): `:app:assembleDebug`,
  `:app:testDebugUnitTest`, `:app:compileDebugAndroidTestKotlin` succeeded with
  `-PBOTTLEMAP_FIREBASE_ENABLED=false`. 784 tests passed, zero failures/errors/skips,
  including six focused reporting tests and three account-screen tests.
- `:app:lintDebug` with `-PBOTTLEMAP_FIREBASE_ENABLED=false` succeeded:
  0 errors, 86 warnings, 4 hints. P25 adds three advisory warnings: the test-default
  SavedStateHandle constructor (two reports) and the existing-style Uri.parse call.
  Production supplies createSavedStateHandle from the navigation destination.
- Initial verification found an application-Context browser launch missing
  `FLAG_ACTIVITY_NEW_TASK`; it was corrected, and the runtime-launch test plus
  the full suite now pass. No test was removed, skipped or weakened.
- Galaxy S23 QA: the user reported 15 passing items (1, 2, 4–12, 15–18), including
  real test-response receipt, guest/signed-in navigation, state preservation and
  Firebase DebugView consent ON/OFF behavior. No failures were reported.
- At the user's request, items 3, 13 and 14 use automated substitute evidence:
  runtime package version -> form URL, ActivityNotFoundException -> existing notice
  only, and browser restoration -> successful same-row retry. Physical no-browser
  behavior and visual version comparison are not claimed as manually tested.
- QA acceptance rerun: `:app:testDebugUnitTest --tests '*ProblemReport*'
  -PBOTTLEMAP_FIREBASE_ENABLED=false` passed all 9 tests after strengthening the
  account-screen test to restore the handler and succeed via the same row.
- Read-only ADB inspection found installed versionName `0.1.0`, versionCode `1`.
  The runtime test deliberately uses a different name and a long versionCode to
  verify dynamic package reading and rule out a hardcoded example value.
- Schedule: P25 Started; only `Schedule!K294` changed. Work-time and date fields untouched.
- Published as a Draft PR from this dedicated feature branch at the user's request.
  User requested Ready for Review after the accepted substitute checks pass.
  Original code-head CI passed Android lint/unit tests/debug APK and owner Compose;
  AI tests were correctly skipped for Android-only changes. No review comments were
  present at QA acceptance. New-head CI and human review remain separate gates.

## Galaxy S23 installation

After the branch has been pushed, run these commands from the repository root in
this order. Do not pull a local branch before a matching remote branch exists.

```powershell
git fetch origin
git switch feature/i5-p25-report-problem
git pull --ff-only
.\gradlew.bat :app:installDebug "-PBOTTLEMAP_API_BASE_URL=https://bottlemap.o-r.kr/"
```

For Firebase verification, use the existing ignored Firebase configuration and
append `"-PBOTTLEMAP_TELEMETRY_DEBUG_ENABLED=true"` and
`"-PBOTTLEMAP_RELEASE_CHANNEL=dev"` to the installation command. Enable the app's
optional `사용 기록 보내기` consent, and route this package to DebugView using the
existing `android/FIREBASE_TELEMETRY.md` instructions. An ordinary debug build or
a build without Firebase configuration sends no events even if the toggle is on.
Do not clear application data. The agent did not reinstall or interact with the
device UI; the only device operation was a read-only installed-version inspection.

## Copyable manual QA result

The record below combines the user's actual device results with the explicitly
accepted automated substitutes, identified on items 3, 13 and 14.
Copy this entire block and replace `[ ]` with `[x]` (pass) or `[!]` (fail).
Perform the deliberate test submission only once and have the form owner verify
receipt; do not put personal information in the test report.

```text
Galaxy S23 P25 실기기 검증 결과
브랜치: feature/i5-p25-report-problem
기기: Galaxy S23

[x] 1. 앱을 열면 기존 Customer 검색 화면이 표시된다. 검색·바 상세를 확인한다.
[x] 2. 게스트로 내 정보 → 문제 신고하기를 누르면 공식 BottleMap Google Form이 열린다.
[x] 3. [자동 대체 검증] 앱 버전 필드가 설치한 APK의 versionName (versionCode)와 일치한다.
[x] 4. 기기 필드가 실제 제조사·모델·Android 버전과 일치한다.
[x] 5. 문의 유형·발생 기능·내용·발생 시점에 예시 값이 자동으로 들어 있지 않다.
[x] 6. Google 로그아웃/시크릿 상태에서도 로그인 없이 작성·제출할 수 있다.
[x] 7. 폼 소유자 설정: 이메일 자동 수집 꺼짐·로그인/조직 제한 없음 — 2026-11-26 사용자 확인.
[x] 8. 자동 입력 값을 수정할 수 있다. 개인정보 없는 테스트 신고 1건을 직접 제출했다.
[x] 9. 폼 소유자가 응답 탭에서 해당 테스트 신고와 두 진단 필드의 저장을 확인했다.
[x] 10. 제출하지 않고 브라우저에서 뒤로 돌아와도 성공 메시지가 뜨지 않고 내 정보가 유지된다.
[x] 11. 로그인 후 같은 경로로 폼을 열고 돌아와도 로그인·계정·기존 탐색 상태가 유지된다.
[x] 12. 문제 신고하기를 빠르게 여러 번 눌러도 폼이 중복 실행되지 않는다.
[x] 13. [자동 대체 검증] 브라우저 핸들러가 없는 QA 환경에서 상단 toast만 나오고 새 페이지/재시도 버튼은 없다.
[x] 14. [자동 대체 검증] 브라우저를 다시 사용 가능하게 한 뒤 같은 문제 신고하기를 누르면 정상 실행된다.
[x] 15. 앱 백그라운드/재개·화면 재생성 후 폼이나 이벤트가 자동 재실행되지 않는다.
[x] 16. 사용 기록 보내기 ON인 검증 빌드에서 DebugView의 report_problem_opened가 실제 열기당 1회 보인다.
[x] 17. 사용 기록 보내기 OFF에서는 폼은 열리지만 해당 이벤트가 수집되지 않는다.
[x] 18. 시스템 Back·상단 Back·검색·지도·바 상세·로그인/로그아웃 흐름이 정상이다.

메모:
```

The app is portrait-only; configuration/state handling is also covered by local
ViewModel tests. Missing-handler/launch-exception branches are covered with test
doubles so a user's daily browser need not be disabled for automated testing.
Form privacy, real-device prefill/return behavior, response receipt and Firebase
Console evidence were confirmed by the user, except for the three explicitly
accepted automated substitutes above. Human review and final PR disposition remain
pending; no merge or Schedule completion is implied by Ready for Review.
