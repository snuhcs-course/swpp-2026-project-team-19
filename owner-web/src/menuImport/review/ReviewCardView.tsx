import { useState } from "react";
import type { CatalogProduct } from "../../owner/queries";
import { Button } from "../../ui/Button";
import { TextField } from "../../ui/TextField";
import { won, type PriceCandidate, type ReviewCard, type ReviewIssue, type ReviewState } from "./model";
import {
  addOption,
  applyRematch,
  chooseServingPrice,
  confirmNew,
  confirmVolumeChoices,
  editOption,
  exactCatalogMatches,
  markAsNewForOperator,
  markLinked,
  MAX_REVIEW_OPTIONS,
  mergedNotice,
  optionFieldText,
  pendingPriceServings,
  priceCandidatesForServing,
  problems,
  rebindUnlinkedPrices,
  reclassify,
  removeOption,
  servingKey,
  sourceLocation,
  toggleBottle,
  toggleVolumeChoice,
  validMenuName,
} from "./rules";
import styles from "../menuImport.module.css";

/** Spec 7.1: a catalog search query is 1 to 100 characters. The app finds nothing for a longer one (`searchCatalogLive`). */
export const CATALOG_QUERY_MAX = 100;

export interface CardActions {
  change: (id: string, update: (card: ReviewCard) => ReviewCard) => void;
  split: (id: string) => void;
  searchCatalog: (query: string) => Promise<CatalogProduct[]>;
  unlinkedPrices: (name: string) => PriceCandidate[];
  openSource: (card: ReviewCard) => void;
  toast: (message: string) => void;
}

/** What each problem asks of the owner (PhotoReviewCard.kt), with commas for the app's middle dots. */
function issueText(issue: ReviewIssue, card: ReviewCard): string {
  switch (issue) {
    case "catalogSearch":
      return "위스키를 검색해 주세요";
    case "match":
      return "위스키가 맞는지 확인해 주세요";
    case "candidate":
      return "위스키를 선택해 주세요";
    case "new":
      return "새로운 메뉴예요. 이름을 확인해 주세요";
    case "priceChoice":
      return "가격을 선택해 주세요";
    case "price":
      return "가격을 입력해 주세요";
    case "volume":
      return "용량을 입력해 주세요";
    case "option":
      return !card.volumeChoicesConfirmed ? "등록할 용량을 선택해 주세요." : "같은 용량의 옵션은 하나만 남겨 주세요. 용량은 최대 3가지까지 설정 가능해요.";
    case "name":
      return "메뉴 이름을 확인해 주세요.";
    case "duplicatePrice":
      return card.type === "whisky" ? "같은 위스키, 용량의 사진별 가격이 달라요" : "같은 메뉴, 옵션의 사진별 가격이 달라요";
  }
}

const servingLabel = (option: { bottle: boolean; volume: number }) => (option.bottle ? "Bottle" : Number.isInteger(option.volume) && option.volume > 0 ? `${option.volume}ml` : "용량 미인식");

/** One line of the photos to confirm (android/.../ui/owner/review/PhotoReviewCard.kt). */
export function ReviewCardView({ card, state, actions }: { card: ReviewCard; state: ReviewState; actions: CardActions }) {
  const issues = problems(card, state);
  const change = (update: (current: ReviewCard) => ReviewCard) => actions.change(card.id, update);
  const notice = mergedNotice(card);

  return (
    <li className={styles.card} aria-label={card.name || "이름 없는 메뉴"}>
      <div className={styles.spread}>
        <h3 className={styles.cardName}>{card.name || "이름 없는 메뉴"}</h3>
        <button type="button" className={styles.linkButton} onClick={() => actions.openSource(card)} aria-label={`${sourceLocation(card)} 원본 사진 크게 보기`}>
          원본 보기
        </button>
      </div>
      <p className={styles.caption}>
        {sourceLocation(card)}, 사진 속 글자: {card.raw}
      </p>
      {notice ? (
        <div className={styles.spread}>
          <p className={styles.text}>{notice}</p>
          {card.mergeSources.length > 0 ? (
            <button type="button" className={styles.linkButton} onClick={() => actions.split(card.id)}>
              서로 다른 위스키예요, 원본 줄 분리
            </button>
          ) : null}
        </div>
      ) : null}
      {issues.length > 0 ? (
        <ul className={styles.issues}>
          {issues.map((issue) => (
            <li key={issue}>{issueText(issue, card)}</li>
          ))}
        </ul>
      ) : null}

      {card.excluded ? (
        <button type="button" className={styles.linkButton} onClick={() => change((c) => ({ ...c, excluded: false, required: true }))}>
          다시 포함
        </button>
      ) : (
        <>
          {card.type === "whisky" ? <MatchPanel card={card} state={state} actions={actions} /> : null}
          <NameEditor card={card} state={state} actions={actions} />
          {!card.volumeChoicesConfirmed ? <VolumeChoices card={card} change={change} /> : <OptionsEditor card={card} state={state} change={change} />}
          <PriceChoices card={card} state={state} change={change} />
          <div className={styles.row}>
            <button type="button" className={styles.linkButton} onClick={() => change((c) => reclassify(c, state.defaultPour))}>
              {card.type === "whisky" ? "그 외 메뉴로 분류" : "위스키로 분류"}
            </button>
            <button type="button" className={styles.linkButton} onClick={() => change((c) => ({ ...c, excluded: true, searchMode: false, nameEditing: false }))}>
              게시 제외
            </button>
          </div>
        </>
      )}
    </li>
  );
}

/** The catalog product of a whisky line: confirm the match, pick a candidate, search, or publish without one. */
function MatchPanel({ card, state, actions }: { card: ReviewCard; state: ReviewState; actions: CardActions }) {
  const change = (update: (current: ReviewCard) => ReviewCard) => actions.change(card.id, update);
  const [picked, setPicked] = useState<string | null>(null);
  const startSearch = () => change((c) => ({ ...c, searchMode: true, nameEditing: false }));
  if (card.searchMode) return <SearchPanel card={card} state={state} actions={actions} />;
  if (card.match === "ambiguous" && !card.nameSaved) {
    const only = card.candidates[0];
    return (
      <div className={styles.choices}>
        <p className={styles.text}>이 위스키가 맞나요? {only?.name}</p>
        <div className={styles.row}>
          <Button variant="secondary" onClick={() => only && change((c) => markLinked(c, { productId: only.productId, name: only.name }, state.savedByProduct))}>
            맞아요
          </Button>
          <Button variant="secondary" onClick={startSearch}>
            아니에요
          </Button>
        </div>
      </div>
    );
  }
  if (card.match === "candidate" && !card.matchConfirmed) {
    return (
      <fieldset className={styles.choices}>
        <legend>위스키를 선택해 주세요</legend>
        {card.candidates.map((candidate) => (
          <label key={candidate.productId} className={styles.choice}>
            <input type="radio" name={`candidate-${card.id}`} checked={picked === candidate.productId} onChange={() => setPicked(candidate.productId)} />
            {candidate.name}
          </label>
        ))}
        <div className={styles.row}>
          <Button
            variant="secondary"
            onClick={() => {
              const chosen = card.candidates.find((c) => c.productId === picked);
              if (!chosen) return actions.toast("위스키를 먼저 선택해 주세요.");
              change((c) => markLinked(c, { productId: chosen.productId, name: chosen.name }, state.savedByProduct));
            }}
          >
            이 위스키로 선택
          </Button>
          <button type="button" className={styles.linkButton} onClick={startSearch}>
            다른 위스키 검색
          </button>
        </div>
      </fieldset>
    );
  }
  if (card.match === "new" && !card.nameSaved) {
    return (
      <div className={styles.choices}>
        <p className={styles.text}>새로운 메뉴예요. 카탈로그에서 찾지 못한 위스키는 이름으로 등록하고, 운영자가 확인한 뒤 연결해요.</p>
        <div className={styles.row}>
          <Button
            variant="secondary"
            disabled={card.nameEditing || !validMenuName(card.name)}
            onClick={() => change(confirmNew)}
          >
            이 이름으로 등록
          </Button>
          <button type="button" className={styles.linkButton} onClick={startSearch}>
            위스키 검색
          </button>
        </div>
      </div>
    );
  }
  return (
    <div className={styles.spread}>
      <p className={styles.text}>
        {card.linkedProductId !== null ? `연결된 위스키: ${card.linkedProductName ?? card.name}` : "상품 연결 없이 등록해요. 운영자가 확인한 뒤 연결해요."}
      </p>
      <button type="button" className={styles.linkButton} onClick={startSearch}>
        다른 위스키 검색
      </button>
    </div>
  );
}

/** Spec 7: the catalog search; inactive products are shown but cannot be picked (7.2). */
function SearchPanel({ card, state, actions }: { card: ReviewCard; state: ReviewState; actions: CardActions }) {
  const change = (update: (current: ReviewCard) => ReviewCard) => actions.change(card.id, update);
  const [query, setQuery] = useState(card.name);
  const [results, setResults] = useState<CatalogProduct[] | null>(null);
  const [picked, setPicked] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function search() {
    const text = query.trim();
    if (text === "") return actions.toast("검색할 위스키 이름을 입력해 주세요.");
    if (text.length > CATALOG_QUERY_MAX) return setResults([]);
    setBusy(true);
    try {
      setResults(await actions.searchCatalog(text));
      setPicked(null);
    } catch {
      actions.toast("검색하지 못했어요. 다시 시도해 주세요.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className={styles.choices}>
      <div className={styles.row}>
        <TextField label="위스키 이름 검색" type="search" value={query} maxLength={CATALOG_QUERY_MAX} onChange={(event) => setQuery(event.currentTarget.value)} />
        <Button variant="secondary" busy={busy} onClick={() => void search()}>
          검색
        </Button>
      </div>
      {results !== null && results.length === 0 ? <p className={styles.text}>검색된 위스키가 없어요.</p> : null}
      {results !== null && results.length > 0 ? (
        <fieldset className={styles.choices}>
          <legend>검색 결과</legend>
          {results.map((product) => (
            <label key={product.productId} className={styles.choice}>
              <input type="radio" name={`search-${card.id}`} disabled={!product.isActive} checked={picked === product.productId} onChange={() => setPicked(product.productId)} />
              {product.displayName}
              {product.isActive ? "" : " (비활성, 운영자 문의)"}
            </label>
          ))}
        </fieldset>
      ) : null}
      <div className={styles.row}>
        <Button
          variant="secondary"
          disabled={picked === null}
          onClick={() => {
            const chosen = results?.find((product) => product.productId === picked && product.isActive);
            if (!chosen) return actions.toast("위스키를 먼저 선택해 주세요.");
            change((c) => markLinked(c, { productId: chosen.productId, name: chosen.displayName }, state.savedByProduct));
          }}
        >
          이 위스키로 선택
        </Button>
        <button type="button" className={styles.linkButton} onClick={() => change((c) => ({ ...c, searchMode: false }))}>
          검색 닫기
        </button>
      </div>
      <p className={styles.text}>찾는 위스키가 없어요</p>
      <Button variant="secondary" onClick={() => change((c) => markAsNewForOperator(c, query))}>
        새로 등록하기
      </Button>
    </div>
  );
}

/**
 * The menu name. A renamed whisky is matched again by its new name (decision 2, as the server does on publishing,
 * 8.11); a menu without a product takes the saved prices of the bar's item of that name.
 */
function NameEditor({ card, state, actions }: { card: ReviewCard; state: ReviewState; actions: CardActions }) {
  const change = (update: (current: ReviewCard) => ReviewCard) => actions.change(card.id, update);
  const [text, setText] = useState(card.name);
  const [busy, setBusy] = useState(false);

  if (!card.nameEditing) {
    return (
      <button type="button" className={styles.linkButton} onClick={() => (setText(card.name), change((c) => ({ ...c, nameEditing: true })))}>
        메뉴 이름 수정
      </button>
    );
  }

  async function save() {
    const proposed = text.trim();
    if (!validMenuName(proposed)) return actions.toast("메뉴 이름을 다시 확인해 주세요.");
    const renamed = (c: ReviewCard): ReviewCard => ({ ...c, name: proposed, nameSaved: true, nameEditing: false });
    if (card.type !== "whisky") {
      const saved = actions.unlinkedPrices(proposed);
      return change((c) => rebindUnlinkedPrices(renamed(c), saved));
    }
    setBusy(true);
    try {
      // A name longer than a search allows matches no product (as in the app): it is published without one.
      const found = proposed.length > CATALOG_QUERY_MAX ? [] : await actions.searchCatalog(proposed);
      const matches = exactCatalogMatches(found, proposed).map((p) => ({ productId: p.productId, name: p.displayName }));
      const saved = matches.length === 1 ? [] : actions.unlinkedPrices(proposed);
      let outcome = "";
      change((c) => {
        const [next, result] = applyRematch(renamed(c), matches, state.savedByProduct);
        outcome = result;
        return next.linkedProductId === null ? rebindUnlinkedPrices(next, saved) : next;
      });
      if (outcome === "operator") actions.toast("메뉴 이름 저장, 상품 연결은 관리자 검토 대상이에요.");
    } catch {
      // A failed search is not "no product": the link stays.
      actions.toast("위스키 검색에 실패했어요. 연결을 유지하고 다시 시도해 주세요.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className={styles.row}>
      <TextField label="메뉴 이름" value={text} maxLength={200} onChange={(event) => setText(event.currentTarget.value)} />
      <Button variant="secondary" busy={busy} onClick={() => void save()}>
        저장
      </Button>
      <button type="button" className={styles.linkButton} disabled={busy} onClick={() => change((c) => ({ ...c, nameEditing: false }))}>
        취소
      </button>
    </div>
  );
}

/** More than three servings were read: the owner keeps up to three (LiveWhiskyReviewGrouping.kt). */
function VolumeChoices({ card, change }: { card: ReviewCard; change: (update: (current: ReviewCard) => ReviewCard) => void }) {
  return (
    <fieldset className={styles.choices}>
      <legend>등록할 용량을 선택해 주세요. 최대 3가지까지 설정 가능해요.</legend>
      {card.volumeChoices.map((option) => {
        const key = servingKey(option);
        return (
          <label key={key} className={styles.choice}>
            <input type="checkbox" checked={card.chosenVolumeKeys.includes(key)} onChange={() => change((c) => toggleVolumeChoice(c, key))} />
            {servingLabel(option)} {won(option.price)}
          </label>
        );
      })}
      <Button variant="secondary" disabled={card.chosenVolumeKeys.length === 0} onClick={() => change(confirmVolumeChoices)}>
        선택한 용량 적용
      </Button>
    </fieldset>
  );
}

/** The servings to publish: volume (or Bottle) and price, at most three. */
function OptionsEditor({ card, state, change }: { card: ReviewCard; state: ReviewState; change: (update: (current: ReviewCard) => ReviewCard) => void }) {
  return (
    <div className={styles.choices}>
      <p className={styles.text}>용량별 가격</p>
      {card.options.map((option, index) => (
        <div key={index} className={styles.optionRow} role="group" aria-label={`${index + 1}번 옵션`}>
          {option.bottle ? (
            <p className={styles.strong}>Bottle</p>
          ) : (
            <TextField
              label="용량 (ml)"
              inputMode="numeric"
              placeholder={card.type === "other" ? "없으면 비워 두세요" : "예: 30"}
              value={optionFieldText(card, "volume", index)}
              onChange={(event) => {
                const value = event.currentTarget.value;
                change((c) => editOption(c, "volume", index, value));
              }}
            />
          )}
          <TextField
            label="가격 (원)"
            inputMode="numeric"
            placeholder="예: 15,000"
            value={optionFieldText(card, "price", index)}
            onChange={(event) => {
              const value = event.currentTarget.value;
              change((c) => editOption(c, "price", index, value));
            }}
          />
          <div className={styles.optionTools}>
            <label className={styles.choice}>
              <input type="checkbox" checked={option.bottle} onChange={() => change((c) => toggleBottle(c, index, state.defaultPour))} />
              Bottle 판매
            </label>
            <button type="button" className={styles.linkButton} onClick={() => change((c) => removeOption(c, index))}>
              옵션 삭제
            </button>
          </div>
        </div>
      ))}
      <button type="button" className={styles.linkButton} disabled={card.options.length >= MAX_REVIEW_OPTIONS} onClick={() => change((c) => addOption(c, state.defaultPour))}>
        + 가격 옵션 추가
      </button>
    </div>
  );
}

/** A serving with several prices (the photo lines, the bar's current menu): the owner picks one. */
function PriceChoices({ card, state, change }: { card: ReviewCard; state: ReviewState; change: (update: (current: ReviewCard) => ReviewCard) => void }) {
  const keys = [...new Set(card.options.map(servingKey))].filter((key) => new Set(priceCandidatesForServing(card, key, state.savedByProduct).map((c) => c.priceKrw)).size > 1);
  if (keys.length === 0) return null;
  const pending = new Set(pendingPriceServings(card, state.savedByProduct));
  return (
    <>
      {keys.map((key) => {
        const option = card.options.find((o) => servingKey(o) === key);
        const prices = new Map<number, boolean>();
        for (const candidate of priceCandidatesForServing(card, key, state.savedByProduct)) prices.set(candidate.priceKrw, (prices.get(candidate.priceKrw) ?? false) || candidate.existing);
        return (
          <fieldset key={key} className={styles.choices}>
            <legend>{option ? servingLabel(option) : key} 가격을 선택해 주세요</legend>
            {[...prices].map(([price, existing]) => (
              <label key={price} className={styles.choice}>
                <input
                  type="radio"
                  name={`price-${card.id}-${key}`}
                  checked={!pending.has(key) && option?.price === price}
                  onChange={() => change((c) => chooseServingPrice(c, key, price, state.savedByProduct))}
                />
                {existing ? "기존" : "사진"} {won(price)}
              </label>
            ))}
          </fieldset>
        );
      })}
    </>
  );
}
