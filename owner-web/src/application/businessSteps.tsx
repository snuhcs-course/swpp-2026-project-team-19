import { useRef, useState } from "react";
import { ApiError, errorMessage, fieldErrorMessages } from "../api/errors";
import { useSession } from "../auth/SessionProvider";
import { IMAGE_RULES, ImagePrepareError, prepareImage } from "../images/prepare";
import { TextField } from "../ui/TextField";
import { checkBusiness, readCertificate } from "./api";
import { useApplication } from "./ApplicationProvider";
import { CenterContent, DigitsField, ErrorText, Hint, Question, StepFrame, SummaryRow } from "./parts";
import { formatResetTime } from "./resetTime";
import {
  businessDigits,
  businessVerificationIsCurrent,
  businessVerificationKey,
  formatBusinessNumber,
  openingDateFromInput,
  registrationPrecheckError,
  validBusinessRegistrationNumber,
  validOpeningDate,
} from "./rules";
import styles from "./application.module.css";

// The business steps of android/.../ui/owner/OwnerOnboardingScreen.kt: INTRO, METHOD, READING, BN, REP,
// DATE, BIZCHECK and VERIFIED, with the copy of the app.

export function IntroStep() {
  const { go } = useApplication();
  const steps = [
    ["사업자 정보 확인", "사업자등록번호, 대표자 성명, 개업일"],
    ["매장 정보 입력", "이름, 사진, 주소, 연락처"],
    ["메뉴판 사진 올리기", "최대 15장"],
    ["운영팀 승인", "승인 전에는 손님에게 보이지 않아요"],
  ];
  return (
    <StepFrame step="intro" action={{ label: "시작하기", enabled: true, onClick: () => go("method") }}>
      <Question title={"매장 등록은\n이렇게 진행돼요"} subtitle="10분 정도 걸려요. 중간에 멈춰도 입력한 내용은 남아 있어요." />
      <ol className={styles.list}>
        {steps.map(([title, text], index) => (
          <li key={title} className={styles.card}>
            <p className={styles.cardTitle}>
              {index + 1}. {title}
            </p>
            <p className={styles.cardText}>{text}</p>
          </li>
        ))}
      </ol>
      <p className={styles.cardTitle}>미리 준비해 주세요</p>
      <Hint>사업자등록증, 가게 사진 1장, 메뉴판 사진</Hint>
    </StepFrame>
  );
}

function ocrFailure(error: unknown): string {
  if (error instanceof ImagePrepareError) return `${error.message} 직접 입력해도 돼요.`;
  if (error instanceof ApiError && error.code === "RATE_LIMITED") {
    const reset = formatResetTime(error.details?.retryAfter);
    return `오늘 사진으로 읽기는 5번까지 할 수 있어요.${reset ? ` ${reset}부터 다시 쓸 수 있어요.` : ""} 직접 입력해 주세요.`;
  }
  if (error instanceof ApiError && error.code === "OCR_UNAVAILABLE") return "지금은 사진을 읽을 수 없어요. 직접 입력해 주세요.";
  return "사업자등록증을 읽지 못했어요. 직접 입력해 주세요.";
}

export function MethodStep() {
  const { api } = useSession();
  const { update, go, setNotice, startReading, finishReading } = useApplication();
  const picker = useRef<HTMLInputElement>(null);

  // Reads the certificate (spec 3.11.12) and fills the fields to check; nothing is submitted unseen.
  async function read(file: File) {
    update({ inputMethod: "photo" });
    setNotice("check", null);
    const run = startReading();
    go("reading");
    let reading: Awaited<ReturnType<typeof readCertificate>>;
    try {
      const image = await prepareImage(file, IMAGE_RULES.certificate);
      reading = await readCertificate(api, image);
    } catch (error) {
      if (finishReading(run)) {
        setNotice("check", ocrFailure(error));
        go("check", { replace: true });
      }
      return;
    }
    // The owner left the reading screen meanwhile (e.g. to type the values): what they type stays.
    if (!finishReading(run)) return;
    update((draft) => ({
      ...draft,
      businessNumber: reading.businessRegistrationNumber ? businessDigits(reading.businessRegistrationNumber) : draft.businessNumber,
      representativeName: reading.representativeName ?? draft.representativeName,
      openingDate: reading.openingDate ?? draft.openingDate,
      proposedBarName: reading.businessName ?? draft.proposedBarName,
      address: reading.address ?? draft.address,
    }));
    go("check", { replace: true });
  }

  return (
    <StepFrame step="method">
      <Question title={"사업자등록증으로\n한 번에 채울까요?"} subtitle="사진을 찍으면 사업자등록번호, 대표자 성명, 개업일을 읽어 채워 드려요." />
      <div className={styles.choices}>
        <button type="button" className={styles.choice} onClick={() => picker.current?.click()}>
          <span className={styles.tag}>추천</span>
          <span className={styles.choiceTitle}>사진으로 채우기</span>
          <span className={styles.choiceText}>읽은 내용은 다음 화면에서 확인해요</span>
        </button>
        <button
          type="button"
          className={styles.choice}
          onClick={() => {
            update({ inputMethod: "manual" });
            go("number");
          }}
        >
          <span className={styles.choiceTitle}>직접 입력하기</span>
          <span className={styles.choiceText}>세 가지를 하나씩 입력해요</span>
        </button>
      </div>
      <Hint>글자가 잘 보이게, 네 모서리가 모두 나오게 찍어 주세요.</Hint>
      <input
        ref={picker}
        className={styles.hiddenInput}
        type="file"
        accept="image/*"
        aria-label="사업자등록증 사진"
        onChange={(event) => {
          const file = event.currentTarget.files?.[0];
          event.currentTarget.value = "";
          if (file) void read(file);
        }}
      />
    </StepFrame>
  );
}

export function ReadingStep() {
  return (
    <StepFrame step="reading" centered>
      <CenterContent title={"사업자등록증을\n읽고 있어요"} text="잠시만 기다려 주세요." loading />
    </StepFrame>
  );
}

/** BN, REP and DATE: on the photo path each goes straight back to the check (primaryAction). */
function nextAfterBusinessField(inputMethod: "photo" | "manual", manualNext: "representative" | "opening-date" | "check") {
  return inputMethod === "photo" ? "check" : manualNext;
}

export function NumberStep() {
  const { draft, update, forward } = useApplication();
  const invalid = draft.businessNumber.length === 10 && !validBusinessRegistrationNumber(draft.businessNumber);
  return (
    <StepFrame
      step="number"
      action={{
        label: "다음",
        enabled: validBusinessRegistrationNumber(draft.businessNumber),
        onClick: () => forward(nextAfterBusinessField(draft.inputMethod, "representative")),
      }}
    >
      <Question title={"사업자등록번호를\n알려주세요"} />
      <DigitsField
        label="사업자등록번호"
        digits={draft.businessNumber}
        maxDigits={10}
        format={formatBusinessNumber}
        onDigits={(digits) => update({ businessNumber: digits })}
        placeholder="000-00-00000"
        hint="숫자 10자리. 하이픈은 자동으로 들어가요."
        error={invalid ? "번호를 다시 확인해 주세요. 사업자등록증의 10자리와 같아야 해요." : undefined}
      />
    </StepFrame>
  );
}

export function RepresentativeStep() {
  const { draft, update, forward, go } = useApplication();
  const name = draft.representativeName.trim();
  return (
    <StepFrame
      step="representative"
      action={{
        label: "다음",
        enabled: name.length >= 1 && name.length <= 100,
        onClick: () => forward(nextAfterBusinessField(draft.inputMethod, "opening-date")),
      }}
    >
      <Question title={"대표자 성명을\n알려주세요"} subtitle="사업자등록증에 적힌 이름 그대로 입력해 주세요." />
      <TextInput label="대표자 성명" value={draft.representativeName} maxLength={100} placeholder="홍길동" onValue={(value) => update({ representativeName: value })} />
      <SummaryRow label="사업자등록번호" value={formatBusinessNumber(draft.businessNumber)} onEdit={() => go("number")} />
    </StepFrame>
  );
}

export function OpeningDateStep() {
  const { draft, update, forward, go } = useApplication();
  const invalid = draft.openingDate.length === 10 && !validOpeningDate(draft.openingDate);
  return (
    <StepFrame step="opening-date" action={{ label: "다음", enabled: validOpeningDate(draft.openingDate), onClick: () => forward("check") }}>
      <Question title={"개업일을\n알려주세요"} subtitle="사업자등록증의 개업연월일이에요." />
      <DigitsField
        label="개업일"
        digits={draft.openingDate.replace(/\D/g, "")}
        maxDigits={8}
        format={(digits) => openingDateFromInput(digits).replaceAll("-", ".")}
        onDigits={(digits) => update({ openingDate: openingDateFromInput(digits) })}
        placeholder="YYYY.MM.DD"
        error={invalid ? "날짜를 다시 확인해 주세요. 오늘 이후 날짜는 넣을 수 없어요." : undefined}
      />
      <SummaryRow label="대표자 성명" value={draft.representativeName} onEdit={() => go("representative")} />
      <SummaryRow label="사업자등록번호" value={formatBusinessNumber(draft.businessNumber)} onEdit={() => go("number")} />
    </StepFrame>
  );
}

/** A 422 of the business check as one message (spec 3.11.16: the rules of 3.11.2). */
function checkValidationMessage(error: ApiError): string {
  const codes = error.fieldErrors.map((field) => field.code);
  if (codes.includes("INVALID_BUSINESS_NUMBER")) return "사업자등록번호와 검사 숫자를 확인해 주세요.";
  if (codes.includes("DATE_IN_FUTURE")) return "개업일은 오늘보다 늦을 수 없어요.";
  return Object.values(fieldErrorMessages(error))[0] ?? "입력값을 확인해 주세요.";
}

export function CheckStep() {
  const { api } = useSession();
  const { draft, update, go, latest, setNotice } = useApplication();
  const [busy, setBusy] = useState(false);
  const precheck = registrationPrecheckError(draft.businessNumber, draft.representativeName, draft.openingDate);
  const photo = draft.inputMethod === "photo";
  const partial = photo && (!draft.businessNumber || !draft.representativeName || !draft.openingDate);
  const fields = (label: string, value: string, step: "number" | "representative" | "opening-date") => (
    <SummaryRow
      key={step}
      label={label}
      value={value || "읽지 못했어요"}
      actionLabel={value ? "수정" : "입력"}
      onEdit={() => go(step)}
    />
  );

  // The NTS check of exactly the values on screen; a result for values changed meanwhile is dropped
  // (ownerBusinessVerificationKey in OwnerOnboardingScreen.kt).
  async function check() {
    if (busy) return;
    setBusy(true);
    const requested = latest();
    const key = businessVerificationKey(requested);
    setNotice("check", null);
    update({ verification: null });
    try {
      const result = await checkBusiness(api, requested);
      if (businessVerificationKey(latest()) !== key) return;
      update({ verification: { key, result, retryAfter: null } });
      go("result");
    } catch (error) {
      if (businessVerificationKey(latest()) !== key) return;
      if (error instanceof ApiError && error.code === "RATE_LIMITED") {
        const retryAfter = typeof error.details?.retryAfter === "string" ? error.details.retryAfter : null;
        update({ verification: { key, result: "limited", retryAfter } });
        go("result");
      } else if (error instanceof ApiError && error.code === "VALIDATION_FAILED") {
        setNotice("check", checkValidationMessage(error));
      } else {
        setNotice("check", errorMessage(error));
      }
    } finally {
      setBusy(false);
    }
  }

  return (
    <StepFrame step="check" action={{ label: "확인하기", enabled: precheck === null, busy, onClick: () => void check() }}>
      <Question
        title={photo ? "읽은 내용이\n맞는지 확인해 주세요" : "이 정보로\n확인할게요"}
        subtitle={photo ? "사진과 한 글자씩 비교해 주세요. 하나라도 다르면 확인에 실패해요." : "국세청에 등록된 정보와 같은지 확인해요."}
      />
      <div>
        {fields("사업자등록번호", formatBusinessNumber(draft.businessNumber), "number")}
        {fields("대표자 성명", draft.representativeName, "representative")}
        {fields("개업일", draft.openingDate.replaceAll("-", "."), "opening-date")}
      </div>
      {partial ? <Hint>읽지 못한 항목은 직접 입력해 주세요.</Hint> : null}
      {!partial && precheck ? <ErrorText>{precheck}</ErrorText> : null}
      <Hint>사업자 정보를 확인해 주세요. 국세청 확인 결과를 다음 화면에서 안내해요.</Hint>
    </StepFrame>
  );
}

const RESULT_COPY = {
  matched: { title: "사업자 정보가\n확인됐어요", text: "이제 매장 정보를 알려주세요.", action: "다음" },
  not_matched: {
    title: "사업자 정보가\n맞지 않아요",
    text: "사업자등록번호, 대표자 성명, 개업일 중 하나가 국세청 정보와 달라요. 사업자등록증과 똑같이 입력했는지 확인해 주세요.",
    action: "다시 확인하기",
  },
  unavailable: { title: "지금은 국세청 확인이\n어려워요", text: "신청은 이어서 할 수 있어요. 운영팀이 나중에 다시 확인해요.", action: "계속하기" },
  limited: { title: "오늘 확인 횟수를\n모두 썼어요", text: "", action: "돌아가기" },
} as const;

export function ResultStep() {
  const { draft, go, update } = useApplication();
  const verification = draft.verification;
  if (!verification || !businessVerificationIsCurrent(verification.key, draft)) return null; // the route sends it to check
  const copy = RESULT_COPY[verification.result];
  const reset = formatResetTime(verification.retryAfter) ?? "내일 0시";
  const text =
    verification.result === "limited" ? `사업자 정보 확인은 하루 30번까지 시도할 수 있어요.\n${reset}부터 다시 진행해 주세요.` : copy.text;

  function next() {
    switch (verification?.result) {
      case "matched":
      case "unavailable":
        go("bar-name");
        break;
      case "not_matched":
        go("check", { replace: true });
        break;
      case "limited":
        update({ step: "intro" });
        go("intro", { replace: true });
        break;
    }
  }

  return (
    <StepFrame step="result" centered action={{ label: copy.action, enabled: true, onClick: next }}>
      <CenterContent title={copy.title} text={text} />
    </StepFrame>
  );
}

/** A plain text input of the application (RegistrationInput). */
export function TextInput({
  label,
  value,
  onValue,
  maxLength,
  placeholder,
  error,
}: {
  label: string;
  value: string;
  onValue: (value: string) => void;
  maxLength?: number;
  placeholder?: string;
  error?: string;
}) {
  return <TextField label={label} value={value} maxLength={maxLength} placeholder={placeholder} error={error} onChange={(event) => onValue(event.currentTarget.value)} />;
}
