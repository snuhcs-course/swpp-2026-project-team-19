/**
 * The review screen's model, ported from android/.../ui/owner/review/PhotoReviewModels.kt.
 *
 * One card per menu line of the photos (5.4 `items[]`). The app keeps a card's first option apart from the
 * others ("primary option"); here every option is in `options`, with the same rules. As in the app, a number the
 * owner typed that is not valid is `NaN`, and "no value" is `0` or `NaN`: validity is always checked with
 * `validVolume` and `validPrice`.
 */
export type CardType = "whisky" | "other";

/** How the line was matched to the catalog when the review started. */
export type ReviewMatch = "exact" | "ambiguous" | "candidate" | "new";

/** Why a line goes to the operator after publishing (shown, never sent). */
export type OperatorReason = "new" | "changed" | "unlinked";

export type ReviewGroup = "pending" | "ready" | "other" | "excluded";

/** A problem that keeps a card in "확인 필요". */
export type ReviewIssue =
  | "catalogSearch"
  | "match"
  | "candidate"
  | "new"
  | "priceChoice"
  | "price"
  | "volume"
  | "option"
  | "name"
  | "duplicatePrice";

export interface CatalogChoice {
  productId: string;
  name: string;
  isActive: boolean;
}

/** A serving read from the photo, as the photo has it. Owner corrections never change it. */
export interface RecognizedOffer {
  volumeMl: number | null;
  bottle: boolean;
  priceKrw: number | null;
}

/** One serving the owner will publish. */
export interface ReviewOption {
  /** ml; 0 for a bottle, NaN for none. */
  volume: number;
  price: number;
  bottle: boolean;
  /** The extracted option it came from (5.4), or null for one the owner added. */
  sourceOptionId: string | null;
  label: string | null;
  /** The photo gave no pour, so the bar's default was used: it follows the default when that changes. */
  fromDefault: boolean;
}

/** A price for one serving: from a photo line, or the bar's current menu (`existing`). */
export interface PriceCandidate {
  servingKey: string;
  volumeMl: number | null;
  bottle: boolean;
  label: string | null;
  priceKrw: number;
  existing: boolean;
  sourceItemId: string | null;
}

/** Another line of the photos merged into this card because it is the same whisky (8.12). */
export interface MergedLine {
  id: string;
  photoIndex: number;
  sourceLine: number;
  raw: string;
  recognizedName: string;
  offers: RecognizedOffer[];
  sourceBox: number[] | null;
}

/** What "분류 변경" keeps so that changing back restores the card. */
export interface ClassificationSnapshot {
  type: CardType;
  options: ReviewOption[];
  match: ReviewMatch;
  matchConfirmed: boolean;
  nameSaved: boolean;
  newConfirmed: boolean;
  linkedProductId: string | null;
  linkedProductName: string | null;
  candidates: CatalogChoice[];
}

export interface ReviewCard {
  id: string;
  /** The menu name to publish. */
  name: string;
  /** The name read from the photo. */
  recognizedName: string;
  type: CardType;
  match: ReviewMatch;
  matchConfirmed: boolean;
  newConfirmed: boolean;
  nameSaved: boolean;
  linkedProductId: string | null;
  linkedProductName: string | null;
  candidates: CatalogChoice[];
  options: ReviewOption[];
  /** Field text that is not a valid number yet, by field key, so it stays as typed. */
  rawEdits: Record<string, string>;
  priceCandidates: PriceCandidate[];
  /** The price chosen for a serving with several, by serving key. */
  chosenServingPrices: Record<string, number>;
  /** More than three servings were read: the owner picks up to three. */
  volumeChoices: ReviewOption[];
  chosenVolumeKeys: string[];
  volumeChoicesConfirmed: boolean;
  excluded: boolean;
  /** Counts toward "검수 n/m 완료". */
  required: boolean;
  /** The card this line was merged into; it is sent as `reject` and its servings go with that card. */
  mergedInto: string | null;
  mergeSources: MergedLine[];
  /** The card's own options before merging, restored when the owner splits it. */
  preMergeOptions: ReviewOption[];
  manuallySplit: boolean;
  operatorReason: OperatorReason | null;
  classificationSnapshot: ClassificationSnapshot | null;
  /** Searching the catalog for another whisky (spec 7). */
  searchMode: boolean;
  /** Typing a new menu name. */
  nameEditing: boolean;
  raw: string;
  photoIndex: number;
  sourceLine: number;
  sourceBox: number[] | null;
  recognizedOffers: RecognizedOffer[];
}

export interface ReviewState {
  cards: ReviewCard[];
  /** The bar's default glass size (3.6 `defaultPourMl`). */
  defaultPour: number;
  /** The bar's current prices for each catalog product, every serving (3.9). */
  savedByProduct: Record<string, PriceCandidate[]>;
}

// ---- Number rules (PhotoReviewModels.kt) ----

/** `readNumeric`: digits with an optional decimal part, commas and spaces ignored; NaN otherwise. */
export function readNumeric(raw: string | null | undefined): number {
  const cleaned = (raw ?? "").replaceAll(",", "").trim();
  return /^\d+(?:\.\d+)?$/.test(cleaned) ? Number(cleaned) : Number.NaN;
}

/** `priceValue`: whole won, commas, spaces and a trailing "원" ignored; NaN otherwise. */
export function priceValue(raw: string | null | undefined): number {
  let text = (raw ?? "").trim().replace(/[,\s]/g, "");
  if (text.endsWith("원")) text = text.slice(0, -1);
  return /^\d+$/.test(text) && text.length <= 15 ? Number(text) : Number.NaN;
}

export const validPrice = (n: number): boolean => Number.isInteger(n) && n >= 1 && n <= 99_999_999;

/** A serving's pour (8.1): 1 to 32767 ml. */
export const validVolume = (n: number): boolean => Number.isInteger(n) && n >= 1 && n <= 32_767;

/** The bar's default pour (3.7): 1 to 999 ml. */
export const validDefaultPour = (n: number): boolean => validVolume(n) && n <= 999;

/** "15,000원", or "—" without a price. */
export function won(n: number | null | undefined): string {
  return n !== null && n !== undefined && n > 0 ? `${Math.trunc(n).toLocaleString("ko-KR")}원` : "—";
}

/** A number as a field shows it: 30, 22.5, or empty. */
export function numberText(n: number): string {
  return Number.isNaN(n) ? "" : String(n);
}
