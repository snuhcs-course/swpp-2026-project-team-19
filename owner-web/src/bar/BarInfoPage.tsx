import { useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useNavigate } from "react-router";
import { ApiError, errorMessage, fieldErrorMessages } from "../api/errors";
import { SummaryRow } from "../application/parts";
import { OwnerScreen } from "../owner/OwnerScreen";
import { ownerQueryKeys, useBar, useMyBars, useUpdateBar, type BarDetail, type OwnedBar } from "../owner/queries";
import { BottomSheet } from "../ui/BottomSheet";
import { Button } from "../ui/Button";
import { TextArea } from "../ui/TextArea";
import { TextField } from "../ui/TextField";
import {
  MAX_DESCRIPTION,
  MAX_TAG_LENGTH,
  MAX_TAGS,
  availableTags,
  barInfoErrors,
  barUpdate,
  canCreateTag,
  characterCount,
  fieldOfPath,
  formFromBar,
  hasEdits,
  tagCandidates,
  toggleTag,
  type BarInfoField,
  type BarInfoForm,
} from "./barInfo";
import { BarQuery } from "./BarHomePage";
import { useLeaveGuard } from "./useLeaveGuard";
import styles from "./bar.module.css";

/**
 * /owner/bars/:barId/info: the bar's description, phone, default pour and tags
 * (android/.../ui/owner/OwnerInfoHtmlV4Screen.kt), saved together with PATCH /api/bars/{barId} (spec 3.7).
 * Photos and hours come in I5-P6. Name and address are shown only: changing them will need an operator's
 * review, for the app and the web alike.
 */
export function BarInfoPage({ bar }: { bar: OwnedBar }) {
  const detail = useBar(bar.barId);
  // The frame (back, sign-out) is there in every state, so a failed load still has a way out.
  return (
    <OwnerScreen title="매장 정보 관리" backTo={`/bars/${bar.barId}`}>
      <BarQuery query={detail} keepDataOnRefetchError>
        {(data) => <BarInfoForm bar={data} />}
      </BarQuery>
    </OwnerScreen>
  );
}

/** Copy for codes the shared field copy (src/api/errors.ts) lacks: DUPLICATE_TAG (spec 3.7). */
const FIELD_COPY: Record<string, string> = { DUPLICATE_TAG: "같은 태그가 이미 있어요." };
const TAGS_FULL = "태그는 최대 5개까지 등록할 수 있어요.";

function BarInfoForm({ bar }: { bar: BarDetail }) {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const update = useUpdateBar(bar.barId);
  const myBars = useMyBars();
  // The draft starts from the bar as loaded and stays until saved, as the app's form does (rememberSaveable).
  // What it is compared with stays that same bar: a later refetch (e.g. after a reconnect) may bring changes
  // made elsewhere, and comparing with those would send this form's older values over them.
  const [opened] = useState(bar);
  const [form, setForm] = useState<BarInfoForm>(() => formFromBar(opened));
  const [query, setQuery] = useState("");
  const [tagError, setTagError] = useState<string | null>(null);
  const [serverErrors, setServerErrors] = useState<Partial<Record<BarInfoField, string>>>({});
  const [error, setError] = useState<string | null>(null);
  const dirty = hasEdits(opened, form);
  const guard = useLeaveGuard(dirty, update.isPending);

  const inputErrors = barInfoErrors(form, formFromBar(opened));
  const fieldError = (field: BarInfoField) => inputErrors[field] ?? serverErrors[field];
  const valid = Object.keys(inputErrors).length === 0;
  const ownBarTags = (myBars.data?.items ?? []).flatMap((item) => item.tags);
  const candidates = tagCandidates(query, form.tags, ownBarTags);
  const creatable = canCreateTag(query, availableTags(ownBarTags), form.tags);

  function change(next: Partial<BarInfoForm>, field?: BarInfoField) {
    setForm((current) => ({ ...current, ...next }));
    setError(null);
    if (field) setServerErrors(({ [field]: _, ...rest }) => rest);
  }

  function pickTag(tag: string) {
    const next = toggleTag(form.tags, tag);
    if (!next) return setTagError(TAGS_FULL);
    change({ tags: next }, "tags");
    setQuery("");
    setTagError(null);
  }

  function removeTag(tag: string) {
    change({ tags: form.tags.filter((item) => item !== tag) }, "tags");
    setTagError(null);
  }

  function done() {
    guard.release();
    void navigate(`/bars/${bar.barId}`);
  }

  function save() {
    if (update.isPending || !valid) return;
    const body = barUpdate(opened, form);
    // Nothing changed after normalizing (e.g. only spaces were added): nothing to send.
    if (Object.keys(body).length === 0) return done();
    setError(null);
    setServerErrors({});
    update.mutate(body, { onSuccess: done, onError: handleFailure });
  }

  function handleFailure(failure: unknown) {
    if (!(failure instanceof ApiError)) return setError(errorMessage(failure));
    switch (failure.code) {
      case "VALIDATION_FAILED": {
        const byField: Partial<Record<BarInfoField, string>> = {};
        const messages = fieldErrorMessages(failure);
        for (const item of failure.fieldErrors) {
          const field = fieldOfPath(item.path);
          if (field && !byField[field]) byField[field] = FIELD_COPY[item.code] ?? messages[item.path];
        }
        setServerErrors(byField);
        return setError(Object.keys(byField).length ? "입력한 내용을 확인해 주세요." : errorMessage(failure));
      }
      case "FORBIDDEN":
        // No longer this bar's owner (spec 3.11.10): the bar list decides what the owner may still open.
        setError("이 매장을 관리할 권한이 없어요.");
        return void queryClient.invalidateQueries({ queryKey: ownerQueryKeys.myBars });
      case "BAR_NOT_FOUND":
        // Spec 3.7: go back to the bar list.
        guard.release();
        void queryClient.invalidateQueries({ queryKey: ownerQueryKeys.myBars });
        return void navigate("/bars", { replace: true });
      default:
        return setError(errorMessage(failure));
    }
  }

  return (
    <>
      <form
        onSubmit={(event) => {
          event.preventDefault();
          save();
        }}
      >
        {/* Locked while saving: an edit made then would not be in the request, and leaving after the save
            would drop it. */}
        <fieldset className={[styles.screen, styles.fieldset].join(" ")} disabled={update.isPending}>
          <section className={styles.section} aria-label="기본 정보">
            <SummaryRow label="매장명" value={bar.name} />
            <SummaryRow label="주소" value={bar.address} />
            <p className={styles.hint}>매장명과 주소는 지금은 바꿀 수 없어요.</p>
          </section>

          <TextArea
            label="한 줄 소개"
            value={form.description}
            rows={3}
            error={fieldError("description")}
            hint={`${characterCount(form.description.trim())}/${MAX_DESCRIPTION}`}
            onChange={(event) => change({ description: event.currentTarget.value }, "description")}
          />
          <TextField
            label="매장 기본 잔 용량 (ml)"
            value={form.pourMl}
            inputMode="numeric"
            placeholder="예: 30"
            error={fieldError("defaultPourMl")}
            // OwnerInfoHtmlV4Screen.kt: digits only, at most three.
            onChange={(event) => change({ pourMl: event.currentTarget.value.replace(/\D/g, "").slice(0, 3) }, "defaultPourMl")}
          />
          <TextField
            label="전화번호"
            value={form.phone}
            type="tel"
            error={fieldError("phone")}
            // OwnerInfoHtmlV4Screen.kt: at most 30 characters.
            onChange={(event) => change({ phone: event.currentTarget.value.slice(0, 30) }, "phone")}
          />

          <section className={styles.section} aria-labelledby="bar-tags-title">
            <div className={styles.sectionHead}>
              <h2 id="bar-tags-title" className={styles.sectionTitle}>
                매장 태그
              </h2>
              <span className={styles.hint}>
                {form.tags.length}/{MAX_TAGS}
              </span>
            </div>
            {form.tags.length === 0 ? (
              <p className={styles.hint}>선택한 태그가 없습니다.</p>
            ) : (
              <ul className={styles.chips} aria-label="선택한 태그">
                {form.tags.map((tag) => (
                  <li key={tag}>
                    <button
                      type="button"
                      className={[styles.chip, styles.chipSelected].join(" ")}
                      aria-label={`${tag} 빼기`}
                      onClick={() => removeTag(tag)}
                    >
                      {tag} ×
                    </button>
                  </li>
                ))}
              </ul>
            )}
            <TextField
              label="태그 검색"
              value={query}
              placeholder="태그 검색 또는 새 태그 입력"
              onChange={(event) => setQuery([...event.currentTarget.value].slice(0, MAX_TAG_LENGTH).join(""))}
              onKeyDown={(event) => {
                // Enter adds the typed tag instead of saving the form. An Enter that ends an IME composition
                // (Korean, Japanese) only confirms the syllable: adding then would take a partial word and
                // leave the last syllable behind in the cleared field.
                if (event.key !== "Enter" || event.nativeEvent.isComposing || event.keyCode === 229) return;
                event.preventDefault();
                if (creatable) pickTag(query);
              }}
            />
            {candidates.length || creatable ? (
              <ul className={styles.chips} aria-label="추가할 수 있는 태그">
                {candidates.map((tag) => (
                  <li key={tag}>
                    <button type="button" className={styles.chip} aria-label={`${tag} 추가`} onClick={() => pickTag(tag)}>
                      {tag} ＋
                    </button>
                  </li>
                ))}
                {creatable ? (
                  <li>
                    <button type="button" className={styles.chip} onClick={() => pickTag(query)}>
                      “{query.trim()}” 새 태그 등록 ＋
                    </button>
                  </li>
                ) : null}
              </ul>
            ) : null}
            {tagError ?? fieldError("tags") ? (
              <p className={styles.error} role="alert">
                {tagError ?? fieldError("tags")}
              </p>
            ) : null}
          </section>

          <section className={styles.section} aria-label="사진과 영업시간">
            <p className={styles.hint}>매장 사진과 영업시간은 웹에서 준비 중이에요.</p>
          </section>

          {error ? (
            <p className={styles.error} role="alert">
              {error}
            </p>
          ) : null}
          <Button type="submit" busy={update.isPending} disabled={!valid}>
            저장하기
          </Button>
        </fieldset>
      </form>

      {/* OwnerInfoHtmlV4Screen.kt: the discard sheet of the form the app opens. */}
      <BottomSheet open={guard.asking} title="변경을 취소할까요?" onClose={guard.stay}>
        <p className={styles.sheetText}>저장하지 않은 수정 사항은 사라집니다.</p>
        <div className={styles.actions}>
          <Button variant="secondary" onClick={guard.stay}>
            계속 편집
          </Button>
          <Button onClick={guard.leave}>변경 취소</Button>
        </div>
      </BottomSheet>
    </>
  );
}
