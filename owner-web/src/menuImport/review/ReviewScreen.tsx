import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useNavigate } from "react-router";
import { ApiError } from "../../api/errors";
import type { components } from "../../api/schema";
import { useBarFailure } from "../../bar/failures";
import { useMe, useUpdateBar, type BarDetail, type BarMenu } from "../../owner/queries";
import { BottomSheet } from "../../ui/BottomSheet";
import { Button, ButtonLink } from "../../ui/Button";
import { LoadingState } from "../../ui/states";
import { TextField } from "../../ui/TextField";
import { ImportSteps } from "../ImportStartPage";
import { useImportActions } from "../importApi";
import { readDeviceDraft, restoreDraft, type DeviceDraft } from "./draft";
import { existingUnlinkedOptions, mapReview, savedCandidate, splitMerged, type ImportReview } from "./mapping";
import { readNumeric, validDefaultPour, type ReviewCard, type ReviewGroup, type ReviewState } from "./model";
import { applyDefaultPour, publicationPreview, reviewStats } from "./rules";
import { ReviewCardView, type CardActions } from "./ReviewCardView";
import { reviewBody, ReviewSubmitError } from "./submit";
import { useDraftSync } from "./useDraftSync";
import styles from "../menuImport.module.css";
import barStyles from "../../bar/bar.module.css";

type Applied = components["schemas"]["ReviewAppliedResponse"];

interface ReviewProps {
  review: ImportReview;
  menu: BarMenu;
  bar: BarDetail;
  onNotice: (message: string | null) => void;
}

/**
 * The one-page menu review (android/.../ui/owner/review/PhotoReviewScreen.kt), from the review response (5.4):
 * each line of the photos as a card to confirm, saved as a draft while the owner works (5.9), and published in
 * one request (8). Choosing the other client's draft opens the review again from it.
 */
export function ReviewScreen(props: ReviewProps) {
  const me = useMe();
  // A restart opens the review from the response just read, before the screen's query passes it down.
  const [restarted, setRestarted] = useState<{ generation: number; review: ImportReview | null }>({ generation: 0, review: null });
  if (!me.data) return <LoadingState message="검수 정보를 불러오고 있어요." />;
  const review = restarted.review?.reviewVersion === props.review.reviewVersion ? restarted.review : props.review;
  return (
    <ReviewBody
      key={restarted.generation}
      {...props}
      review={review}
      userId={me.data.userId}
      restart={(fresh) => setRestarted(({ generation }) => ({ generation: generation + 1, review: fresh }))}
    />
  );
}

/** The cards the review starts with: the server draft, or this device's unsent copy when it builds on it. */
function initialReview(review: ImportReview, menu: BarMenu, bar: BarDetail, device: DeviceDraft | null): { state: ReviewState; resume: boolean; conflict: DeviceDraft | null } {
  const fresh = mapReview(review, menu, bar.defaultPourMl);
  const server = review.reviewDraft;
  const fromServer = server ? restoreDraft(fresh, review, server) : fresh;
  if (!device) return { state: fromServer, resume: false, conflict: null };
  if (device.reviewVersion !== review.reviewVersion) {
    // The review was built again (9.4): this device's decisions apply where their lines are still in it. With a
    // server draft as well, the owner chooses, so the edit the server never got is not dropped unseen.
    return server
      ? { state: fromServer, resume: false, conflict: device }
      : { state: restoreDraft(fresh, review, { reviewVersion: device.reviewVersion, content: device.content }), resume: true, conflict: null };
  }
  if (device.baseDraftVersion === (server?.draftVersion ?? 0)) {
    return { state: restoreDraft(fresh, review, { reviewVersion: device.reviewVersion, content: device.content }), resume: true, conflict: null };
  }
  return { state: fromServer, resume: false, conflict: device };
}

type Publish =
  | { kind: "confirm" }
  | { kind: "sending" }
  | { kind: "done"; applied: Applied | null }
  | { kind: "unknown"; checking: boolean }
  | { kind: "failed"; messages: string[] };

const GROUPS: { group: ReviewGroup; title: string }[] = [
  { group: "pending", title: "메뉴를 확인해 주세요" },
  { group: "ready", title: "바로 등록할 수 있어요" },
  { group: "other", title: "그 외 메뉴도 등록돼요" },
  { group: "excluded", title: "게시 제외" },
];

/** Copy for the 422 field errors of a publish (8.7, 9.3), by `fieldErrors[].code`. */
const PUBLISH_FIELD_COPY: Record<string, string> = {
  OPTION_PRICE_CONFLICT: "같은 메뉴와 용량에 가격이 달라요. 가격을 하나로 맞춰 주세요.",
  NOT_NORMALIZABLE: "메뉴 이름을 확인해 주세요.",
  PRODUCT_INACTIVE: "운영이 중지된 위스키예요. 다른 위스키를 골라 주세요.",
  DUPLICATE_OPTION_VALUES: "같은 용량의 옵션은 하나만 남겨 주세요.",
};

function ReviewBody({ review, menu, bar, onNotice, userId, restart }: ReviewProps & { userId: string; restart: (fresh: ImportReview | null) => void }) {
  const navigate = useNavigate();
  const actions = useImportActions(bar.barId);
  const fail = useBarFailure();
  const updateBar = useUpdateBar(bar.barId);
  const start = useMemo(() => initialReview(review, menu, bar, readDeviceDraft(userId, review.menuImportId)), []); // eslint-disable-line react-hooks/exhaustive-deps
  const [state, setState] = useState<ReviewState>(start.state);
  const [deviceConflict, setDeviceConflict] = useState<DeviceDraft | null>(start.conflict);
  const [open, setOpen] = useState<Record<ReviewGroup, boolean>>({ pending: true, ready: true, other: true, excluded: false });
  const [message, setMessage] = useState<string | null>(null);
  const [publish, setPublish] = useState<Publish | null>(null);
  const [pourText, setPourText] = useState("");
  const [sourceFor, setSourceFor] = useState<ReviewCard | null>(null);
  const [leaving, setLeaving] = useState(false);

  const reread = useCallback(() => void actions.readNow(review.menuImportId).catch(() => undefined), [actions, review.menuImportId]);
  const draft = useDraftSync({
    menuImportId: review.menuImportId,
    reviewVersion: review.reviewVersion,
    userId,
    baseDraftVersion: review.reviewDraft?.draftVersion ?? 0,
    actions,
    onClosed: reread,
    onFailure: (failure) => setMessage(fail(failure)),
  });
  const resumed = useRef(false);
  useEffect(() => {
    // This device's unsent copy is sent again as soon as the review opens.
    if (start.resume && !resumed.current) {
      resumed.current = true;
      draft.schedule(start.state);
    }
  }, [draft, start]);

  const stats = reviewStats(state);
  // Changes after a request (a search, a rematch) apply to the cards as they are then, not as they were.
  const current = useRef(state);
  current.current = state;
  const change = (next: ReviewState) => {
    current.current = next;
    setState(next);
    draft.schedule(next);
  };
  const changeCard = (id: string, update: (card: ReviewCard) => ReviewCard) =>
    change({ ...current.current, cards: current.current.cards.map((card) => (card.id === id ? update(card) : card)) });
  const unlinkedPrices = (name: string) => {
    try {
      return existingUnlinkedOptions(menu, name).map(savedCandidate);
    } catch (failure) {
      setMessage(failure instanceof Error ? failure.message : "기존 메뉴 가격을 확인하지 못했어요. 다시 시도해 주세요.");
      return [];
    }
  };

  const cardActions: CardActions = {
    change: changeCard,
    split: (id) => change(splitMerged(current.current, id, unlinkedPrices)),
    searchCatalog: actions.searchCatalog,
    unlinkedPrices,
    openSource: (card) => openSource(card),
    toast: setMessage,
  };

  async function saveDefaultPour() {
    const n = readNumeric(pourText);
    if (!validDefaultPour(n)) return setMessage("1 ~ 999 사이의 숫자를 입력해주세요.");
    try {
      // Claimed only after the bar is saved (3.7): a failed save must not unlock publishing.
      await updateBar.mutateAsync({ defaultPourMl: n });
      setPourText("");
      change({ ...current.current, defaultPour: n, cards: current.current.cards.map((card) => applyDefaultPour(card, n)) });
    } catch (failure) {
      setMessage(fail(failure) ?? "기본 잔 용량을 저장하지 못했어요. 다시 시도해 주세요.");
    }
  }

  function imageOf(photoIndex: number) {
    return review.images.find((image) => image.imageOrder === photoIndex);
  }

  async function openSource(card: ReviewCard) {
    const image = imageOf(card.photoIndex);
    // A signed URL past its time is read again from the same GET (5.4); the cards stay as they are.
    if (image?.imageUrlExpiresAt && Date.parse(image.imageUrlExpiresAt) <= Date.now()) await actions.readNow(review.menuImportId).catch(() => undefined);
    setSourceFor(card);
  }

  async function leave() {
    setLeaving(true);
    await draft.flush();
    void navigate(`/bars/${bar.barId}/menu`);
  }

  async function confirmPublish() {
    if (publish?.kind === "sending") return;
    const where = await draft.flush();
    if (where === "conflict" || where === "closed") return setPublish(null);
    let body;
    try {
      body = reviewBody(review, state, menu);
    } catch (failure) {
      return setPublish({ kind: "failed", messages: [failure instanceof ReviewSubmitError ? failure.message : "검수 내용을 다시 확인해 주세요."] });
    }
    setPublish({ kind: "sending" });
    try {
      const applied = await actions.apply(review.menuImportId, body);
      draft.discard();
      setPublish({ kind: "done", applied });
    } catch (failure) {
      handlePublishFailure(failure, body.itemDecisions.map((d) => d.extractedItemId));
    }
  }

  function handlePublishFailure(failure: unknown, lineIds: string[]) {
    const code = failure instanceof ApiError ? failure.code : null;
    if (code === "REVIEW_OUTDATED") {
      // The menu changed after the review was built; the server built it again (9.4). It reopens from the draft.
      setPublish(null);
      onNotice("다른 곳에서 메뉴가 바뀌어 검수 내용을 새로 불러왔어요. 확인한 뒤 다시 게시해 주세요.");
      return reread();
    }
    if (code === "INVALID_IMPORT_STATE" || code === "MENU_IMPORT_NOT_FOUND") {
      setPublish(null);
      return reread();
    }
    if (code === "VALIDATION_FAILED" && failure instanceof ApiError) {
      const names = new Map(state.cards.map((card) => [card.id, card.name]));
      const messages = failure.fieldErrors.map((field) => {
        const index = /^itemDecisions\[(\d+)\]/.exec(field.path)?.[1];
        const name = index !== undefined ? names.get(lineIds[Number(index)] ?? "") : undefined;
        const text = PUBLISH_FIELD_COPY[field.code] ?? "검수 내용을 다시 확인해 주세요.";
        return name ? `${name}: ${text}` : text;
      });
      return setPublish({ kind: "failed", messages: messages.length > 0 ? [...new Set(messages)] : ["검수 내용을 다시 확인해 주세요."] });
    }
    if (code === "FORBIDDEN" || code === "BAR_NOT_FOUND") {
      const text = fail(failure);
      return setPublish(text ? { kind: "failed", messages: [text] } : null);
    }
    // No answer, or a server failure: it may have been applied. Never send again before reading the import (8.8).
    setPublish({ kind: "unknown", checking: false });
  }

  async function checkPublished() {
    setPublish({ kind: "unknown", checking: true });
    try {
      const current = await actions.peek(review.menuImportId);
      if (current.status === "applied") {
        draft.discard();
        await actions.refreshBar();
        return setPublish({ kind: "done", applied: null });
      }
      if (current.status === "ready_for_review" && current.reviewVersion === review.reviewVersion) {
        setPublish(null);
        return setMessage("게시되지 않았어요. 검수 내용을 확인한 뒤 다시 게시해 주세요.");
      }
      // Canceled meanwhile, or built again: the status screen shows it.
      setPublish(null);
      reread();
    } catch {
      setPublish({ kind: "unknown", checking: false });
    }
  }

  if (publish?.kind === "done") {
    const added = publish.applied?.result.added;
    const unlinked = publish.applied?.result.unlinkedWhisky ?? 0;
    return (
      <div className={styles.screen}>
        <ImportSteps step={3} />
        <h2 className={styles.title}>메뉴를 게시했어요.</h2>
        {added !== undefined ? <p className={styles.strong}>메뉴에 {added}개를 더했어요.</p> : null}
        <p className={styles.text}>기존에 등록된 메뉴는 삭제하지 않아요.</p>
        {/* Spec 8.10: shown once when the server published whiskies without a product. */}
        {unlinked > 0 ? <p className={styles.notice}>새로 등록한 위스키는 운영자가 확인한 뒤부터 위스키 검색에 나와요.</p> : null}
        <ButtonLink to={`/bars/${bar.barId}/menu`} variant="primary">
          메뉴 관리로 돌아가기
        </ButtonLink>
      </div>
    );
  }

  const preview = publicationPreview(state);
  const draftNotice: Record<string, string | null> = {
    device: "이 기기에는 저장됐어요. 서버 저장을 다시 시도해 주세요.",
    tooLarge: "이 기기에는 저장됐어요. 서버 256KB 제한을 초과했어요. 입력 내용을 줄이면 서버에 저장할 수 있어요.",
  };
  const busy = publish?.kind === "sending" || leaving;

  return (
    <div className={styles.screen}>
      <div className={styles.reviewHead}>
        <ImportSteps step={2} />
        <div className={styles.spread}>
          <p className={styles.strong}>
            검수 {stats.done}/{stats.total} 완료
          </p>
          <p className={styles.text}>
            위스키 {stats.ready.length}, 그 외 메뉴 {stats.other.length}, 제외 {stats.excluded.length}
          </p>
        </div>
        <div className={styles.progress} role="progressbar" aria-label="검수 진행" aria-valuemin={0} aria-valuemax={100} aria-valuenow={stats.percent}>
          <span style={{ width: `${stats.percent}%` }} />
        </div>
      </div>
      {message ? (
        <p className={styles.notice} role="status">
          {message}
        </p>
      ) : null}
      {draftNotice[draft.status] ? (
        <div className={styles.row}>
          <p className={styles.notice} role="status">
            {draftNotice[draft.status]}
          </p>
          {draft.status === "device" ? (
            <Button variant="secondary" onClick={draft.retry}>
              다시 시도
            </Button>
          ) : null}
        </div>
      ) : null}

      <div className={styles.row}>
        <TextField
          label={`기본 잔 용량 (지금 ${validDefaultPour(state.defaultPour) ? `${state.defaultPour}ml` : "없음"})`}
          inputMode="numeric"
          placeholder="예: 30"
          value={pourText}
          onChange={(event) => setPourText(event.currentTarget.value)}
        />
        <Button variant="secondary" busy={updateBar.isPending} disabled={pourText.trim() === ""} onClick={() => void saveDefaultPour()}>
          적용
        </Button>
      </div>
      {stats.noDefault ? <p className={styles.error}>매장 기본 잔 용량을 입력해주세요.</p> : null}

      {GROUPS.map(({ group, title }) => {
        const cards = stats[group];
        if (cards.length === 0) return null;
        return (
          <section key={group} className={styles.group} aria-label={title}>
            <button type="button" className={styles.groupHead} aria-expanded={open[group]} onClick={() => setOpen({ ...open, [group]: !open[group] })}>
              <span>
                {title} {cards.length}
              </span>
              <span aria-hidden="true">{open[group] ? "⌃" : "⌄"}</span>
            </button>
            {open[group] ? (
              <ul className={styles.cards}>
                {cards.map((card) => (
                  <ReviewCardView key={card.id} card={card} state={state} actions={cardActions} />
                ))}
              </ul>
            ) : null}
          </section>
        );
      })}

      <div className={styles.footer}>
        <Button variant="secondary" busy={leaving} disabled={busy} onClick={() => void leave()}>
          나중에 하기
        </Button>
        <Button disabled={!stats.canPublish || busy} onClick={() => setPublish({ kind: "confirm" })}>
          게시하기
        </Button>
      </div>

      <BottomSheet open={publish?.kind === "confirm" || publish?.kind === "sending"} title="이대로 게시할까요?" onClose={() => publish?.kind !== "sending" && setPublish(null)}>
        <p className={barStyles.sheetText}>
          위스키 {stats.ready.length}, 그 외 메뉴 {stats.other.length}, 제외 {stats.excluded.length}
          {preview.changedExistingPrices > 0 ? <><br />기존 가격 변경 {preview.changedExistingPrices}건</> : null}
          {preview.publishWithoutProduct > 0 ? <><br />연결 없이 등록할 메뉴 {preview.publishWithoutProduct}건</> : null}
          <br />
          기존에 등록된 메뉴는 삭제하지 않아요.
        </p>
        <div className={barStyles.actions}>
          <Button variant="secondary" disabled={publish?.kind === "sending"} onClick={() => setPublish(null)}>
            검수로 돌아가기
          </Button>
          <Button busy={publish?.kind === "sending"} onClick={() => void confirmPublish()}>
            게시하기
          </Button>
        </div>
      </BottomSheet>

      <BottomSheet open={publish?.kind === "failed"} title="게시하지 못했어요" onClose={() => setPublish(null)}>
        {publish?.kind === "failed" ? (
          <ul className={styles.issues} role="alert">
            {publish.messages.map((text) => (
              <li key={text}>{text}</li>
            ))}
          </ul>
        ) : null}
        <div className={barStyles.actions}>
          <Button onClick={() => setPublish(null)}>검수로 돌아가기</Button>
        </div>
      </BottomSheet>

      <BottomSheet open={publish?.kind === "unknown"} title="게시 결과를 확인하지 못했어요" onClose={() => undefined}>
        <p className={barStyles.sheetText}>요청이 이미 처리되었을 수 있어요. 다시 게시하기 전에 게시 상태를 확인해 주세요.</p>
        <div className={barStyles.actions}>
          <Button busy={publish?.kind === "unknown" && publish.checking} onClick={() => void checkPublished()}>
            게시 상태 확인
          </Button>
        </div>
      </BottomSheet>

      <BottomSheet open={draft.status === "conflict" || deviceConflict !== null} title="다른 곳에서 먼저 저장한 검수 내용이 있어요" onClose={() => undefined}>
        <p className={barStyles.sheetText}>다른 기기나 운영자가 이 검수를 고쳤어요. 어느 내용으로 이어 할까요?</p>
        <div className={barStyles.actions}>
          <Button
            variant="secondary"
            onClick={() => {
              // The other draft wins: this device's copy is dropped and the review opens again from the server.
              draft.discard();
              setDeviceConflict(null);
              void actions
                .readNow(review.menuImportId)
                .then((fresh) => restart(fresh.status === "ready_for_review" ? fresh : null))
                .catch(() => restart(null));
            }}
          >
            다른 곳 내용으로 이어 하기
          </Button>
          <Button
            onClick={() => {
              if (deviceConflict) {
                const restored = restoreDraft(mapReview(review, menu, bar.defaultPourMl), review, { reviewVersion: deviceConflict.reviewVersion, content: deviceConflict.content });
                setDeviceConflict(null);
                setState(restored);
                draft.schedule(restored);
                draft.overwrite(review.reviewDraft?.draftVersion ?? 0);
              } else draft.overwrite();
            }}
          >
            이 기기 내용으로 덮어쓰기
          </Button>
        </div>
      </BottomSheet>

      <BottomSheet open={sourceFor !== null} title="원본 사진" onClose={() => setSourceFor(null)}>
        {sourceFor ? <SourcePhoto card={sourceFor} url={imageOf(sourceFor.photoIndex)?.imageUrl ?? null} onExpired={reread} /> : null}
        <div className={barStyles.actions}>
          <Button variant="secondary" onClick={() => setSourceFor(null)}>
            닫기
          </Button>
        </div>
      </BottomSheet>
    </div>
  );
}

/**
 * The photo with the line's box (5.4 `sourceBox`, 0 to 1000 of each side), drawn over the image, so the signed
 * URL is shown as it is. A failed image (an expired URL) reads the import again once for a new one.
 */
function SourcePhoto({ card, url, onExpired }: { card: ReviewCard; url: string | null; onExpired: () => void }) {
  const retried = useRef(false);
  const box = card.sourceBox;
  return (
    <>
      <p className={styles.caption}>{card.raw}</p>
      {url ? (
        <figure className={styles.source}>
          <img
            src={url}
            alt={`${card.photoIndex}번째 메뉴판 사진`}
            onError={() => {
              if (!retried.current) {
                retried.current = true;
                onExpired();
              }
            }}
          />
          {box ? (
            <span
              className={styles.sourceBox}
              style={{ left: `${box[0]! / 10}%`, top: `${box[1]! / 10}%`, width: `${(box[2]! - box[0]!) / 10}%`, height: `${(box[3]! - box[1]!) / 10}%` }}
            />
          ) : null}
        </figure>
      ) : null}
      {!box ? <p className={styles.caption}>사진에서 메뉴 위치를 특정하지 못했어요.</p> : null}
    </>
  );
}
