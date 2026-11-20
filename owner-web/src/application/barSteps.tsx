import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router";
import { ApiError, errorMessage, fieldErrorMessages } from "../api/errors";
import { useSession } from "../auth/SessionProvider";
import { readConfig } from "../config";
import { IMAGE_RULES, ImagePrepareError, MAX_MENU_PHOTOS, MAX_MENU_PHOTOS_BYTES, prepareImage, type PreparedImage } from "../images/prepare";
import { ownerQueryKeys } from "../owner/queries";
import { Button, ButtonLink } from "../ui/Button";
import { searchBarNames, submitApplication, SubmitError, type BarNameItem } from "./api";
import { useApplication } from "./ApplicationProvider";
import { TextInput } from "./businessSteps";
import { searchAddress, type AddressResult } from "./kakaoAddress";
import { pickedPhoto } from "./photos";
import { CenterContent, ErrorText, Hint, PhoneField, Question, StepFrame, SummaryRow, Visibility } from "./parts";
import { formatResetTime } from "./resetTime";
import {
  businessVerificationIsCurrent,
  businessVerificationKey,
  canCopyShopPhone,
  exactNameMatches,
  formatBusinessNumber,
  formatOwnerPhone,
  needsNewBarDetailsAfterClaimEdit,
  registrationPrecheckError,
  updatedBarName,
  validOwnerPhone,
} from "./rules";
import type { StepId } from "./steps";
import styles from "./application.module.css";

// The bar, photo, contact and review steps of android/.../ui/owner/OwnerOnboardingScreen.kt: BARNAME,
// BARPHOTO, ADDRESS, BARPHONE, MENUS, CONTACT, REVIEW and DONE, with the copy of the app.

export const OWNED_BAR_NOTICE = "이미 업주가 등록된 매장입니다. 운영자에게 문의해 주세요.";
export const LOCKED_NOTICE = "신청은 접수됐어요. 남은 사진만 올리면 돼요. 신청 내용은 바꿀 수 없어요.";

function useDebounced<T>(value: T, delayMs: number): T {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => {
    const timer = window.setTimeout(() => setDebounced(value), delayMs);
    return () => window.clearTimeout(timer);
  }, [value, delayMs]);
  return debounced;
}

export function BarNameStep() {
  const { api } = useSession();
  const { draft, update, go, forward, editingReview } = useApplication();
  const [ownedNotice, setOwnedNotice] = useState<string | null>(null);
  const name = draft.proposedBarName.trim();
  const query = useDebounced(name, 300);
  const searchable = query.length >= 2 && query.length <= 100;
  // Spec 3.11.11: bars by name; one whose name is the typed name is asked about, as in the app.
  const search = useQuery({
    queryKey: ["bar-names", query],
    queryFn: ({ signal }) => searchBarNames(api, query, signal),
    enabled: searchable,
    staleTime: 30_000,
  });
  const settled = query === name && (!searchable || !search.isFetching);
  const matches: BarNameItem[] = searchable && query === name ? exactNameMatches(search.data ?? [], name) : [];
  const nameValid = name.length >= 1 && name.length <= 150;

  function rename(value: string) {
    const edited = updatedBarName(
      { kind: draft.kind, existingBarId: draft.existingBar?.barId ?? null, proposedBarName: draft.proposedBarName },
      value,
    );
    setOwnedNotice(null);
    update({
      kind: edited.kind,
      proposedBarName: edited.proposedBarName,
      existingBar: edited.kind === "existing_bar" ? draft.existingBar : null,
    });
    // A claim turned into a new bar while editing from review collects the new-bar details first.
    if (needsNewBarDetailsAfterClaimEdit(editingReview, draft.kind, edited.kind)) go("bar-name", { replace: true });
  }

  function mine(bar: BarNameItem) {
    if (bar.hasOwner) {
      setOwnedNotice(bar.barId);
      return;
    }
    update({
      kind: "existing_bar",
      existingBar: { barId: bar.barId, name: bar.name, address: bar.address },
      proposedBarName: bar.name,
    });
    go("menus");
  }

  function other() {
    update({ kind: "new_bar", existingBar: null });
    go("cover");
  }

  return (
    <StepFrame
      step="bar-name"
      action={{
        label: "다음",
        enabled: nameValid && settled && matches.length === 0,
        onClick: () => forward(draft.kind === "existing_bar" && draft.existingBar ? "menus" : "cover"),
      }}
    >
      <Question title={"매장 이름을\n알려주세요"} subtitle="손님에게 보이는 이름이에요. 사업자등록증의 상호와 간판이 다르면 간판 이름으로 고쳐 주세요." />
      <TextInput label="매장 이름" value={draft.proposedBarName} maxLength={150} placeholder="예: 몰트 앤 무드" onValue={rename} />
      {search.isError && query === name ? <ErrorText>기존 매장을 검색하지 못했어요.</ErrorText> : null}
      {matches.map((bar) => (
        <section key={bar.barId} className={styles.card} aria-label={`${bar.name} 확인`}>
          <p className={styles.cardTitle}>BottleMap에 이미 등록된 매장이 있어요</p>
          <p className={styles.cardText}>{bar.name}</p>
          <p className={styles.cardText}>{bar.address}</p>
          {ownedNotice === bar.barId ? <ErrorText>{OWNED_BAR_NOTICE}</ErrorText> : null}
          <div className={styles.cardActions}>
            <Button onClick={() => mine(bar)}>우리 매장이에요</Button>
            <Button variant="secondary" onClick={other}>
              아니에요
            </Button>
          </div>
        </section>
      ))}
    </StepFrame>
  );
}

function PhotoPicker({ label, multiple = false, onFiles, children, disabled = false, className }: {
  label: string;
  multiple?: boolean;
  onFiles: (files: File[]) => void;
  children: React.ReactNode;
  disabled?: boolean;
  className?: string;
}) {
  const input = useRef<HTMLInputElement>(null);
  return (
    <>
      <button type="button" className={className} disabled={disabled} onClick={() => input.current?.click()}>
        {children}
      </button>
      <input
        ref={input}
        className={styles.hiddenInput}
        type="file"
        accept="image/*"
        multiple={multiple}
        aria-label={label}
        onChange={(event) => {
          const files = [...(event.currentTarget.files ?? [])];
          event.currentTarget.value = "";
          if (files.length) onFiles(files);
        }}
      />
    </>
  );
}

export function CoverStep() {
  const { cover, setCover, forward } = useApplication();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function choose([file]: File[]) {
    if (!file) return;
    setBusy(true);
    setError(null);
    try {
      setCover(await prepareImage(file, IMAGE_RULES.cover));
    } catch (failure) {
      setError(failure instanceof ImagePrepareError ? failure.message : "사진을 읽을 수 없어요. 다른 사진을 골라 주세요.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <StepFrame step="cover" action={{ label: "다음", enabled: cover !== null && !busy, busy, onClick: () => forward("address") }}>
      <Question title={"매장 사진을\n올려 주세요"} subtitle="대표 사진을 골라 주세요. 신청 시 전송하고 승인되면 첫 매장 사진이 돼요." />
      <PhotoPicker label="대표 사진" onFiles={(files) => void choose(files)} className={styles.cover}>
        {cover ? <img src={cover.previewUrl} alt="고른 대표 사진" /> : <span>사진 올리기</span>}
      </PhotoPicker>
      {cover ? <Hint>사진을 누르면 바꿀 수 있어요.</Hint> : null}
      {error ? <ErrorText>{error}</ErrorText> : null}
      <Hint>간판이나 입구, 매장 안쪽이 잘 보이는 사진</Hint>
      <Hint>사람 얼굴이 크게 나오지 않은 사진</Hint>
    </StepFrame>
  );
}

export function AddressStep() {
  const { draft, update, forward } = useApplication();
  const [results, setResults] = useState<AddressResult[] | null>(null);
  const [searching, setSearching] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const full = [draft.address, draft.addressDetail].map((part) => part.trim()).filter(Boolean).join(" ");

  async function search() {
    setSearching(true);
    setError(null);
    try {
      const found = await searchAddress(readConfig().kakaoJavascriptKey, draft.address.trim());
      setResults(found);
      if (found.length === 0) setError("주소를 찾지 못했어요. 도로명 주소나 건물명으로 다시 찾거나 직접 입력해 주세요.");
    } catch (failure) {
      setResults(null);
      setError(failure instanceof Error ? failure.message : "주소를 찾지 못했어요. 직접 입력해 주세요.");
    } finally {
      setSearching(false);
    }
  }

  return (
    <StepFrame
      step="address"
      action={{ label: "다음", enabled: draft.address.trim() !== "" && full.length <= 500, onClick: () => forward("bar-phone") }}
    >
      <Question title={"매장 주소를\n알려주세요"} subtitle="손님이 지도에서 찾을 수 있게 정확히 입력해 주세요." />
      <TextInput label="주소" value={draft.address} maxLength={500} placeholder="도로명 주소 또는 건물명 입력" onValue={(value) => update({ address: value })} />
      <Button variant="secondary" busy={searching} disabled={draft.address.trim() === ""} onClick={() => void search()}>
        주소 검색
      </Button>
      {error ? <ErrorText>{error}</ErrorText> : null}
      {results?.length ? (
        <ul className={styles.list} aria-label="주소 검색 결과">
          {results.map((result) => (
            <li key={result.address}>
              <button
                type="button"
                className={styles.result}
                onClick={() => {
                  update({ address: result.address });
                  setResults(null);
                }}
              >
                <span>{result.address}</span>
                {result.label ? <span className={styles.cardText}>{result.label}</span> : null}
              </button>
            </li>
          ))}
        </ul>
      ) : null}
      <TextInput label="상세 주소" value={draft.addressDetail} maxLength={200} placeholder="예: 2층" onValue={(value) => update({ addressDetail: value })} />
    </StepFrame>
  );
}

export function BarPhoneStep() {
  const { draft, update, forward } = useApplication();
  return (
    <StepFrame
      step="bar-phone"
      action={{ label: "다음", enabled: draft.storePhone !== "" && validOwnerPhone(draft.storePhone), onClick: () => forward("menus") }}
    >
      <Question title={"매장 전화번호를\n알려주세요"} subtitle="예약이나 문의 전화를 받을 가게 번호예요." />
      <Visibility isPublic />
      <PhoneField
        label="매장 전화번호"
        digits={draft.storePhone}
        onDigits={(digits) => update({ storePhone: digits })}
        hint="지역번호나 0507 안심번호도 넣을 수 있어요."
        error={draft.storePhone.length >= 9 && !validOwnerPhone(draft.storePhone) ? "번호를 다시 확인해 주세요." : undefined}
      />
      <button
        type="button"
        className={styles.linkButton}
        onClick={() => {
          update({ storePhone: "" });
          forward("menus");
        }}
      >
        가게 전화가 없어요
      </button>
    </StepFrame>
  );
}

export function MenusStep() {
  const { menus, setMenus, forward } = useApplication();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function add(files: File[]) {
    setBusy(true);
    setError(null);
    const room = MAX_MENU_PHOTOS - menus.length;
    const prepared: PreparedImage[] = [];
    let failed = 0;
    for (const file of files.slice(0, room)) {
      try {
        prepared.push(await prepareImage(file, IMAGE_RULES.menu));
      } catch {
        failed++;
      }
    }
    const total = [...menus.map((photo) => photo.image), ...prepared].reduce((sum, image) => sum + image.blob.size, 0);
    if (total > MAX_MENU_PHOTOS_BYTES) {
      setError("사진이 모두 합쳐 60MB를 넘어요. 몇 장을 빼고 다시 골라 주세요.");
    } else {
      setMenus((current) => [...current, ...prepared.map(pickedPhoto)]);
      const messages = [];
      if (files.length > room) messages.push(`메뉴판 사진은 ${MAX_MENU_PHOTOS}장까지 올릴 수 있어요.`);
      if (failed) messages.push(`${failed}장은 읽을 수 없어 빼고 올렸어요.`);
      if (messages.length) setError(messages.join(" "));
    }
    setBusy(false);
  }

  return (
    <StepFrame step="menus" action={{ label: "다음", enabled: menus.length > 0 && !busy, busy, onClick: () => forward("contact") }}>
      <Question title={"메뉴판 사진을\n올려 주세요"} subtitle="AI가 메뉴를 읽어 두면, 승인된 뒤에 확인만 하고 공개할 수 있어요." />
      <ul className={styles.thumbs} aria-label="메뉴판 사진">
        {menus.map((photo, index) => (
          <li key={photo.id} className={styles.thumb}>
            <img src={photo.previewUrl} alt={`메뉴판 사진 ${index + 1}`} />
            <span className={styles.thumbIndex}>{index + 1}</span>
            <button
              type="button"
              className={styles.thumbRemove}
              aria-label={`${index + 1}번째 사진 빼기`}
              onClick={() => setMenus((current) => current.filter((item) => item.id !== photo.id))}
            >
              ×
            </button>
          </li>
        ))}
        <li>
          <PhotoPicker label="메뉴판 사진 추가" multiple disabled={busy || menus.length >= MAX_MENU_PHOTOS} onFiles={(files) => void add(files)} className={styles.addTile}>
            <span>사진 추가</span>
            <span>
              {menus.length}/{MAX_MENU_PHOTOS}
            </span>
          </PhotoPicker>
        </li>
      </ul>
      {error ? <ErrorText>{error}</ErrorText> : null}
      <Hint>메뉴판 순서대로 올려 주세요</Hint>
      <Hint>한 장에 한 면씩, 글자와 가격이 잘리지 않게</Hint>
      <Hint>빛 반사 없이 정면에서</Hint>
    </StepFrame>
  );
}

export function ContactStep() {
  const { draft, update, forward } = useApplication();
  return (
    <StepFrame
      step="contact"
      action={{ label: "다음", enabled: draft.contactPhone !== "" && validOwnerPhone(draft.contactPhone), onClick: () => forward("review") }}
    >
      <Question title={"연락받을 번호를\n알려주세요"} subtitle="승인 전에 운영팀이 확인 연락을 드릴 수 있어요." />
      <Visibility isPublic={false} />
      {draft.storePhone ? (
        <button
          type="button"
          className={styles.linkButton}
          disabled={!canCopyShopPhone(draft.storePhone)}
          onClick={() => update({ contactPhone: draft.storePhone })}
        >
          매장 번호와 같아요
        </button>
      ) : null}
      <PhoneField
        label="연락받을 번호"
        digits={draft.contactPhone}
        onDigits={(digits) => update({ contactPhone: digits })}
        error={draft.contactPhone.length >= 9 && !validOwnerPhone(draft.contactPhone) ? "번호를 다시 확인해 주세요." : undefined}
      />
    </StepFrame>
  );
}

const FIELD_STEPS: Record<string, StepId> = {
  businessRegistrationNumber: "check",
  representativeName: "check",
  openingDate: "check",
  "proposedBar.name": "bar-name",
  "proposedBar.address": "address",
  "proposedBar.phone": "bar-phone",
  contactPhone: "contact",
};

export function ReviewStep() {
  const { api } = useSession();
  const queryClient = useQueryClient();
  const application = useApplication();
  const { draft, cover, menus, update, go, setNotice, finish, locked } = application;
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<{ message: string; toStatus?: boolean } | null>(null);
  const newBar = draft.kind === "new_bar";
  const verificationCurrent =
    businessVerificationIsCurrent(draft.verification?.key, draft) &&
    (draft.verification?.result === "matched" || draft.verification?.result === "unavailable");
  const menusReady = menus.length > 0 || draft.uploaded.menus;
  const coverReady = !newBar || cover !== null || draft.uploaded.cover;
  const ready =
    draft.contactPhone !== "" &&
    validOwnerPhone(draft.contactPhone) &&
    menusReady &&
    coverReady &&
    registrationPrecheckError(draft.businessNumber, draft.representativeName, draft.openingDate) === null &&
    verificationCurrent;
  const edit = (step: StepId) => go(step, { fromReview: true });
  // Once the application exists only its photos are left to send: the server has the rest, and there is no
  // API to change it, so the text is shown but not edited (it would look saved while the server kept the old).
  const editText = (step: StepId) => (locked ? undefined : () => edit(step));

  async function submit() {
    setBusy(true);
    setError(null);
    try {
      await submitApplication({
        api,
        draft: application.latest(),
        cover: cover?.image ?? null,
        menus: menus.map((photo) => photo.image),
        onProgress: (progress) => update(progress),
      });
      finish();
      await queryClient.invalidateQueries({ queryKey: ownerQueryKeys.myApplications });
      go("done", { replace: true });
    } catch (failure) {
      handleFailure(failure);
    } finally {
      setBusy(false);
    }
  }

  function handleFailure(failure: unknown) {
    const stage = failure instanceof SubmitError ? failure.stage : "create";
    const cause = failure instanceof SubmitError ? failure.cause : failure;
    if (!(cause instanceof ApiError)) return setError({ message: errorMessage(cause) });

    if (stage !== "create") {
      if (cause.code === "INVALID_APPLICATION_STATE" || cause.code === "OWNER_APPLICATION_NOT_FOUND") {
        return setError({ message: "신청 상태가 바뀌어 사진을 올릴 수 없어요. 신청 상태를 확인해 주세요.", toStatus: true });
      }
      const photo = cause.status === 413 || cause.status === 415 || cause.code === "VALIDATION_FAILED";
      return setError({
        message: photo
          ? "신청은 접수됐지만 사진을 올리지 못했어요. 사진을 다시 골라 신청하기를 눌러 주세요."
          : `신청은 접수됐지만 사진을 올리지 못했어요. ${errorMessage(cause)} 신청하기를 다시 눌러 주세요.`,
      });
    }

    switch (cause.code) {
      case "BUSINESS_VERIFICATION_FAILED":
        // The server refused exactly these three values: show the mismatch result, as the app does.
        update({ verification: { key: businessVerificationKey(application.latest()), result: "not_matched", retryAfter: null } });
        return go("result");
      case "RATE_LIMITED": {
        const reset = formatResetTime(cause.details?.retryAfter) ?? "내일 0시";
        return setError({ message: `오늘 사업자 정보 확인 횟수를 모두 사용했어요. ${reset}부터 다시 신청해 주세요.` });
      }
      case "BAR_OWNER_EXISTS":
        update({ kind: "new_bar", existingBar: null });
        setNotice("bar-name", OWNED_BAR_NOTICE);
        return go("bar-name");
      case "BAR_NOT_FOUND":
        update({ kind: "new_bar", existingBar: null });
        setNotice("bar-name", "선택한 매장을 찾을 수 없어요. 매장을 다시 골라 주세요.");
        return go("bar-name");
      case "OWNER_APPLICATION_EXISTS":
        return setError({ message: "이미 처리 중인 신청이 있어요. 신청 상태를 확인해 주세요.", toStatus: true });
      case "VALIDATION_FAILED": {
        const codes = cause.fieldErrors.map((field) => field.code);
        const first = cause.fieldErrors.find((field) => field.path in FIELD_STEPS);
        if (codes.includes("INVALID_BUSINESS_NUMBER") || codes.includes("DATE_IN_FUTURE") || first) {
          const step = first ? (FIELD_STEPS[first.path] ?? "check") : "check";
          const message = codes.includes("INVALID_BUSINESS_NUMBER")
            ? "사업자등록번호와 검사 숫자를 확인해 주세요."
            : codes.includes("DATE_IN_FUTURE")
              ? "개업일은 오늘보다 늦을 수 없어요."
              : (fieldErrorMessages(cause)[first?.path ?? ""] ?? "입력값을 확인해 주세요.");
          setNotice(step, message);
          return go(step, { fromReview: true });
        }
        return setError({ message: Object.values(fieldErrorMessages(cause))[0] ?? errorMessage(cause) });
      }
      default:
        return setError({ message: errorMessage(cause) });
    }
  }

  const address = [draft.address, draft.addressDetail].map((part) => part.trim()).filter(Boolean).join(" ");
  return (
    <StepFrame step="review" action={{ label: "신청하기", enabled: ready && !busy, busy, onClick: () => void submit() }}>
      <Question title={"이렇게\n신청할게요"} subtitle="한 번 더 확인하고 신청해 주세요." />
      {locked ? <p className={styles.notice}>{LOCKED_NOTICE}</p> : null}
      {!locked && draft.verification?.result !== "matched" ? <Hint>국세청 정보 확인은 '신청하기'를 누를 때 진행돼요.</Hint> : null}
      <ReviewSection title="사업자 정보" onEdit={editText("check")}>
        <SummaryRow label="등록번호" value={formatBusinessNumber(draft.businessNumber)} />
        <SummaryRow label="대표자" value={draft.representativeName} />
        <SummaryRow label="개업일" value={draft.openingDate.replaceAll("-", ".")} />
      </ReviewSection>
      <ReviewSection title="매장 정보" onEdit={editText("bar-name")}>
        <SummaryRow label="이름" value={draft.proposedBarName} />
        {newBar ? (
          <>
            <SummaryRow label="대표 사진" value={cover || draft.uploaded.cover ? "1장" : "다시 골라 주세요"} onEdit={() => edit("cover")} actionLabel="바꾸기" />
            <SummaryRow label="주소" value={address} />
            <SummaryRow label="전화번호" value={draft.storePhone ? formatOwnerPhone(draft.storePhone) : "없음"} />
          </>
        ) : (
          <SummaryRow label="주소" value={draft.existingBar?.address ?? ""} />
        )}
      </ReviewSection>
      <ReviewSection title="메뉴판" onEdit={() => edit("menus")}>
        <SummaryRow label="메뉴판 사진" value={menusReady ? `${draft.uploaded.menus ? "올림 완료" : `${menus.length}장`}` : "다시 골라 주세요"} />
      </ReviewSection>
      <ReviewSection title="연락처" onEdit={editText("contact")}>
        <SummaryRow label="연락받을 번호" value={formatOwnerPhone(draft.contactPhone)} />
      </ReviewSection>
      {!menusReady || !coverReady ? <Hint>새로고침하면 고른 사진이 지워져요. 사진을 다시 골라 주세요.</Hint> : null}
      <Hint>운영팀 승인 전에는 매장과 메뉴가 손님에게 보이지 않아요.</Hint>
      {error ? (
        <>
          <ErrorText>{error.message}</ErrorText>
          {error.toStatus ? <ButtonLink to="/">신청 상태 보기</ButtonLink> : null}
        </>
      ) : null}
    </StepFrame>
  );
}

function ReviewSection({ title, onEdit, children }: { title: string; onEdit?: () => void; children: React.ReactNode }) {
  return (
    <section className={styles.section} aria-label={title}>
      <div className={styles.sectionHead}>
        <h3 className={styles.sectionTitle}>{title}</h3>
        {onEdit ? (
          <button type="button" className={styles.linkButton} onClick={onEdit} aria-label={`${title} 수정`}>
            수정
          </button>
        ) : null}
      </div>
      {children}
    </section>
  );
}

export function DoneStep() {
  const navigate = useNavigate();
  // The start screen sends the owner on to their application's status.
  return (
    <StepFrame step="done" centered action={{ label: "확인", enabled: true, onClick: () => void navigate("/", { replace: true }) }}>
      <CenterContent title="신청을 마쳤어요" text={"운영팀이 실제 매장인지 확인한 뒤 승인해요.\n진행 상황은 처음 화면에서 볼 수 있어요."} />
    </StepFrame>
  );
}
