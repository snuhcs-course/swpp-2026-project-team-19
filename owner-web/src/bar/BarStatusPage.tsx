import { useRef, useState } from "react";
import { useNavigate } from "react-router";
import { ApiError, fieldErrorMessages, isRetryable } from "../api/errors";
import { OwnerScreen } from "../owner/OwnerScreen";
import { useApplyException, useBar, type OperatingExceptionInput, type OwnedBar } from "../owner/queries";
import { BottomSheet } from "../ui/BottomSheet";
import { Button } from "../ui/Button";
import { TextField } from "../ui/TextField";
import { BarQuery } from "./BarHomePage";
import { characterCount } from "./barInfo";
import { useBarFailure } from "./failures";
import { applyDate, validVacationAtApply } from "./operating";
import { seoulClock } from "./seoulTime";
import { useLeaveGuard } from "./useLeaveGuard";
import { TimeSelect } from "./TimeSelect";
import styles from "./bar.module.css";

type Choice = "closed_today" | "custom_hours" | "vacation";
type Field = "date" | "startDate" | "endDate" | "openTime" | "closeTime" | "note";

/** OwnerManagementHomeScreen.kt `OwnerOperatingQuickScreen`: the three kinds and their apply labels. */
const CHOICES: { value: Choice; label: string; apply: string }[] = [
  { value: "closed_today", label: "오늘 휴무", apply: "휴무 적용" },
  { value: "custom_hours", label: "오늘만 영업시간 변경", apply: "변경 적용" },
  { value: "vacation", label: "기간 임시 휴업", apply: "휴업 적용" },
];

const MAX_NOTE = 100;
const SAME_TIMES = "영업 시작과 종료 시각이 같을 수 없어요.";
const BAD_RANGE = "시작일과 종료일을 다시 확인해 주세요.";

/** Copy for the codes of spec 3.15.6 that the shared field copy (src/api/errors.ts) lacks. */
const FIELD_COPY: Record<string, string> = {
  SAME_OPEN_CLOSE: SAME_TIMES,
  END_BEFORE_START: "종료일은 시작일 이후여야 해요.",
  DATE_IN_PAST: "시작일이 지났어요. 날짜를 다시 골라 주세요.",
  INVALID_TIME: "5분 단위로 골라 주세요.",
};

const sameInput = (a: OperatingExceptionInput, b: OperatingExceptionInput) => JSON.stringify(a) === JSON.stringify(b);

/**
 * /owner/bars/:barId/status: a temporary closure applied at once (spec 3.15.2), as the app's
 * OwnerOperatingQuickScreen. It replaces the bar's current closure, so applying asks first.
 */
export function BarStatusPage({ bar }: { bar: OwnedBar }) {
  const detail = useBar(bar.barId);
  return (
    <OwnerScreen title="영업 상태 변경" backTo={`/bars/${bar.barId}`}>
      <BarQuery query={detail} keepDataOnRefetchError>
        {(data) => <StatusForm barId={data.barId} />}
      </BarQuery>
    </OwnerScreen>
  );
}

function StatusForm({ barId }: { barId: string }) {
  const navigate = useNavigate();
  const apply = useApplyException(barId);
  const [choice, setChoice] = useState<Choice | null>(null);
  // OwnerOperatingQuickScreen: today's changed hours start at 18:00 to 21:30.
  const [openTime, setOpenTime] = useState("18:00");
  const [closeTime, setCloseTime] = useState("21:30");
  const [startDate, setStartDate] = useState("");
  const [endDate, setEndDate] = useState("");
  const [note, setNote] = useState("");
  const [asking, setAsking] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [fieldErrors, setFieldErrors] = useState<Partial<Record<Field, string>>>({});
  // A request whose answer was lost (network failure or 5xx) may have been saved. Applying the same input
  // again sends it unchanged, with its date, even after midnight: spec 3.15.2 answers 200 to the same
  // request, so it is not applied to the next day instead. Any other answer, or a changed input, clears it.
  const unanswered = useRef<OperatingExceptionInput | null>(null);
  const guard = useLeaveGuard(choice !== null || note !== "", apply.isPending);
  const fail = useBarFailure(guard.release);
  // Read when shown; the date that is sent is read again when the owner applies (spec 3.15.2).
  const today = seoulClock().date;

  const noteError = characterCount(note.trim()) > MAX_NOTE ? "고객 안내는 100자 이하여야 해요." : undefined;
  const sameTimes = choice === "custom_hours" && openTime === closeTime;
  const rangeReady = choice !== "vacation" || validVacationAtApply(startDate, endDate, today);
  const ready = choice !== null && !noteError && !sameTimes && rangeReady;

  function choose(next: Choice) {
    setChoice(next);
    setError(null);
    setFieldErrors({});
  }

  function body(date: string): OperatingExceptionInput {
    const trimmed = note.trim() || null;
    if (choice === "closed_today") return { kind: "closed_today", date, note: trimmed };
    if (choice === "custom_hours") return { kind: "custom_hours", date, openTime, closeTime, note: trimmed };
    return { kind: "vacation", startDate, endDate, note: trimmed };
  }

  function confirm() {
    if (apply.isPending || !choice) return;
    const last = unanswered.current;
    unanswered.current = null;
    const again = last && sameInput(last, body("date" in last ? last.date : "")) ? last : null;
    // Otherwise the date is Seoul's today when the owner applies, not when the screen opened (ownerQuickApplyDay).
    const date = applyDate(Date.now());
    if (!again && choice === "vacation" && !validVacationAtApply(startDate, endDate, date)) {
      setAsking(false);
      return setError(BAD_RANGE);
    }
    const sent = again ?? body(date);
    setError(null);
    setFieldErrors({});
    apply.mutate(sent, {
      onSuccess: () => {
        setAsking(false);
        guard.release();
        void navigate(`/bars/${barId}`);
      },
      onError: (failure) => {
        setAsking(false);
        if (isRetryable(failure)) unanswered.current = sent;
        handleFailure(failure);
      },
    });
  }

  function handleFailure(failure: unknown) {
    if (failure instanceof ApiError && failure.code === "VALIDATION_FAILED") {
      const codes = failure.fieldErrors.map((item) => item.code);
      if (codes.includes("DATE_NOT_TODAY")) {
        // Spec 3.15.6: the date changed (midnight passed, or the device clock is off); apply again.
        return setError("날짜가 바뀌었어요. 확인한 뒤 다시 적용해 주세요.");
      }
      const messages = fieldErrorMessages(failure);
      const byField: Partial<Record<Field, string>> = {};
      for (const item of failure.fieldErrors) {
        const field = item.path as Field;
        if (["date", "startDate", "endDate", "openTime", "closeTime", "note"].includes(field) && !byField[field]) {
          byField[field] = FIELD_COPY[item.code] ?? messages[item.path];
        }
      }
      setFieldErrors(byField);
      return setError(Object.keys(byField).length ? "입력한 내용을 확인해 주세요." : (messages[""] ?? "입력한 내용을 확인해 주세요."));
    }
    setError(fail(failure));
  }

  const current = CHOICES.find((item) => item.value === choice);
  return (
    <form
      onSubmit={(event) => {
        event.preventDefault();
        if (ready) setAsking(true);
      }}
    >
      <fieldset className={[styles.screen, styles.fieldset].join(" ")} disabled={apply.isPending}>
        <div className={styles.choices} role="radiogroup" aria-label="임시 휴무 종류">
          {CHOICES.map((item) => (
            <button
              key={item.value}
              type="button"
              role="radio"
              aria-checked={choice === item.value}
              className={[styles.choice, choice === item.value ? styles.choiceSelected : ""].join(" ")}
              onClick={() => choose(item.value)}
            >
              <span>{item.label}</span>
              <span aria-hidden="true">›</span>
            </button>
          ))}
        </div>

        {choice === "custom_hours" ? (
          <section className={styles.section} aria-label="오늘 영업시간">
            <h2 className={styles.sectionTitle}>오늘 영업시간</h2>
            <TimeSelect label="영업 시작" value={openTime} onChange={(value) => value && setOpenTime(value)} error={fieldErrors.openTime} />
            <TimeSelect label="영업 종료" value={closeTime} onChange={(value) => value && setCloseTime(value)} error={fieldErrors.closeTime} />
            {closeTime < openTime ? <p className={styles.hint}>종료는 다음 날 {closeTime}이에요.</p> : null}
            {sameTimes ? (
              <p className={styles.error} role="alert">
                {SAME_TIMES}
              </p>
            ) : null}
          </section>
        ) : null}

        {choice === "vacation" ? (
          <section className={styles.section} aria-label="임시 휴업 기간">
            <h2 className={styles.sectionTitle}>임시 휴업 기간</h2>
            <TextField
              label="시작일"
              type="date"
              value={startDate}
              min={today}
              error={fieldErrors.startDate}
              onChange={(event) => {
                const value = event.currentTarget.value;
                setStartDate(value);
                // OwnerOperatingQuickComponents.kt `updateQuickVacationDates`: an end before the new start is cleared.
                if (endDate && value && endDate < value) setEndDate("");
                setFieldErrors(({ startDate: _, ...rest }) => rest);
              }}
            />
            <TextField
              label="종료일"
              type="date"
              value={endDate}
              min={startDate || today}
              error={fieldErrors.endDate}
              onChange={(event) => {
                setEndDate(event.currentTarget.value);
                setFieldErrors(({ endDate: _, ...rest }) => rest);
              }}
            />
          </section>
        ) : null}

        {choice ? (
          <TextField
            label="고객 안내 (선택)"
            value={note}
            placeholder="예: 내부 사정으로 조기 마감합니다"
            error={noteError ?? fieldErrors.note}
            // OwnerOperatingQuickScreen: one line of at most 100 characters.
            onChange={(event) => {
              setNote(event.currentTarget.value.replace(/[\r\n]/g, ""));
              setFieldErrors(({ note: _, ...rest }) => rest);
            }}
          />
        ) : null}

        {error ? (
          <p className={styles.error} role="alert">
            {error}
          </p>
        ) : null}
        {current ? (
          <Button type="submit" busy={apply.isPending} disabled={!ready}>
            {current.apply}
          </Button>
        ) : null}
      </fieldset>

      <BottomSheet open={asking} title="임시 휴무를 적용할까요?" onClose={() => !apply.isPending && setAsking(false)}>
        <p className={styles.sheetText}>지금 설정된 임시 휴무가 있으면 이 내용으로 바뀌어요.</p>
        <div className={styles.actions}>
          <Button variant="secondary" disabled={apply.isPending} onClick={() => setAsking(false)}>
            계속 편집
          </Button>
          <Button busy={apply.isPending} onClick={confirm}>
            적용하기
          </Button>
        </div>
      </BottomSheet>

      {/* OwnerInfoHtmlV4Screen.kt: the same discard sheet as the info form. */}
      <BottomSheet open={guard.asking} title="변경을 취소할까요?" onClose={guard.stay}>
        <p className={styles.sheetText}>저장하지 않은 수정 사항은 사라집니다.</p>
        <div className={styles.actions}>
          <Button variant="secondary" onClick={guard.stay}>
            계속 편집
          </Button>
          <Button onClick={guard.leave}>변경 취소</Button>
        </div>
      </BottomSheet>
    </form>
  );
}
